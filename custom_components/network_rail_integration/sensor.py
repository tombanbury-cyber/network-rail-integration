"""Sensor platform for Network Rail integration - per-station (STANOX) sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up STANOX station sensors from a config entry."""
    store = hass.data.get(DOMAIN, {})
    coordinator: DataUpdateCoordinator | None = store.get(entry.entry_id, {}).get("coordinator")

    if coordinator is None:
        # No coordinator found — nothing to create
        return

    stations = coordinator.data.get("stations", {}) or {}
    entities: list[StationSensor] = []

    # If stations is a list, convert to dict keyed by STANOX:
    if isinstance(stations, list):
        station_map: dict[str, dict] = {}
        for s in stations:
            key = s.get("stanox") or s.get("stn") or s.get("stnox") or s.get("code")
            if key:
                station_map[str(key)] = s
        stations = station_map

    for stn_code, stn_info in stations.items():
        entities.append(StationSensor(coordinator, entry, stn_code))

    if entities:
        async_add_entities(entities, True)


class StationSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing a single station (STANOX)."""

    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry, stn_code: str) -> None:
        """Initialize the station sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._stn = str(stn_code)
        station_name = coordinator.data.get("stations", {}).get(self._stn, {}).get("name")
        if station_name:
            self._attr_name = f"{station_name} ({self._stn})"
        else:
            self._attr_name = f"Station {self._stn}"
        self._attr_unique_id = f"{entry.entry_id}_station_{self._stn}"
        self._attr_native_unit_of_measurement = "trains"

    @property
    def native_value(self) -> Any:
        """Return the main value for the station sensor.

        Priority:
        1. data['train_count']
        2. len(data['trains'])
        3. data['active'] if numeric
        """
        stations = self.coordinator.data.get("stations", {}) or {}
        data = stations.get(self._stn, {}) or {}

        if "train_count" in data:
            return data.get("train_count")

        trains = data.get("trains")
        if isinstance(trains, (list, tuple)):
            return len(trains)

        if "active" in data and isinstance(data["active"], (int, float)):
            return data["active"]

        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return station-specific attributes (raw station dict)."""
        stations = self.coordinator.data.get("stations", {}) or {}
        data = stations.get(self._stn, {}) or {}
        return dict(data)
