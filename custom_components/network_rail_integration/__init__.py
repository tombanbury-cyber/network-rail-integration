"""The Network Rail integration (Network Rail STOMP feeds)."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD
from .hub import OpenRailDataHub
from .debug_log import DebugLogger
from .smart_data import SmartDataManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]

SERVICE_REFRESH_SMART_DATA = "refresh_smart_data"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Network Rail from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create debug logger (sensor will be attached later during sensor setup)
    debug_logger = DebugLogger(_LOGGER)
    hass.data[DOMAIN][f"{entry.entry_id}_debug_logger"] = debug_logger

    # Initialize SMART data manager
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    smart_manager = SmartDataManager(hass, username, password)
    hass.data[DOMAIN][f"{entry.entry_id}_smart_manager"] = smart_manager
    
    # Load SMART data asynchronously (non-blocking)
    hass.async_create_task(smart_manager.load_data())

    hub = OpenRailDataHub(hass, entry, debug_logger)
    hass.data[DOMAIN][entry.entry_id] = hub

    await hub.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # After platforms are set up, connect the debug sensor to the logger
    debug_sensor = hass.data[DOMAIN].get(f"{entry.entry_id}_debug_sensor")
    if debug_sensor:
        debug_logger.set_sensor(debug_sensor)
        debug_logger.info("Debug sensor connected to logger")
    else:
        _LOGGER.warning("Debug sensor not found, debug logging to UI will not be available")
    
    # Register services
    async def handle_refresh_smart_data(call: ServiceCall) -> None:
        """Handle refresh_smart_data service call."""
        _LOGGER.info("Refreshing SMART data via service call")
        success = await smart_manager.refresh_data()
        if success:
            _LOGGER.info("SMART data refreshed successfully")
        else:
            _LOGGER.error("Failed to refresh SMART data")
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_SMART_DATA,
        handle_refresh_smart_data,
        schema=vol.Schema({}),
    )
    
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
    
    # Clean up SMART manager
    hass.data[DOMAIN].pop(f"{entry.entry_id}_smart_manager", None)
    
    # Unregister services if this is the last entry
    entries = hass.config_entries.async_entries(DOMAIN)
    if len(entries) == 0:
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH_SMART_DATA)
    
    return unload_ok
