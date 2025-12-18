"""Sensors for OpenRailData (Train Movements)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DISPATCH_MOVEMENT


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OpenRailDataLastMovementSensor(hass, entry, hub)], True)


def _ms_to_local_iso(ms: Any) -> str | None:
    try:
        ms_i = int(ms)
    except Exception:
        return None
    dt_utc = datetime.fromtimestamp(ms_i / 1000.0, tz=timezone.utc)
    dt_local = dt_util.as_local(dt_utc)
    return dt_local.isoformat()


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

        attrs: dict[str, Any] = {
            "msg_type": header.get("msg_type"),
            "source_dev_id": header.get("source_dev_id"),
            "original_data_source": header.get("original_data_source"),
            "msg_queue_timestamp": header.get("msg_queue_timestamp"),
            "msg_queue_time_local": _ms_to_local_iso(header.get("msg_queue_timestamp")),
            "train_id": body.get("train_id"),
            "toc_id": body.get("toc_id"),
            "event_type": body.get("event_type"),
            "planned_timestamp": body.get("planned_timestamp"),
            "planned_time_local": _ms_to_local_iso(body.get("planned_timestamp")),
            "actual_timestamp": body.get("actual_timestamp"),
            "actual_time_local": _ms_to_local_iso(body.get("actual_timestamp")),
            "timetable_variation": body.get("timetable_variation"),
            "variation_status": body.get("variation_status"),
            "loc_stanox": body.get("loc_stanox"),
            "platform": body.get("platform"),
            "line_ind": body.get("line_ind"),
            "direction_ind": body.get("direction_ind"),
            "corr_id": body.get("corr_id"),
            "event_source": body.get("event_source"),
            "train_terminated": body.get("train_terminated"),
            "offroute_ind": body.get("offroute_ind"),
            "batch_count_seen": self.hub.state.last_batch_count,
            "raw": body,
        }

        return attrs
