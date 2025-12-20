"""The Network Rail integration (Network Rail STOMP feeds)."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .hub import OpenRailDataHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Network Rail from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    hub = OpenRailDataHub(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = hub

    await hub.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register update listener to reload when options change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hub: OpenRailDataHub = hass.data[DOMAIN].pop(entry.entry_id)
    await hub.async_stop()
    return unload_ok
