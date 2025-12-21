"""Debug log sensor and logger helper for Network Rail Integration."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DebugLogSensor(SensorEntity):
    """Sensor that displays recent log messages."""

    _attr_has_entity_name = True
    _attr_name = "Debug Log"
    _attr_icon = "mdi:text-box-search-outline"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the debug log sensor."""
        self.hass = hass
        self.entry = entry
        self._log_entries: deque[dict[str, str]] = deque(maxlen=50)
        # Add initial log entry
        self.add_log_entry("INFO", "Debug log sensor initialized")

    def add_log_entry(self, level: str, message: str) -> None:
        """Add a log entry to the sensor."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
        }
        self._log_entries.append(entry)
        # Schedule state update
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self.entry.entry_id}_debug_log"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Network Rail Integration",
            manufacturer="Network Rail",
            model="Debug Logs",
        )

    @property
    def native_value(self) -> str | None:
        """Return the most recent log entry as the state."""
        if not self._log_entries:
            return "No log messages"
        latest = self._log_entries[-1]
        return f"[{latest['level']}] {latest['message']}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all log entries as attributes."""
        return {
            "log_entries": list(self._log_entries),
            "entry_count": len(self._log_entries),
        }


class DebugLogger:
    """Logger wrapper that logs to both standard logger and debug sensor."""

    def __init__(self, logger: logging.Logger, sensor: DebugLogSensor | None = None) -> None:
        """Initialize the debug logger."""
        self._logger = logger
        self._sensor = sensor

    def set_sensor(self, sensor: DebugLogSensor) -> None:
        """Set or update the debug sensor."""
        self._sensor = sensor

    def _format_message(self, message: str, *args) -> str:
        """Format log message with arguments, handling errors gracefully."""
        try:
            return message % args if args else message
        except (TypeError, ValueError):
            return message

    def debug(self, message: str, *args, **kwargs) -> None:
        """Log a debug message."""
        self._logger.debug(message, *args, **kwargs)
        if self._sensor:
            formatted_message = self._format_message(message, *args)
            self._sensor.add_log_entry("DEBUG", formatted_message)

    def info(self, message: str, *args, **kwargs) -> None:
        """Log an info message."""
        self._logger.info(message, *args, **kwargs)
        if self._sensor:
            formatted_message = self._format_message(message, *args)
            self._sensor.add_log_entry("INFO", formatted_message)

    def warning(self, message: str, *args, **kwargs) -> None:
        """Log a warning message."""
        self._logger.warning(message, *args, **kwargs)
        if self._sensor:
            formatted_message = self._format_message(message, *args)
            self._sensor.add_log_entry("WARNING", formatted_message)

    def error(self, message: str, *args, **kwargs) -> None:
        """Log an error message."""
        self._logger.error(message, *args, **kwargs)
        if self._sensor:
            formatted_message = self._format_message(message, *args)
            self._sensor.add_log_entry("ERROR", formatted_message)

    def exception(self, message: str, *args, **kwargs) -> None:
        """Log an exception message."""
        self._logger.exception(message, *args, **kwargs)
        if self._sensor:
            formatted_message = self._format_message(message, *args)
            self._sensor.add_log_entry("ERROR", formatted_message)
