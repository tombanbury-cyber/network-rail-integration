"""Sensors for OpenRailData (Train Movements and Train Describer)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, 
    DISPATCH_MOVEMENT, 
    DISPATCH_TD,
    CONF_STATIONS, 
    CONF_STANOX_FILTER,
    CONF_ENABLE_TD,
    CONF_TD_AREAS,
    CONF_TD_EVENT_HISTORY_SIZE,
    CONF_TD_UPDATE_INTERVAL,
    CONF_DIAGRAM_CONFIGS,
    CONF_ENABLE_DEBUG_SENSOR,
    CONF_ENABLE_TD_RAW_JSON,
    DEFAULT_TD_EVENT_HISTORY_SIZE,
    DEFAULT_TD_UPDATE_INTERVAL,
)
from .toc_codes import get_toc_name, get_direction_description, get_line_description
from .stanox_utils import get_station_name, get_formatted_station_name, load_stanox_data
from .td_area_codes import format_td_area_title, get_td_area_name
from .debug_log import DebugLogSensor

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    # Preload STANOX data to avoid blocking I/O later
    await load_stanox_data()

    _LOGGER.info("=== async_setup_entry called for sensors ===")
    _LOGGER.info("Entry ID: %s", entry.entry_id)
    _LOGGER.info("Entry options: %s", entry.options)
    
    hub = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Get configured stations
    options = entry.options
    stations = options.get(CONF_STATIONS, [])
    stanox_filter = (options.get(CONF_STANOX_FILTER) or "").strip()
    
    # Create sensor for each configured station
    for station in stations:
        stanox = station.get("stanox", "")
        name = station.get("name", "Unknown")
        if stanox:
            entities.append(OpenRailDataStationSensor(hass, entry, hub, stanox, name))
    
    # Backward compatibility: if old stanox_filter is set, create a sensor for it
    if stanox_filter and not any(s.get("stanox") == stanox_filter for s in stations):
        entities.append(OpenRailDataStationSensor(hass, entry, hub, stanox_filter, f"Station {stanox_filter}"))
    
    # Always add the global last movement sensor for backward compatibility
    entities.append(OpenRailDataLastMovementSensor(hass, entry, hub))
    
    # Add Train Describer sensors if enabled
    if options.get(CONF_ENABLE_TD, False):
        # Initialize event history size in berth state
        event_history_size = options.get(CONF_TD_EVENT_HISTORY_SIZE, DEFAULT_TD_EVENT_HISTORY_SIZE)
        hub.state.berth_state.set_event_history_size(event_history_size)
        
        # Initialize platform mappings if SMART data is available
        smart_manager = hass.data[DOMAIN].get(f"{entry.entry_id}_smart_manager")
        if smart_manager and smart_manager.is_available():
            from .smart_utils import get_berth_to_platform_mapping
            graph = smart_manager.get_graph()
            
            # Build berth-to-platform mapping for configured TD areas
            td_areas = options.get(CONF_TD_AREAS, [])
            berth_platform_mapping = {}
            
            for area_id in td_areas:
                area_mapping = get_berth_to_platform_mapping(graph, area_id)
                # Convert to full berth keys (area:berth)
                for berth_id, platform_id in area_mapping.items():
                    berth_key = f"{area_id}:{berth_id}"
                    berth_platform_mapping[berth_key] = platform_id
            
            hub.state.berth_state.set_berth_to_platform_mapping(berth_platform_mapping)
        
        entities.append(TrainDescriberStatusSensor(hass, entry, hub))
        
        # Add raw JSON sensor if enabled
        if options.get(CONF_ENABLE_TD_RAW_JSON, True):  # Default to True for backward compatibility
            entities.append(TrainDescriberRawJsonSensor(hass, entry, hub))
        
        # Create sensors for specific TD areas if configured
        td_areas = options.get(CONF_TD_AREAS, [])
        for area_id in td_areas:
            entities.append(TrainDescriberAreaSensor(hass, entry, hub, area_id))
    
    # Add Network Diagram sensors for each configured diagram
    diagram_configs = options.get(CONF_DIAGRAM_CONFIGS, [])
    smart_manager = hass.data[DOMAIN].get(f"{entry.entry_id}_smart_manager")
    
    _LOGGER.info("Setting up Network Diagram sensors: %d diagrams configured", len(diagram_configs))
    
    if smart_manager:
        _LOGGER.info("Smart manager found: is_available=%s", smart_manager.is_available())
        for diagram_cfg in diagram_configs:
            enabled = diagram_cfg.get("enabled", False)
            diagram_stanox = diagram_cfg.get("stanox")
            diagram_range = diagram_cfg.get("range", 1)
            
            _LOGGER.info(
                "Processing diagram config: stanox=%s, enabled=%s, range=%d",
                diagram_stanox,
                enabled,
                diagram_range
            )
            
            if enabled and diagram_stanox:
                _LOGGER.info("Creating NetworkDiagramSensor for stanox=%s", diagram_stanox)
                entities.append(NetworkDiagramSensor(hass, entry, hub, smart_manager, diagram_stanox, diagram_range))
            else:
                _LOGGER.warning("Skipping diagram: stanox=%s, enabled=%s", diagram_stanox, enabled)
    else:
        _LOGGER.warning("Smart manager not found, skipping Network Diagram sensors")
    
    # Add Track Section sensors for each configured section
    from .const import CONF_TRACK_SECTIONS
    track_sections = options.get(CONF_TRACK_SECTIONS, [])
    vstp_manager = hass.data[DOMAIN].get(f"{entry.entry_id}_vstp_manager")
    if track_sections:
        for section in track_sections:
            section_name = section.get("name")
            if section_name:
                entities.append(TrackSectionSensor(hass, entry, hub, section, vstp_manager, smart_manager))
    
    # Add debug log sensor if enabled
    if options.get(CONF_ENABLE_DEBUG_SENSOR, True):  # Default to True for backward compatibility
        debug_sensor = DebugLogSensor(hass, entry)
        entities.append(debug_sensor)
        
        # Store debug sensor reference in hass.data for access by the hub
        hass.data[DOMAIN][f"{entry.entry_id}_debug_sensor"] = debug_sensor
    
    async_add_entities(entities, True)


def _should_throttle_update(last_update_time: float, throttle_seconds: float) -> bool:
    """Check if update should be throttled based on time since last update.
    
    Args:
        last_update_time: Timestamp of last update (monotonic time)
        throttle_seconds: Minimum seconds between updates
        
    Returns:
        True if update should be throttled, False if update should proceed
    """
    if last_update_time == 0:
        return False  # First update, don't throttle
    
    elapsed = time.monotonic() - last_update_time
    return elapsed < throttle_seconds


def _ms_to_local_iso(ms: Any) -> str | None:
    try:
        ms_i = int(ms)
    except Exception:
        return None
    dt_utc = datetime.fromtimestamp(ms_i / 1000.0, tz=timezone.utc)
    dt_local = dt_util.as_local(dt_utc)
    return dt_local.isoformat()


def _build_movement_attributes(header: dict[str, Any], body: dict[str, Any], extra_attrs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build common movement attributes from header and body data.
    
    Args:
        header: The message header
        body: The message body
        extra_attrs: Optional extra attributes to include (e.g., station_name, batch_count_seen)
        
    Returns:
        Dictionary of attributes
    """
    # Get raw values for decoding
    toc_id = body.get("toc_id")
    direction_ind = body.get("direction_ind")
    line_ind = body.get("line_ind")
    loc_stanox = body.get("loc_stanox")
    platform = body.get("platform")

    attrs: dict[str, Any] = {
        "msg_type": header.get("msg_type"),
        "source_dev_id": header.get("source_dev_id"),
        "original_data_source": header.get("original_data_source"),
        "msg_queue_timestamp": header.get("msg_queue_timestamp"),
        "msg_queue_time_local": _ms_to_local_iso(header.get("msg_queue_timestamp")),
        "train_id": body.get("train_id"),
        "toc_id": toc_id,
        "toc_name": get_toc_name(toc_id),
        "event_type": body.get("event_type"),
        "planned_timestamp": body.get("planned_timestamp"),
        "planned_time_local": _ms_to_local_iso(body.get("planned_timestamp")),
        "actual_timestamp": body.get("actual_timestamp"),
        "actual_time_local": _ms_to_local_iso(body.get("actual_timestamp")),
        "timetable_variation": body.get("timetable_variation"),
        "variation_status": body.get("variation_status"),
        "loc_stanox": loc_stanox,
        "location_name": get_station_name(loc_stanox),
        "platform": platform,
        "line_ind": line_ind,
        "line_description": get_line_description(line_ind),
        "direction_ind": direction_ind,
        "direction_description": get_direction_description(direction_ind),
        "corr_id": body.get("corr_id"),
        "event_source": body.get("event_source"),
        "train_terminated": body.get("train_terminated"),
        "offroute_ind": body.get("offroute_ind"),
        "raw": body,
    }
    
    # Add any extra attributes
    if extra_attrs:
        attrs.update(extra_attrs)
    
    return attrs


class OpenRailDataLastMovementSensor(SensorEntity):
    """Shows the last movement message seen (after optional filtering)."""

    _attr_has_entity_name = True
    _attr_name = "Last movement"
    _attr_icon = "mdi:train"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_MOVEMENT, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_last_movement"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Train Movements Feed",
        )

    @property
    def native_value(self) -> str | None:
        mv = self.hub.state.last_movement
        if not mv:
            return None
        body = mv.get("body") or {}
        return str(body.get("event_type") or body.get("movement_type") or "movement")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mv = self.hub.state.last_movement
        if not mv:
            return {}
        header = mv.get("header") or {}
        body = mv.get("body") or {}

        return _build_movement_attributes(
            header, 
            body, 
            extra_attrs={"batch_count_seen": self.hub.state.last_batch_count}
        )


class OpenRailDataStationSensor(SensorEntity):
    """Shows the last movement for a specific station."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:train"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub, stanox: str, station_name: str) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self._stanox = stanox
        self._station_name = station_name
        # Use formatted station name if available, otherwise use the provided name
        formatted_name = get_formatted_station_name(stanox)
        self._attr_name = formatted_name if formatted_name else station_name
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        # Subscribe to station-specific dispatcher signal
        self._unsub = async_dispatcher_connect(
            self.hass, 
            f"{DISPATCH_MOVEMENT}_{self._stanox}", 
            self._handle_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_station_{self._stanox}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Train Movements Feed",
        )

    @property
    def native_value(self) -> str | None:
        mv = self.hub.state.last_movement_per_station.get(self._stanox)
        if not mv:
            return None
        body = mv.get("body") or {}
        return str(body.get("event_type") or body.get("movement_type") or "movement")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mv = self.hub.state.last_movement_per_station.get(self._stanox)
        if not mv:
            return {"stanox": self._stanox, "station_name": self._station_name}
        header = mv.get("header") or {}
        body = mv.get("body") or {}

        return _build_movement_attributes(
            header, 
            body, 
            extra_attrs={
                "stanox": self._stanox,
                "station_name": self._station_name
            }
        )


class TrainDescriberStatusSensor(SensorEntity):
    """Sensor showing Train Describer feed status."""

    _attr_has_entity_name = True
    _attr_name = "Train Describer Status"
    _attr_icon = "mdi:train-car-passenger-door"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self._unsub = None
        self._last_update_time = 0.0  # Track last update for throttling

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_TD, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, parsed_message: dict[str, Any]) -> None:
        # Apply throttling based on configuration
        throttle_seconds = self.entry.options.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL)
        
        if _should_throttle_update(self._last_update_time, throttle_seconds):
            return  # Skip this update due to throttling
        
        self._last_update_time = time.monotonic()
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_td_status"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Train Describer Feed",
        )

    @property
    def native_value(self) -> str | None:
        msg = self.hub.state.last_td_message
        msg_count = self.hub.state.td_message_count
        if not msg:
            if msg_count == 0:
                return "Waiting for messages"
            return "No recent messages"
        
        msg_type = msg.get("msg_type", "Unknown")
        description = msg.get("description", "")
        time_ms = msg.get("time")
        
        # Format timestamp as HH:MM:SS
        time_str = ""
        if time_ms:
            time_iso = _ms_to_local_iso(time_ms)
            if time_iso:
                try:
                    # Extract time portion from ISO format more safely
                    # Expected format: 2024-12-22T14:32:15+00:00 or 2024-12-22T14:32:15-05:00
                    time_part = time_iso.split("T")[1]
                    # Split on + or - for timezone, take first part
                    for sep in ["+", "-"]:
                        if sep in time_part:
                            time_part = time_part.split(sep)[0]
                            break
                    time_str = time_part[:8]  # HH:MM:SS
                except (IndexError, ValueError):
                    # If parsing fails, omit timestamp rather than showing confusing placeholder
                    time_str = ""
        
        # Format message count with comma separators
        count_str = f"{msg_count:,}"
        
        # Build status message based on type
        if msg_type == "CA":
            from_berth = msg.get("from_berth", "").strip()
            to_berth = msg.get("to_berth", "").strip()
            train_desc = f"Train {description} " if description else ""
            # Handle empty berths
            if not from_berth or not to_berth:
                berth_info = f"berth {from_berth or to_berth or 'unknown'}"
            else:
                berth_info = f"from {from_berth} to {to_berth}"
            time_suffix = f" at {time_str}" if time_str else ""
            return f"CA - {train_desc}moved {berth_info}{time_suffix} ({count_str} messages)"
        elif msg_type == "CB":
            from_berth = msg.get("from_berth", "").strip()
            train_desc = f"Train {description} " if description else ""
            berth_info = f"from {from_berth}" if from_berth else "from unknown berth"
            time_suffix = f" at {time_str}" if time_str else ""
            return f"CB - {train_desc}cancelled {berth_info}{time_suffix} ({count_str} messages)"
        elif msg_type == "CC":
            to_berth = msg.get("to_berth", "").strip()
            train_desc = f"Train {description} " if description else ""
            berth_info = f"at {to_berth}" if to_berth else "at unknown berth"
            time_suffix = f" at {time_str}" if time_str else ""
            return f"CC - {train_desc}interposed {berth_info}{time_suffix} ({count_str} messages)"
        elif msg_type == "CT":
            time_suffix = f" at {time_str}" if time_str else ""
            return f"CT - Heartbeat{time_suffix} ({count_str} messages)"
        elif msg_type in ("SF", "SG", "SH"):
            time_suffix = f" at {time_str}" if time_str else ""
            return f"{msg_type} - Signal update{time_suffix} ({count_str} messages)"
        
        time_suffix = f" at {time_str}" if time_str else ""
        return f"{msg_type}{time_suffix} ({count_str} messages)"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        msg = self.hub.state.last_td_message
        if not msg:
            return {
                "message_count": self.hub.state.td_message_count,
                "berth_count": len(self.hub.state.berth_state.get_all_berths()),
            }
        
        attrs = {
            "msg_type": msg.get("msg_type"),
            "area_id": msg.get("area_id"),
            "time": msg.get("time"),
            "time_local": _ms_to_local_iso(msg.get("time")),
            "message_count": self.hub.state.td_message_count,
            "berth_count": len(self.hub.state.berth_state.get_all_berths()),
        }
        
        # Add type-specific attributes
        msg_type = msg.get("msg_type")
        if msg_type == "CA":
            attrs.update({
                "from_berth": msg.get("from_berth"),
                "to_berth": msg.get("to_berth"),
                "description": msg.get("description"),
            })
        elif msg_type == "CB":
            attrs.update({
                "from_berth": msg.get("from_berth"),
                "description": msg.get("description"),
            })
        elif msg_type == "CC":
            attrs.update({
                "to_berth": msg.get("to_berth"),
                "description": msg.get("description"),
            })
        elif msg_type == "CT":
            attrs.update({
                "report_time": msg.get("report_time"),
            })
        elif msg_type in ("SF", "SG", "SH"):
            attrs.update({
                "address": msg.get("address"),
                "data": msg.get("data"),
            })
        
        return attrs


class TrainDescriberAreaSensor(SensorEntity):
    """Sensor showing Train Describer data for a specific area."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:train-car-passenger-door"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub, area_id: str) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self._area_id = area_id
        # Use formatted TD area name with full descriptive title
        self._attr_name = format_td_area_title(area_id)
        self._unsub = None
        self._last_message: dict[str, Any] | None = None
        self._last_update_time = 0.0  # Track last update for throttling

    async def async_added_to_hass(self) -> None:
        # Subscribe to area-specific dispatcher signal
        self._unsub = async_dispatcher_connect(
            self.hass, 
            f"{DISPATCH_TD}_{self._area_id}", 
            self._handle_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, parsed_message: dict[str, Any]) -> None:
        # Apply throttling based on configuration
        throttle_seconds = self.entry.options.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL)
        
        if _should_throttle_update(self._last_update_time, throttle_seconds):
            # Still update the internal message but don't trigger HA state update
            self._last_message = parsed_message
            return
        
        self._last_message = parsed_message
        self._last_update_time = time.monotonic()
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_td_area_{self._area_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Train Describer Feed",
        )

    @property
    def native_value(self) -> str | None:
        if not self._last_message:
            return "Waiting for messages"
        msg_type = self._last_message.get("msg_type", "Unknown")
        return f"{msg_type}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        area_berths = self.hub.state.berth_state.get_area_berths(self._area_id)
        
        # Get platform states (all platforms, no filtering)
        platform_states = self.hub.state.berth_state.get_all_platform_states()
        
        # Get event history (all events, no filtering)
        event_history = self.hub.state.berth_state.get_event_history()
        
        # Get SMART data for station information if available
        smart_manager = self.hass.data.get(DOMAIN, {}).get(f"{self.entry.entry_id}_smart_manager")
        station_name = None
        station_code = None
        stations_in_area = []
        
        if smart_manager and smart_manager.is_available():
            # Try to find stations in this TD area from SMART data
            graph = smart_manager.get_graph()
            stanox_to_berths = graph.get("stanox_to_berths", {})
            
            # Find all unique stations in this TD area
            # Note: For large datasets, consider caching or indexing by TD area
            found_stations = set()
            for stanox, berth_records in stanox_to_berths.items():
                for record in berth_records:
                    if record.get("td_area") == self._area_id:
                        stanme = record.get("stanme", "").strip()
                        if stanme and stanox and stanox.strip():
                            found_stations.add((stanox, stanme))
            
            if found_stations:
                # Sort by STANOX and use the first station
                sorted_stations = sorted(found_stations)
                station_code, station_name = sorted_stations[0]
                
                # Store all stations for reference
                stations_in_area = [
                    {"stanox": stanox, "name": name} 
                    for stanox, name in sorted_stations
                ]
        
        # Fallback to TD area name if no SMART data or no stations found
        if not station_name:
            station_name = get_td_area_name(self._area_id) or f"TD Area {self._area_id}"
            station_code = self._area_id
        
        attrs = {
            "area_id": self._area_id,
            "station_name": station_name,
            "station_code": station_code,
            "berth_count": len(area_berths),
            "occupied_berths": {},
        }
        
        # Add list of stations if we found multiple
        if stations_in_area:
            attrs["stations_in_area"] = stations_in_area
        
        # Add platform states in the new format
        if platform_states:
            platforms_dict = {}
            for platform_id, state in platform_states.items():
                last_updated = state.get("last_updated")
                platforms_dict[platform_id] = {
                    "platform_id": state.get("platform_id"),
                    "current_train": state.get("current_train"),
                    "current_event": state.get("current_event"),
                    "last_updated": _ms_to_local_iso(last_updated) if last_updated else None,
                    "status": state.get("status", "idle"),
                }
            attrs["platforms"] = platforms_dict
        
        # Add recent events
        if event_history:
            recent_events = []
            for event in event_history:
                timestamp = event.get("timestamp")
                event_dict = {
                    "event_type": event.get("event_type"),
                    "train_id": event.get("train_id"),
                    "timestamp": _ms_to_local_iso(timestamp) if timestamp else None,
                    "area_id": event.get("area_id"),
                }
                
                # Add platform information
                if "platform" in event:
                    event_dict["platform"] = event["platform"]
                if "from_platform" in event:
                    event_dict["from_platform"] = event["from_platform"]
                if "to_platform" in event:
                    event_dict["to_platform"] = event["to_platform"]
                
                # Add berth information
                if "from_berth" in event:
                    event_dict["from_berth"] = event["from_berth"]
                if "to_berth" in event:
                    event_dict["to_berth"] = event["to_berth"]
                
                recent_events.append(event_dict)
            
            attrs["recent_events"] = recent_events
        
        # Add event history size
        attrs["event_history_size"] = self.hub.state.berth_state.get_event_history_size()
        
        # Add current berth occupancy (backward compatibility)
        for berth_id, state in area_berths.items():
            attrs["occupied_berths"][berth_id] = state.get("description", "")
        
        if self._last_message:
            attrs.update({
                "last_msg_type": self._last_message.get("msg_type"),
                "last_time": self._last_message.get("time"),
                "last_time_local": _ms_to_local_iso(self._last_message.get("time")),
            })
            
            # Add type-specific attributes
            msg_type = self._last_message.get("msg_type")
            if msg_type == "CA":
                attrs.update({
                    "last_from_berth": self._last_message.get("from_berth"),
                    "last_to_berth": self._last_message.get("to_berth"),
                    "last_description": self._last_message.get("description"),
                })
            elif msg_type == "CB":
                attrs.update({
                    "last_from_berth": self._last_message.get("from_berth"),
                    "last_description": self._last_message.get("description"),
                })
            elif msg_type == "CC":
                attrs.update({
                    "last_to_berth": self._last_message.get("to_berth"),
                    "last_description": self._last_message.get("description"),
                })
        
        return attrs


class TrainDescriberRawJsonSensor(SensorEntity):
    """Sensor showing raw JSON from Train Describer feed."""

    _attr_has_entity_name = True
    _attr_name = "Train Describer Raw JSON"
    _attr_icon = "mdi:code-json"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self._unsub = None
        self._last_update_time = 0.0  # Track last update for throttling

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_TD, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, parsed_message: dict[str, Any]) -> None:
        # Apply throttling based on configuration
        throttle_seconds = self.entry.options.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL)
        
        if _should_throttle_update(self._last_update_time, throttle_seconds):
            return  # Skip this update due to throttling
        
        self._last_update_time = time.monotonic()
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_td_raw_json"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Train Describer Feed",
        )

    @property
    def native_value(self) -> str | None:
        msg = self.hub.state.last_td_message
        if not msg:
            return "No messages"
        return f"{msg.get('msg_type', 'Unknown')} - {msg.get('area_id', 'Unknown')}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        msg = self.hub.state.last_td_message
        if not msg:
            return {
                "raw_json": None,
                "message_count": self.hub.state.td_message_count,
            }
        
        # Get the raw field from the parsed message
        raw = msg.get("raw", {})
        
        return {
            "raw_json": raw,
            "message_count": self.hub.state.td_message_count,
            "msg_type": msg.get("msg_type"),
            "area_id": msg.get("area_id"),
            "time": msg.get("time"),
            "time_local": _ms_to_local_iso(msg.get("time")),
        }


class NetworkDiagramSensor(SensorEntity):
    """Sensor showing network diagram with berth occupancy."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:map-marker-path"

    def __init__(
        self, 
        hass: HomeAssistant, 
        entry: ConfigEntry, 
        hub, 
        smart_manager,
        center_stanox: str,
        diagram_range: int = 1
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self.smart_manager = smart_manager
        self._center_stanox = center_stanox
        self._diagram_range = diagram_range
        # Use formatted station name if available, otherwise use STANOX code
        formatted_name = get_formatted_station_name(center_stanox)
        if formatted_name:
            self._attr_name = f"Network Diagram for {formatted_name} ({center_stanox})"
        else:
            self._attr_name = f"Network Diagram {center_stanox}"
        self._unsub = None
        self._last_update_time = 0.0  # Track last update for throttling
        
        _LOGGER.info(
            "NetworkDiagramSensor created: stanox=%s, name=%s, range=%d",
            center_stanox,
            self._attr_name,
            diagram_range
        )

    async def async_added_to_hass(self) -> None:
        _LOGGER.info("NetworkDiagramSensor async_added_to_hass: stanox=%s", self._center_stanox)
        # Subscribe to TD messages for berth updates
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_TD, self._handle_update)
        _LOGGER.info("NetworkDiagramSensor subscribed to TD updates: stanox=%s", self._center_stanox)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, parsed_message: dict[str, Any]) -> None:
        """Handle TD message update with throttling."""
        _LOGGER.debug("NetworkDiagramSensor _handle_update called: stanox=%s", self._center_stanox)
        
        # Apply throttling based on configuration
        throttle_seconds = self.entry.options.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL)
        
        if _should_throttle_update(self._last_update_time, throttle_seconds):
            return  # Skip this update due to throttling
        
        self._last_update_time = time.monotonic()
        _LOGGER.debug("NetworkDiagramSensor triggering state update: stanox=%s", self._center_stanox)
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_diagram_{self._center_stanox}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Network Diagram",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        smart_available = self.smart_manager.is_available()
        hub_connected = self.hub.is_connected
        
        _LOGGER.debug(
            "NetworkDiagramSensor availability check: smart_manager.is_available()=%s, hub.is_connected=%s",
            smart_available,
            hub_connected
        )
        
        return smart_available and hub_connected

    @property
    def native_value(self) -> int:
        """Return the count of currently occupied berths in the diagram area."""
        if not self.smart_manager.is_available():
            _LOGGER.debug("NetworkDiagramSensor native_value: SMART manager not available")
            return 0
        
        # Get all berths in the diagram area
        graph = self.smart_manager.get_graph()
        berth_state = self.hub.state.berth_state
        
        # Get berths for center station and adjacent stations
        all_berths = self._get_all_diagram_berths(graph)
        
        _LOGGER.debug(
            "NetworkDiagramSensor native_value: Found %d berths in diagram area for STANOX %s",
            len(all_berths),
            self._center_stanox
        )
        
        # Count occupied berths
        occupied_count = 0
        for berth_key in all_berths:
            parts = berth_key.split(":", 1)
            if len(parts) == 2:
                td_area, berth_id = parts
                berth_data = berth_state.get_berth(td_area, berth_id)
                if berth_data:
                    occupied_count += 1
        
        _LOGGER.debug("NetworkDiagramSensor native_value: %d occupied berths", occupied_count)
        return occupied_count

    def _get_all_diagram_berths(self, graph: dict[str, Any]) -> set[str]:
        """Get all berth keys in the diagram area."""
        from .smart_utils import get_berths_for_stanox
        
        all_berths = set()
        
        # Get berths for center station
        center_berths = get_berths_for_stanox(graph, self._center_stanox)
        for berth_info in center_berths:
            td_area = berth_info.get("td_area", "")
            from_berth = berth_info.get("from_berth", "")
            to_berth = berth_info.get("to_berth", "")
            if from_berth and td_area:
                all_berths.add(f"{td_area}:{from_berth}")
            if to_berth and td_area:
                all_berths.add(f"{td_area}:{to_berth}")
        
        # Get berths for adjacent stations (based on diagram_range)
        # For now, we'll get immediately adjacent stations
        # In a more sophisticated implementation, this would expand based on diagram_range
        from .smart_utils import get_station_berths_with_connections
        
        station_data = get_station_berths_with_connections(graph, self._center_stanox)
        
        # Add berths from up connections
        for conn in station_data.get("up_connections", [])[:self._diagram_range]:
            conn_stanox = conn.get("stanox")
            if conn_stanox:
                conn_berths = get_berths_for_stanox(graph, conn_stanox)
                for berth_info in conn_berths:
                    td_area = berth_info.get("td_area", "")
                    from_berth = berth_info.get("from_berth", "")
                    to_berth = berth_info.get("to_berth", "")
                    if from_berth and td_area:
                        all_berths.add(f"{td_area}:{from_berth}")
                    if to_berth and td_area:
                        all_berths.add(f"{td_area}:{to_berth}")
        
        # Add berths from down connections
        for conn in station_data.get("down_connections", [])[:self._diagram_range]:
            conn_stanox = conn.get("stanox")
            if conn_stanox:
                conn_berths = get_berths_for_stanox(graph, conn_stanox)
                for berth_info in conn_berths:
                    td_area = berth_info.get("td_area", "")
                    from_berth = berth_info.get("from_berth", "")
                    to_berth = berth_info.get("to_berth", "")
                    if from_berth and td_area:
                        all_berths.add(f"{td_area}:{from_berth}")
                    if to_berth and td_area:
                        all_berths.add(f"{td_area}:{to_berth}")
        
        return all_berths

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed diagram attributes."""
        if not self.smart_manager.is_available():
            return {
                "smart_data_available": False,
                "smart_data_last_updated": None,
                "center_stanox": self._center_stanox,
            }
        
        graph = self.smart_manager.get_graph()
        berth_state = self.hub.state.berth_state
        
        from .smart_utils import get_berths_for_stanox, get_station_berths_with_connections
        
        # Get station data with connections
        station_data = get_station_berths_with_connections(graph, self._center_stanox)
        
        # Build center berths with occupancy
        center_berths = []
        for berth_info in station_data.get("berths", []):
            berth_id = berth_info.get("berth_id", "")
            td_area = berth_info.get("td_area", "")
            
            # Get occupancy from live TD data
            occupied = False
            headcode = None
            if td_area and berth_id:
                berth_data = berth_state.get_berth(td_area, berth_id)
                if berth_data:
                    occupied = True
                    headcode = berth_data.get("description")
            
            center_berths.append({
                "berth_id": berth_id,
                "td_area": td_area,
                "platform": berth_info.get("platform", ""),
                "occupied": occupied,
                "headcode": headcode,
            })
        
        # Build up stations with occupancy
        up_stations = self._build_station_berths_with_occupancy(
            station_data.get("up_connections", []),
            graph
        )
        
        # Build down stations with occupancy
        down_stations = self._build_station_berths_with_occupancy(
            station_data.get("down_connections", []),
            graph
        )
        
        last_updated = self.smart_manager.get_last_updated()
        
        return {
            "center_stanox": self._center_stanox,
            "center_name": station_data.get("stanme", ""),
            "center_berths": center_berths,
            "up_stations": up_stations,
            "down_stations": down_stations,
            "smart_data_available": True,
            "smart_data_last_updated": last_updated.isoformat() if last_updated else None,
            "diagram_range": self._diagram_range,
        }


class TrackSectionSensor(SensorEntity):
    """Sensor that monitors trains along a defined track section."""
    
    _attr_has_entity_name = True
    _attr_icon = "mdi:train-car-container"
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        hub,
        section_config: dict[str, Any],
        vstp_manager,
        smart_manager,
    ) -> None:
        """Initialize the track section sensor."""
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self.vstp_manager = vstp_manager
        self.smart_manager = smart_manager
        
        # Section configuration
        self._section_name = section_config.get("name", "Unknown")
        self._center_stanox = section_config.get("center_stanox", "")
        self._berth_range = section_config.get("berth_range", 3)
        self._td_areas = section_config.get("td_areas", [])
        self._alert_services = section_config.get("alert_services", {})
        
        # Train tracking
        self._trains_in_section: dict[str, dict[str, Any]] = {}
        
        # Section berths (calculated from SMART data)
        self._section_berths: set[str] = set()
        self._calculate_section_berths()
        
        self._unsub_td = None
        self._unsub_vstp = None
    
    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self.entry.entry_id}_track_section_{self._section_name.lower().replace(' ', '_')}"
    
    @property
    def name(self) -> str:
        """Return sensor name."""
        return f"Track Section {self._section_name}"
    
    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return len(self._trains_in_section)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return sensor attributes."""
        trains_list = []
        alert_count = 0
        
        for train_id, train_data in self._trains_in_section.items():
            train_info = {
                "train_id": train_id,
                "headcode": train_data.get("headcode", train_id),
                "current_berth": train_data.get("current_berth"),
                "current_platform": train_data.get("current_platform"),
                "direction": train_data.get("direction"),
                "entered_section_at": train_data.get("entered_at"),
                "time_in_section_seconds": self._calculate_time_in_section(train_data),
                "berths_visited": train_data.get("berths_visited", []),
                "berths_ahead": self._calculate_berths_ahead(train_data),
            }
            
            # Add VSTP data if available
            vstp_data = train_data.get("vstp_data")
            if vstp_data:
                train_info.update({
                    "service_type": train_data.get("service_type"),
                    "category": vstp_data.get("CIF_train_category"),
                    "origin": train_data.get("origin"),
                    "destination": train_data.get("destination"),
                    "operator": train_data.get("operator"),
                    "power_type": vstp_data.get("CIF_power_type"),
                    "train_class": vstp_data.get("train_class"),
                    "next_scheduled_stop": train_data.get("next_stop"),
                    "scheduled_arrival": train_data.get("scheduled_arrival"),
                    "scheduled_platform": train_data.get("scheduled_platform"),
                    "running_status": train_data.get("running_status", "unknown"),
                })
            
            # Add alert information
            if train_data.get("triggers_alert", False):
                alert_count += 1
                train_info["triggers_alert"] = True
                train_info["alert_reason"] = train_data.get("alert_reason")
            else:
                train_info["triggers_alert"] = False
                train_info["alert_reason"] = None
            
            trains_list.append(train_info)
        
        return {
            "trains_in_section": trains_list,
            "section_config": {
                "name": self._section_name,
                "center_stanox": self._center_stanox,
                "berth_range": self._berth_range,
                "td_areas": self._td_areas,
            },
            "section_berths": list(self._section_berths),
            "total_trains": len(self._trains_in_section),
            "alert_trains": alert_count,
        }
    
    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Track Section Monitor",
        )
    
    async def async_added_to_hass(self) -> None:
        """Subscribe to TD and VSTP events."""
        from .const import DISPATCH_TD, DISPATCH_VSTP
        
        # Subscribe to TD events
        self._unsub_td = async_dispatcher_connect(
            self.hass, DISPATCH_TD, self._handle_td_message
        )
        
        # Subscribe to VSTP events if manager is available
        if self.vstp_manager:
            self._unsub_vstp = async_dispatcher_connect(
                self.hass, DISPATCH_VSTP, self._handle_vstp_message
            )
    
    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from events."""
        if self._unsub_td:
            self._unsub_td()
        if self._unsub_vstp:
            self._unsub_vstp()
    
    def _calculate_section_berths(self) -> None:
        """Calculate which berths are in this section using SMART data."""
        if not self.smart_manager or not self.smart_manager.is_available():
            return
        
        from .smart_utils import get_berths_for_stanox
        
        graph = self.smart_manager.get_graph()
        
        # Get berths at center station
        center_berths = get_berths_for_stanox(graph, self._center_stanox)
        
        # Add center berths to section
        for berth_info in center_berths:
            td_area = berth_info.get("td_area", "")
            from_berth = berth_info.get("from_berth", "")
            to_berth = berth_info.get("to_berth", "")
            
            if from_berth:
                self._section_berths.add(f"{td_area}:{from_berth}")
            if to_berth:
                self._section_berths.add(f"{td_area}:{to_berth}")
        
        # If no SMART data available or no TD areas configured, use TD areas from config
        if not self._section_berths and self._td_areas:
            # This is a fallback - we'll just monitor all berths in configured areas
            pass
    
    @callback
    def _handle_td_message(self, td_message: dict[str, Any]) -> None:
        """Handle TD message and update train positions."""
        msg_type = td_message.get("msg_type")
        area_id = td_message.get("area_id")
        
        # Check if this message is for our monitored areas
        if self._td_areas and area_id not in self._td_areas:
            return
        
        # Handle berth step (CA) - train moved from one berth to another
        if msg_type == "CA":
            from_berth = td_message.get("from")
            to_berth = td_message.get("to")
            headcode = td_message.get("descr")
            
            if not headcode:
                return
            
            from_berth_key = f"{area_id}:{from_berth}" if from_berth else None
            to_berth_key = f"{area_id}:{to_berth}" if to_berth else None
            
            # Check if train is entering, leaving, or moving within section
            from_in_section = from_berth_key in self._section_berths if from_berth_key else False
            to_in_section = to_berth_key in self._section_berths if to_berth_key else False
            
            if to_in_section and not from_in_section:
                # Train entering section
                self._train_entered_section(to_berth_key, headcode, td_message)
            elif from_in_section and not to_in_section:
                # Train leaving section
                self._train_left_section(headcode)
            elif from_in_section and to_in_section:
                # Train moving within section
                self._train_moved_in_section(from_berth_key, to_berth_key, headcode, td_message)
        
        # Handle berth cancel (CB) - train disappeared from berth
        elif msg_type == "CB":
            from_berth = td_message.get("from")
            headcode = td_message.get("descr")
            
            if headcode and from_berth:
                from_berth_key = f"{area_id}:{from_berth}"
                if from_berth_key in self._section_berths:
                    # Train cancelled in section - remove it
                    self._train_left_section(headcode)
        
        # Handle berth interpose (CC) - train appeared in berth
        elif msg_type == "CC":
            to_berth = td_message.get("to")
            headcode = td_message.get("descr")
            
            if headcode and to_berth:
                to_berth_key = f"{area_id}:{to_berth}"
                if to_berth_key in self._section_berths:
                    # Train interposed in section
                    self._train_entered_section(to_berth_key, headcode, td_message)
        
        # Trigger update
        self.async_write_ha_state()
    
    @callback
    def _handle_vstp_message(self, vstp_message: dict[str, Any]) -> None:
        """Handle VSTP message and enrich train data."""
        # VSTP messages are processed by vstp_manager
        # We'll query it when we need schedule data
        pass
    
    def _train_entered_section(self, berth: str, headcode: str, td_message: dict[str, Any]) -> None:
        """Handle train entering the section."""
        now = dt_util.now()
        
        # Get VSTP data if available
        vstp_data = None
        service_classification = None
        if self.vstp_manager:
            vstp_data = self.vstp_manager.get_schedule_for_headcode(headcode)
            
            if vstp_data:
                # Classify the service
                from .service_classifier import classify_service
                service_classification = classify_service(vstp_data, headcode)
        
        # Create train data
        train_data = {
            "headcode": headcode,
            "current_berth": berth,
            "entered_at": now.isoformat(),
            "berths_visited": [berth],
            "td_message": td_message,
        }
        
        # Add VSTP enrichment if available
        if vstp_data and service_classification:
            origin, destination = self.vstp_manager.get_origin_destination(vstp_data) if self.vstp_manager else (None, None)
            
            train_data.update({
                "vstp_data": vstp_data,
                "service_type": service_classification.get("service_type"),
                "service_category": service_classification.get("service_category"),
                "description": service_classification.get("description"),
                "origin": origin,
                "destination": destination,
                "is_freight": service_classification.get("is_freight", False),
                "is_passenger": service_classification.get("is_passenger", False),
                "is_special": service_classification.get("is_special", False),
                "special_types": service_classification.get("special_types", []),
            })
            
            # Check if this should trigger an alert
            from .service_classifier import should_alert_for_service
            should_alert, alert_reason = should_alert_for_service(service_classification, self._alert_services)
            train_data["triggers_alert"] = should_alert
            train_data["alert_reason"] = alert_reason
            
            # Fire alert event if needed
            if should_alert:
                self._fire_track_alert(headcode, train_data, alert_reason)
        
        # Store train data
        self._trains_in_section[headcode] = train_data
    
    def _train_left_section(self, headcode: str) -> None:
        """Handle train leaving the section."""
        if headcode in self._trains_in_section:
            del self._trains_in_section[headcode]
    
    def _train_moved_in_section(
        self, 
        from_berth: str, 
        to_berth: str, 
        headcode: str,
        td_message: dict[str, Any]
    ) -> None:
        """Handle train moving within the section."""
        if headcode in self._trains_in_section:
            train_data = self._trains_in_section[headcode]
            train_data["current_berth"] = to_berth
            train_data["berths_visited"].append(to_berth)
            train_data["td_message"] = td_message
        else:
            # Train wasn't tracked - add it now
            self._train_entered_section(to_berth, headcode, td_message)
    
    def _calculate_time_in_section(self, train_data: dict[str, Any]) -> int:
        """Calculate how long train has been in section (seconds)."""
        entered_at_str = train_data.get("entered_at")
        if not entered_at_str:
            return 0
        
        try:
            entered_at = datetime.fromisoformat(entered_at_str)
            now = dt_util.now()
            delta = now - entered_at
            return int(delta.total_seconds())
        except Exception:
            return 0
    
    def _calculate_berths_ahead(self, train_data: dict[str, Any]) -> list[str]:
        """Calculate berths ahead of train in section.
        
        TODO: Implement this using SMART data to find berths ahead in the direction of travel.
        For now, returns empty list as this is an enhancement for future releases.
        """
        current_berth = train_data.get("current_berth")
        if not current_berth or not self.smart_manager or not self.smart_manager.is_available():
            return []
        
        # Future implementation: Use SMART data to traverse berth connections
        # and find berths ahead based on direction of travel
        return []
    
    def _fire_track_alert(self, headcode: str, train_data: dict[str, Any], alert_reason: str) -> None:
        """Fire a Home Assistant event for track section alert."""
        event_data = {
            "section_name": self._section_name,
            "train_id": headcode,
            "headcode": headcode,
            "alert_type": train_data.get("service_type", "unknown"),
            "alert_reason": alert_reason,
            "current_berth": train_data.get("current_berth"),
            "service_type": train_data.get("service_type"),
            "origin": train_data.get("origin"),
            "destination": train_data.get("destination"),
            "operator": train_data.get("operator"),
            "entered_at": train_data.get("entered_at"),
        }
        
        self.hass.bus.async_fire("homeassistant_network_rail_uk_track_alert", event_data)
