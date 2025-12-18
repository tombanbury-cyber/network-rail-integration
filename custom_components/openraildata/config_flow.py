"""Config flow for OpenRailData."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_EVENT_TYPES,
    CONF_PASSWORD,
    CONF_STANOX_FILTER,
    CONF_TOC_FILTER,
    CONF_TOPIC,
    CONF_USERNAME,
    DEFAULT_TOPIC,
    DOMAIN,
)


class OpenRailDataConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_TOPIC, default=DEFAULT_TOPIC): str,
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)

        await self.async_set_unique_id(f"{DOMAIN}_{user_input[CONF_USERNAME]}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"OpenRailData ({user_input.get(CONF_TOPIC, DEFAULT_TOPIC)})",
            data=user_input,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OpenRailDataOptionsFlowHandler(config_entry)


class OpenRailDataOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is None:
            opts = self.config_entry.options
            schema = vol.Schema(
                {
                    vol.Optional(CONF_STANOX_FILTER, default=opts.get(CONF_STANOX_FILTER, "")): str,
                    vol.Optional(CONF_TOC_FILTER, default=opts.get(CONF_TOC_FILTER, "")): str,
                    vol.Optional(CONF_EVENT_TYPES, default=opts.get(CONF_EVENT_TYPES, [])): list,
                }
            )
            return self.async_show_form(step_id="init", data_schema=schema)

        return self.async_create_entry(title="", data=user_input)
