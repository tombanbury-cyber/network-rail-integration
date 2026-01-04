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
    CONF_ENABLE_VSTP,
    CONF_EVENT_TYPES,
    CONF_PASSWORD,
    CONF_STANOX_FILTER,
    CONF_STATIONS,
    CONF_TD_AREAS,
    CONF_TD_EVENT_HISTORY_SIZE,
    CONF_TD_MAX_BATCH_SIZE,
    CONF_TD_MAX_MESSAGES_PER_SECOND,
    CONF_TD_UPDATE_INTERVAL,
    CONF_TOC_FILTER,
    CONF_TOPIC,
    CONF_USERNAME,
    DEFAULT_TD_EVENT_HISTORY_SIZE,
    DEFAULT_TD_MAX_BATCH_SIZE,
    DEFAULT_TD_MAX_MESSAGES_PER_SECOND,
    DEFAULT_TD_UPDATE_INTERVAL,
    DEFAULT_TD_TOPIC,
    DEFAULT_TOPIC,
    DEFAULT_VSTP_TOPIC,
    DISPATCH_CONNECTED,
    DISPATCH_MOVEMENT,
    DISPATCH_TD,
    DISPATCH_VSTP,
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
    td_message_count: int = 0
    # TD rate limiting state
    td_batch: list[dict[str, Any]] = field(default_factory=list)
    td_last_dispatch_time: float = 0.0
    td_message_rate_window: list[float] = field(default_factory=list)
    td_dropped_count: int = 0
    
    def __post_init__(self):
        """Initialize berth state with default history size."""
        # Create berth_state as an instance attribute after dataclass initialization
        self.berth_state = BerthState(event_history_size=DEFAULT_TD_EVENT_HISTORY_SIZE)


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

    @property
    def is_connected(self) -> bool:
        """Return if hub is connected to STOMP broker."""
        return self.state.connected
    
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
                CONF_TD_EVENT_HISTORY_SIZE: opt.get(CONF_TD_EVENT_HISTORY_SIZE, DEFAULT_TD_EVENT_HISTORY_SIZE),
                CONF_TD_UPDATE_INTERVAL: opt.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL),
                CONF_TD_MAX_BATCH_SIZE: opt.get(CONF_TD_MAX_BATCH_SIZE, DEFAULT_TD_MAX_BATCH_SIZE),
                CONF_TD_MAX_MESSAGES_PER_SECOND: opt.get(CONF_TD_MAX_MESSAGES_PER_SECOND, DEFAULT_TD_MAX_MESSAGES_PER_SECOND),
                CONF_ENABLE_VSTP: opt.get(CONF_ENABLE_VSTP, False),
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
                    
                    # Subscribe to VSTP if enabled
                    if options.get(CONF_ENABLE_VSTP, False):
                        vstp_dest = f"/topic/{DEFAULT_VSTP_TOPIC}"
                        self._hub.debug_logger.info(
                            "Subscribing to VSTP feed: %s", 
                            vstp_dest
                        )
                        self._conn_ref.subscribe(
                            destination=vstp_dest,
                            id=3,
                            ack="auto",
                            headers={
                                "activemq.subscriptionName": f"network_rail_integration-{DEFAULT_VSTP_TOPIC}",
                            },
                        )
                        self._hub.debug_logger.info("Successfully subscribed to VSTP feed")
                    else:
                        self._hub.debug_logger.debug("VSTP feed is disabled")
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
                    self._hub.debug_logger.debug("Received dict payload, checking message type")
                    
                    # Try to handle as VSTP message first (has JsonScheduleV1 key)
                    if self._handle_vstp_message(payload):
                        # Successfully handled as VSTP message
                        return
                    
                    # Try to handle as TD message
                    if self._handle_td_message(payload):
                        # Successfully handled as TD message
                        return
                    # Not a valid TD or VSTP message, continue to process as other message type
                    self._hub.debug_logger.debug("Dict payload was not a TD or VSTP message, continuing processing")

                # Feed is a JSON list (may be empty) for train movements
                if not isinstance(payload, list) or not payload:
                    self._mark_seen(0)
                    return

                # Check if list contains TD messages (dicts with *_MSG keys)
                # TD messages arrive in list format like train movements
                if len(payload) > 0 and isinstance(payload[0], dict):
                    # Check if first item looks like a TD message
                    first_item = payload[0]
                    has_td_msg_key = any(key.endswith("_MSG") for key in first_item.keys())
                    
                    if has_td_msg_key:
                        self._hub.debug_logger.debug("Received list with TD messages, processing %d items", len(payload))
                        # Process each TD message in the list
                        # _handle_td_message will validate each message is actually a TD message
                        td_count = 0
                        for item in payload:
                            if isinstance(item, dict) and self._handle_td_message(item):
                                td_count += 1
                        
                        # If we processed any TD messages, mark as seen and return
                        if td_count > 0:
                            self._hub.debug_logger.debug("Processed %d TD messages from list", td_count)
                            self._mark_seen(td_count)
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

            def _handle_vstp_message(self, message: dict[str, Any]) -> bool:
                """Handle a VSTP schedule message.
                
                Returns:
                    True if message was successfully handled as a VSTP message,
                    False if the message is not a valid VSTP message format
                """
                # Check for JsonScheduleV1 key (VSTP message indicator)
                if "JsonScheduleV1" not in message:
                    return False
                
                self._hub.debug_logger.debug("Received VSTP schedule message")
                
                # Get VSTP manager from hass data
                from .const import DOMAIN
                vstp_manager = self._hass.data[DOMAIN].get(f"{self._hub.entry.entry_id}_vstp_manager")
                
                if vstp_manager:
                    try:
                        vstp_manager.process_vstp_message(message)
                        self._hub.debug_logger.debug("VSTP message processed successfully")
                        
                        # Dispatch VSTP event for track section sensors
                        self._publish_vstp_message(message)
                    except Exception as exc:
                        self._hub.debug_logger.error("Error processing VSTP message: %s", exc)
                else:
                    self._hub.debug_logger.warning("VSTP manager not found, message discarded")
                
                return True

            def _handle_td_message(self, message: dict[str, Any]) -> bool:
                """Handle a Train Describer message with rate limiting and batching.
                
                Returns:
                    True if message was successfully handled as a TD message (including 
                    filtered messages), False if the message is not a valid TD message format
                """
                options = _read_options()
                
                # Early filtering: Check area filter BEFORE parsing to save CPU
                td_areas = set(options.get(CONF_TD_AREAS, []))
                if td_areas:
                    # Quick check: does message contain any of our area IDs?
                    # TD messages have keys like "CA_MSG", "CB_MSG", etc.
                    has_area_match = False
                    for key, content in message.items():
                        if key.endswith("_MSG") and isinstance(content, dict):
                            area_id = content.get("area_id", "")
                            if area_id in td_areas:
                                has_area_match = True
                                break
                    
                    if not has_area_match:
                        # Message is for an area we're not tracking, skip parsing
                        self._hub.debug_logger.debug("TD message filtered early: area not in filter")
                        return True  # Still counts as handled TD message
                
                # Parse the message
                parsed = parse_td_message(message)
                if not parsed:
                    self._hub.debug_logger.debug("Message was not a valid TD message")
                    return False
                
                self._hub.debug_logger.debug(
                    "Parsed TD message: type=%s, area=%s", 
                    parsed.get("msg_type"), 
                    parsed.get("area_id")
                )
                
                # Apply remaining filters (in case early filter missed something)
                area_filter = td_areas if td_areas else None
                if not apply_td_filters(parsed, area_filter=area_filter):
                    self._hub.debug_logger.debug(
                        "TD message filtered out: area=%s not in %s",
                        parsed.get("area_id"),
                        td_areas
                    )
                    return True
                
                # Rate limiting: check message rate
                max_msg_per_sec = options.get(CONF_TD_MAX_MESSAGES_PER_SECOND, DEFAULT_TD_MAX_MESSAGES_PER_SECOND)
                now = time.monotonic()
                
                # Clean old timestamps from rate window (keep last 1 second)
                self._hub.state.td_message_rate_window = [
                    t for t in self._hub.state.td_message_rate_window if now - t < 1.0
                ]
                
                # Check if we're over the rate limit
                if len(self._hub.state.td_message_rate_window) >= max_msg_per_sec:
                    self._hub.state.td_dropped_count += 1
                    if self._hub.state.td_dropped_count % 100 == 1:  # Log every 100 drops
                        self._hub.debug_logger.warning(
                            "TD rate limit exceeded (%d msg/s): dropped %d messages",
                            max_msg_per_sec,
                            self._hub.state.td_dropped_count
                        )
                    return True
                
                # Add to rate window
                self._hub.state.td_message_rate_window.append(now)
                
                # Add to batch
                self._hub.state.td_batch.append(parsed)
                
                # Check if batch is full or if enough time has passed
                max_batch_size = options.get(CONF_TD_MAX_BATCH_SIZE, DEFAULT_TD_MAX_BATCH_SIZE)
                update_interval = options.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL)
                time_since_last = now - self._hub.state.td_last_dispatch_time
                
                should_dispatch = (
                    len(self._hub.state.td_batch) >= max_batch_size or
                    time_since_last >= update_interval
                )
                
                if should_dispatch and self._hub.state.td_batch:
                    self._hub.debug_logger.debug(
                        "Dispatching TD batch: %d messages (batch_full=%s, time_elapsed=%.1fs)",
                        len(self._hub.state.td_batch),
                        len(self._hub.state.td_batch) >= max_batch_size,
                        time_since_last
                    )
                    # Dispatch the batch
                    batch_to_send = self._hub.state.td_batch.copy()
                    self._hub.state.td_batch.clear()
                    self._hub.state.td_last_dispatch_time = now
                    self._publish_td_batch(batch_to_send)
                
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
                """Publish a single Train Describer message to Home Assistant (legacy)."""
                hass_loop = self._hass.loop
                hass_loop.call_soon_threadsafe(self._update_td_message, parsed_message)
            
            def _publish_td_batch(self, batch: list[dict[str, Any]]) -> None:
                """Publish a batch of Train Describer messages to Home Assistant."""
                hass_loop = self._hass.loop
                hass_loop.call_soon_threadsafe(self._update_td_batch, batch)

            def _publish_vstp_message(self, message: dict[str, Any]) -> None:
                """Publish a VSTP message to Home Assistant."""
                hass_loop = self._hass.loop
                hass_loop.call_soon_threadsafe(self._update_vstp_message, message)

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
                """Update Train Describer state and dispatch events (legacy single message)."""
                self._update_td_batch([parsed_message])
            
            @callback
            def _update_td_batch(self, batch: list[dict[str, Any]]) -> None:
                """Update Train Describer state and dispatch events for a batch of messages."""
                if not batch:
                    return
                
                # Process all messages in batch
                for parsed_message in batch:
                    self._hub.state.last_td_message = parsed_message
                    self._hub.state.td_message_count += 1
                    
                    # Update berth state
                    msg_type = parsed_message.get("msg_type")
                    if msg_type in ("CA", "CB", "CC"):
                        self._hub.state.berth_state.update(parsed_message)
                
                # Only dispatch once per batch (use last message as representative)
                last_message = batch[-1]
                
                # Dispatch TD event (throttled - only once per batch)
                async_dispatcher_send(self._hass, DISPATCH_TD, last_message)
                
                # Dispatch area-specific events (collect unique areas, dispatch once per area)
                area_messages = {}
                for parsed_message in batch:
                    area_id = parsed_message.get("area_id")
                    if area_id:
                        # Keep the latest message for each area
                        area_messages[area_id] = parsed_message
                
                # Dispatch once per unique area
                for area_id, message in area_messages.items():
                    async_dispatcher_send(self._hass, f"{DISPATCH_TD}_{area_id}", message)

            @callback
            def _update_vstp_message(self, message: dict[str, Any]) -> None:
                """Update VSTP state and dispatch events."""
                # Dispatch VSTP event for any listeners (e.g., track section sensors)
                async_dispatcher_send(self._hass, DISPATCH_VSTP, message)

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
