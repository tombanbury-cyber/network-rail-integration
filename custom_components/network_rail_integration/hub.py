"""Hub that maintains the STOMP connection and shares latest data."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_ENABLE_TD,
    CONF_EVENT_TYPES,
    CONF_PASSWORD,
    CONF_STANOX_FILTER,
    CONF_STATIONS,
    CONF_TD_AREAS,
    CONF_TOC_FILTER,
    CONF_TOPIC,
    CONF_USERNAME,
    DEFAULT_TD_TOPIC,
    DEFAULT_TOPIC,
    DISPATCH_CONNECTED,
    DISPATCH_MOVEMENT,
    DISPATCH_TD,
    NR_HOST,
    NR_PORT,
)
from .td_parser import BerthState, parse_td_message, apply_td_filters

_LOGGER = logging.getLogger(__name__)


@dataclass
class HubState:
    connected: bool = False
    last_movement: dict[str, Any] | None = None
    last_movement_per_station: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_batch_count: int = 0
    last_error: str | None = None
    last_seen_monotonic: float | None = None
    # Train Describer state
    last_td_message: dict[str, Any] | None = None
    berth_state: BerthState = field(default_factory=BerthState)
    td_message_count: int = 0


class OpenRailDataHub:
    """Owns the background STOMP client thread."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, debug_logger=None) -> None:
        self.hass = hass
        self.entry = entry
        self.state = HubState()
        self.debug_logger = debug_logger if debug_logger else _LOGGER

        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    async def async_start(self) -> None:
        """Start the background thread."""
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f"network_rail_integration-{self.entry.entry_id}",
            daemon=True,
        )
        self._thread.start()

    async def async_stop(self) -> None:
        """Stop the background thread."""
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            await self.hass.async_add_executor_job(self._thread.join, 5)

    def _thread_main(self) -> None:
        """Blocking thread loop to manage STOMP connection."""
        try:
            import stomp  # type: ignore
        except Exception as exc:  # pragma: no cover
            _LOGGER.error("Failed to import stomp.py: %s", exc)
            return

        username = self.entry.data.get(CONF_USERNAME)
        password = self.entry.data.get(CONF_PASSWORD)
        topic = self.entry.data.get(CONF_TOPIC, DEFAULT_TOPIC)
        dest = f"/topic/{topic}"

        def _read_options() -> dict[str, Any]:
            opt = self.entry.options
            return {
                CONF_STANOX_FILTER: opt.get(CONF_STANOX_FILTER, ""),
                CONF_STATIONS: opt.get(CONF_STATIONS, []),
                CONF_TOC_FILTER: opt.get(CONF_TOC_FILTER, ""),
                CONF_EVENT_TYPES: opt.get(CONF_EVENT_TYPES, []),
                CONF_ENABLE_TD: opt.get(CONF_ENABLE_TD, False),
                CONF_TD_AREAS: opt.get(CONF_TD_AREAS, []),
            }

        reconnect_delay = 5

        class _Listener(stomp.ConnectionListener):  # type: ignore
            def __init__(self, hub: "OpenRailDataHub", conn_ref) -> None:
                self._hub = hub
                self._hass = hub.hass
                self._conn_ref = conn_ref

            def on_connected(self, frame):  # noqa: N802
                self._hub.debug_logger.info("Connected to STOMP broker; subscribing to %s", dest)
                self._set_connected(True)
                try:
                    # Subscribe to primary topic (train movements)
                    self._conn_ref.subscribe(
                        destination=dest, 
                        id=1, 
                        ack="auto",
                        headers={
                            "activemq.subscriptionName": f"network_rail_integration-{topic}",
                        },
                    )
                    
                    # Subscribe to Train Describer if enabled
                    options = _read_options()
                    if options.get(CONF_ENABLE_TD, False):
                        td_dest = f"/topic/{DEFAULT_TD_TOPIC}"
                        td_areas = options.get(CONF_TD_AREAS, [])
                        self._hub.debug_logger.info(
                            "Subscribing to Train Describer feed: %s (areas: %s)", 
                            td_dest,
                            ", ".join(td_areas) if td_areas else "all"
                        )
                        self._conn_ref.subscribe(
                            destination=td_dest,
                            id=2,
                            ack="auto",
                            headers={
                                "activemq.subscriptionName": f"network_rail_integration-{DEFAULT_TD_TOPIC}",
                            },
                        )
                        self._hub.debug_logger.info("Successfully subscribed to Train Describer feed")
                    else:
                        self._hub.debug_logger.debug("Train Describer feed is disabled")
                except Exception as exc:
                    self._hub.debug_logger.error("Subscribe failed: %s", exc)

            def on_disconnected(self):  # noqa: N802
                self._hub.debug_logger.warning("Disconnected from STOMP broker")
                self._set_connected(False)

            def on_heartbeat_timeout(self):  # noqa: N802
                self._hub.debug_logger.warning("STOMP heartbeat timeout")
                self._set_connected(False)

            def on_error(self, frame):  # noqa: N802
                self._hub.debug_logger.error("STOMP error frame: %s", getattr(frame, "body", frame))

            def on_message(self, frame):  # noqa: N802
                body = getattr(frame, "body", "")
                try:
                    payload = json.loads(body)
                except Exception:
                    _LOGGER.debug("Non-JSON message received (ignored)")
                    return

                # Check if this is a Train Describer message (dict with *_MSG keys)
                if isinstance(payload, dict):
                    self._hub.debug_logger.debug("Received dict payload, checking if TD message")
                    # Try to handle as TD message
                    if self._handle_td_message(payload):
                        # Successfully handled as TD message
                        return
                    # Not a valid TD message, continue to process as other message type
                    self._hub.debug_logger.debug("Dict payload was not a TD message, continuing processing")

                # Feed is a JSON list (may be empty) for train movements
                if not isinstance(payload, list) or not payload:
                    self._mark_seen(0)
                    return

                options = _read_options()
                stanox_filter = (options.get(CONF_STANOX_FILTER) or "").strip()
                stations = options.get(CONF_STATIONS, [])
                toc_filter = (options.get(CONF_TOC_FILTER) or "").strip()
                event_types = set(options.get(CONF_EVENT_TYPES) or [])
                
                # Build set of station stanox codes to track
                tracked_stanox = set()
                if stanox_filter:  # Backward compatibility with old single filter
                    tracked_stanox.add(stanox_filter)
                for station in stations:
                    stanox = station.get("stanox", "").strip()
                    if stanox:
                        tracked_stanox.add(stanox)

                last = None
                kept = 0
                station_movements = {}  # stanox -> last movement for that station
                
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    header = item.get("header") or {}
                    if header.get("msg_type") != "0003":
                        continue  # movement only
                    mv = item.get("body") or {}
                    loc_stanox = str(mv.get("loc_stanox", ""))
                    
                    # Check if this movement is for a tracked station
                    if tracked_stanox and loc_stanox not in tracked_stanox:
                        continue
                    if toc_filter and str(mv.get("toc_id", "")) != toc_filter:
                        continue
                    if event_types and str(mv.get("event_type", "")) not in event_types:
                        continue

                    kept += 1
                    last = item
                    
                    # Track per station
                    if loc_stanox:
                        station_movements[loc_stanox] = item

                self._mark_seen(len(payload))

                if last is None:
                    return

                self._publish_last_movement(last, kept, station_movements)

            def _handle_td_message(self, message: dict[str, Any]) -> bool:
                """Handle a Train Describer message.
                
                Returns:
                    True if message was handled as a TD message, False otherwise
                """
                # Log that we received a potential TD message
                self._hub.debug_logger.debug("Received potential TD message: %s", list(message.keys()))
                
                parsed = parse_td_message(message)
                if not parsed:
                    self._hub.debug_logger.debug("Message was not a valid TD message")
                    return False
                
                self._hub.debug_logger.debug(
                    "Parsed TD message: type=%s, area=%s", 
                    parsed.get("msg_type"), 
                    parsed.get("area_id")
                )
                
                options = _read_options()
                
                # Apply filters
                td_areas = set(options.get(CONF_TD_AREAS, []))
                area_filter = td_areas if td_areas else None
                
                self._hub.debug_logger.debug(
                    "TD filters: areas=%s (filter=%s)", 
                    td_areas if td_areas else "all", 
                    area_filter
                )
                
                if not apply_td_filters(parsed, area_filter=area_filter):
                    self._hub.debug_logger.debug(
                        "TD message filtered out: area=%s not in %s",
                        parsed.get("area_id"),
                        td_areas
                    )
                    # Still mark as handled since it was a valid TD message, just filtered
                    return True
                
                self._hub.debug_logger.info(
                    "Publishing TD message: type=%s, area=%s",
                    parsed.get("msg_type"),
                    parsed.get("area_id")
                )
                
                # Publish to HA
                self._publish_td_message(parsed)
                return True

            def _mark_seen(self, batch_count: int) -> None:
                hass_loop = self._hass.loop
                hass_loop.call_soon_threadsafe(self._update_seen, batch_count)

            def _set_connected(self, is_connected: bool) -> None:
                hass_loop = self._hass.loop
                hass_loop.call_soon_threadsafe(self._update_connected, is_connected)

            def _publish_last_movement(self, movement: dict[str, Any], kept: int, station_movements: dict[str, dict[str, Any]]) -> None:
                hass_loop = self._hass.loop
                hass_loop.call_soon_threadsafe(self._update_movement, movement, kept, station_movements)

            def _publish_td_message(self, parsed_message: dict[str, Any]) -> None:
                """Publish a Train Describer message to Home Assistant."""
                hass_loop = self._hass.loop
                hass_loop.call_soon_threadsafe(self._update_td_message, parsed_message)

            @callback
            def _update_connected(self, is_connected: bool) -> None:
                self._hub.state.connected = is_connected
                async_dispatcher_send(self._hass, DISPATCH_CONNECTED, is_connected)

            @callback
            def _update_seen(self, batch_count: int) -> None:
                self._hub.state.last_batch_count = batch_count
                self._hub.state.last_seen_monotonic = time.monotonic()

            @callback
            def _update_movement(self, movement: dict[str, Any], kept: int, station_movements: dict[str, dict[str, Any]]) -> None:
                self._hub.state.last_movement = movement
                self._hub.state.last_movement_per_station.update(station_movements)
                self._hub.state.last_batch_count = kept
                self._hub.state.last_seen_monotonic = time.monotonic()
                # Dispatch general movement event
                async_dispatcher_send(self._hass, DISPATCH_MOVEMENT)
                # Dispatch per-station movement events
                for stanox in station_movements:
                    async_dispatcher_send(self._hass, f"{DISPATCH_MOVEMENT}_{stanox}")

            @callback
            def _update_td_message(self, parsed_message: dict[str, Any]) -> None:
                """Update Train Describer state and dispatch events."""
                self._hub.state.last_td_message = parsed_message
                self._hub.state.td_message_count += 1
                
                # Update berth state
                msg_type = parsed_message.get("msg_type")
                if msg_type in ("CA", "CB", "CC"):
                    self._hub.state.berth_state.update(parsed_message)
                
                # Dispatch TD event
                async_dispatcher_send(self._hass, DISPATCH_TD, parsed_message)
                
                # Dispatch area-specific event
                area_id = parsed_message.get("area_id")
                if area_id:
                    async_dispatcher_send(self._hass, f"{DISPATCH_TD}_{area_id}", parsed_message)

        conn = None
        while not self._stop_evt.is_set():
            try:
                conn = stomp.Connection12(  # type: ignore
                    host_and_ports=[(NR_HOST, NR_PORT)],
                    heartbeats=(10000, 10000),
                    keepalive=True,
                )
                listener = _Listener(self, conn)
                conn.set_listener("", listener)

                self.debug_logger.info("Connecting to %s:%s ...", NR_HOST, NR_PORT)
                conn.connect(
                    username=username, 
                    passcode=password, 
                    wait=True,
                    headers={
                        "host": "datafeeds.networkrail.co.uk",                      # IMPORTANT
                        "client-id": username,            # recommended for durability
                    },
                )

                while not self._stop_evt.is_set() and conn.is_connected():
                    time.sleep(0.5)

            except Exception as exc:
                self.debug_logger.warning("STOMP connection error: %s", exc)
                self.state.connected = False
                self.state.last_error = str(exc)
                self.hass.loop.call_soon_threadsafe(
                    async_dispatcher_send, self.hass, DISPATCH_CONNECTED, False
                )

            finally:
                try:
                    if conn and conn.is_connected():
                        conn.disconnect()
                except Exception:
                    pass

            if self._stop_evt.is_set():
                break

            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)
