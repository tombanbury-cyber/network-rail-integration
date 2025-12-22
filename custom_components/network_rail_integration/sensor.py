"""Sensors for OpenRailData (Train Movements and Train Describer)."""

from __future__ import annotations

from datetime import datetime, timezone
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
    CONF_TD_PLATFORMS,
    CONF_TD_EVENT_HISTORY_SIZE,
    CONF_DIAGRAM_ENABLED,
    CONF_DIAGRAM_STANOX,
    CONF_DIAGRAM_RANGE,
    DEFAULT_TD_EVENT_HISTORY_SIZE,
)
from .toc_codes import get_toc_name, get_direction_description, get_line_description
from .stanox_utils import get_station_name, get_formatted_station_name
from .td_area_codes import format_td_area_title
from .debug_log import DebugLogSensor


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
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
            
            # Initialize platform states for configured platforms
            td_platforms_config = options.get(CONF_TD_PLATFORMS, {})
            for area_id, platform_list in td_platforms_config.items():
                hub.state.berth_state.initialize_platform_states(platform_list)
        
        entities.append(TrainDescriberStatusSensor(hass, entry, hub))
        entities.append(TrainDescriberRawJsonSensor(hass, entry, hub))
        
        # Create sensors for specific TD areas if configured
        td_areas = options.get(CONF_TD_AREAS, [])
        for area_id in td_areas:
            entities.append(TrainDescriberAreaSensor(hass, entry, hub, area_id))
    
    # Add Network Diagram sensor if enabled
    if options.get(CONF_DIAGRAM_ENABLED, False):
        diagram_stanox = options.get(CONF_DIAGRAM_STANOX)
        diagram_range = options.get(CONF_DIAGRAM_RANGE, 1)
        if diagram_stanox:
            smart_manager = hass.data[DOMAIN].get(f"{entry.entry_id}_smart_manager")
            if smart_manager:
                entities.append(NetworkDiagramSensor(hass, entry, hub, smart_manager, diagram_stanox, diagram_range))
    
    # Add debug log sensor
    debug_sensor = DebugLogSensor(hass, entry)
    entities.append(debug_sensor)
    
    # Store debug sensor reference in hass.data for access by the hub
    hass.data[DOMAIN][f"{entry.entry_id}_debug_sensor"] = debug_sensor
    
    async_add_entities(entities, True)


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

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_TD, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, parsed_message: dict[str, Any]) -> None:
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
        self._last_message = parsed_message
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
        
        # Get configured platforms for this area
        options = self.entry.options
        td_platforms_config = options.get(CONF_TD_PLATFORMS, {})
        selected_platforms = td_platforms_config.get(self._area_id, [])
        
        # Get platform states
        platform_states = self.hub.state.berth_state.get_all_platform_states(
            selected_platforms if selected_platforms else None
        )
        
        # Get event history (filtered by platform if configured)
        event_history = self.hub.state.berth_state.get_event_history(
            selected_platforms if selected_platforms else None
        )
        
        # Get SMART data for station information if available
        smart_manager = self.hass.data.get(DOMAIN, {}).get(f"{self.entry.entry_id}_smart_manager")
        station_name = None
        station_code = None
        
        if smart_manager and smart_manager.is_available():
            # Try to find station name from SMART data
            # This is a simplified approach - in practice you'd need to map TD area to STANOX
            from .stanox_utils import get_station_name
            # For now, we'll just use the area_id as a placeholder
            station_code = self._area_id
        
        attrs = {
            "area_id": self._area_id,
            "station_name": station_name,
            "station_code": station_code,
            "selected_platforms": selected_platforms if selected_platforms else "all",
            "berth_count": len(area_berths),
            "occupied_berths": {},
        }
        
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

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_TD, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, parsed_message: dict[str, Any]) -> None:
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

    async def async_added_to_hass(self) -> None:
        # Subscribe to TD messages for berth updates
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_TD, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, parsed_message: dict[str, Any]) -> None:
        """Handle TD message update."""
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
    def native_value(self) -> int:
        """Return the count of currently occupied berths in the diagram area."""
        if not self.smart_manager.is_available():
            return 0
        
        # Get all berths in the diagram area
        graph = self.smart_manager.get_graph()
        berth_state = self.hub.state.berth_state
        
        # Get berths for center station and adjacent stations
        all_berths = self._get_all_diagram_berths(graph)
        
        # Count occupied berths
        occupied_count = 0
        for berth_key in all_berths:
            parts = berth_key.split(":", 1)
            if len(parts) == 2:
                td_area, berth_id = parts
                berth_data = berth_state.get_berth(td_area, berth_id)
                if berth_data:
                    occupied_count += 1
        
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
