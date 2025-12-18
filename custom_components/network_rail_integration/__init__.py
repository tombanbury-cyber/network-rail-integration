"""Network Rail integration - init."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# NOTE:
# If your existing __init__.py already creates and stores the coordinator,
# merge the forward_entry_setups line into your existing async_setup_entry implementation.
# This file provides a safe example which stores a coordinator under hass.data[DOMAIN][entry.entry_id]["coordinator"].
# If your integration already does that, this change is effectively just adding the platform forward.

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry.

    This example assumes a coordinator is created elsewhere in this function.
    If you already have coordinator creation logic, keep it and ensure the coordinator
    is stored as hass.data[DOMAIN][entry.entry_id]["coordinator"].
    """
    # Example placeholder: keep your real coordinator creation here.
    # from .coordinator import NetworkRailDataUpdateCoordinator
    # coordinator = NetworkRailDataUpdateCoordinator(hass, entry)
    # await coordinator.async_config_entry_first_refresh()
    # hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator}

    # Forward the entry setup to the sensor platform so sensor.py::async_setup_entry runs.
    hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True
