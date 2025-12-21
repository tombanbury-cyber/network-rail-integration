"""The Network Rail integration (Network Rail STOMP feeds)."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .hub import OpenRailDataHub
from .debug_log import DebugLogger

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Network Rail from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create debug logger (sensor will be attached later during sensor setup)
    debug_logger = DebugLogger(_LOGGER)
    hass.data[DOMAIN][f"{entry.entry_id}_debug_logger"] = debug_logger

    hub = OpenRailDataHub(hass, entry, debug_logger)
    hass.data[DOMAIN][entry.entry_id] = hub

    await hub.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # After platforms are set up, connect the debug sensor to the logger
    debug_sensor = hass.data[DOMAIN].get(f"{entry.entry_id}_debug_sensor")
    if debug_sensor:
        debug_logger.set_sensor(debug_sensor)
    
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
