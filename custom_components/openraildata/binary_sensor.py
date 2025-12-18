"""Binary sensors for OpenRailData."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DISPATCH_CONNECTED


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OpenRailDataConnectedBinarySensor(hass, entry, hub)], True)


class OpenRailDataConnectedBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Feed connected"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(self.hass, DISPATCH_CONNECTED, self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self, _is_connected: bool) -> None:
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_connected"

    @property
    def is_on(self) -> bool | None:
        return bool(self.hub.state.connected)

    @property
    def extra_state_attributes(self):
        return {
            "last_error": self.hub.state.last_error,
            "last_seen_monotonic": self.hub.state.last_seen_monotonic,
        }
