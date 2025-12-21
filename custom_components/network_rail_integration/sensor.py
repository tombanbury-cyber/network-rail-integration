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
)
from .toc_codes import get_toc_name, get_direction_description, get_line_description
from .stanox_utils import get_station_name
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
        entities.append(TrainDescriberStatusSensor(hass, entry, hub))
        entities.append(TrainDescriberRawJsonSensor(hass, entry, hub))
        
        # Create sensors for specific TD areas if configured
        td_areas = options.get(CONF_TD_AREAS, [])
        for area_id in td_areas:
            entities.append(TrainDescriberAreaSensor(hass, entry, hub, area_id))
    
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
        self._attr_name = station_name
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
        return f"{msg_type}"

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
        self._attr_name = f"TD Area {area_id}"
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
        
        attrs = {
            "area_id": self._area_id,
            "berth_count": len(area_berths),
            "occupied_berths": {},
        }
        
        # Add current berth occupancy
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
