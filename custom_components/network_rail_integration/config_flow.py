"""Config flow for Network Rail Integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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
from .stanox_utils import search_stanox


class NetworkRailConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

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
            title=f"Network Rail ({user_input.get(CONF_TOPIC, DEFAULT_TOPIC)})",
            data=user_input,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NetworkRailOptionsFlowHandler()


class NetworkRailOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self) -> None:
        """Initialize options flow."""
        self._search_results: list[dict[str, str]] = []
    
    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Check if user wants to search for a station
            if user_input.get("search_station"):
                return await self.async_step_search_station()
            
            return self.async_create_entry(title="", data=user_input)
        
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_STANOX_FILTER, 
                    default=opts.get(CONF_STANOX_FILTER, "")
                ): str,
                vol.Optional(
                    "search_station",
                    default=False,
                ): bool,
                vol.Optional(
                    CONF_TOC_FILTER, 
                    default=opts.get(CONF_TOC_FILTER, "")
                ): str,
                vol.Optional(
                    CONF_EVENT_TYPES, 
                    default=opts.get(CONF_EVENT_TYPES, [])
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["ARRIVAL", "DEPARTURE"],
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
    
    async def async_step_search_station(self, user_input=None) -> FlowResult:
        """Search for a station by name."""
        errors = {}
        
        if user_input is not None:
            # User selected a STANOX from search results
            if "selected_stanox" in user_input and user_input["selected_stanox"]:
                # Return to init step with the selected STANOX
                opts = self.config_entry.options.copy()
                opts[CONF_STANOX_FILTER] = user_input["selected_stanox"]
                return self.async_create_entry(title="", data=opts)
            
            # User entered a search query
            if "station_query" in user_input and user_input["station_query"]:
                query = user_input["station_query"]
                self._search_results = await self.hass.async_add_executor_job(
                    search_stanox, query, 50
                )
                
                if not self._search_results:
                    errors["station_query"] = "no_results"
        
        # Build options from search results
        if self._search_results:
            options = [
                {
                    "label": f"{r['stanme']} ({r['stanox']})",
                    "value": r["stanox"],
                }
                for r in self._search_results
            ]
            
            schema = vol.Schema(
                {
                    vol.Optional("selected_stanox"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    vol.Optional("station_query", default=""): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required("station_query", default=""): str,
                }
            )
        
        return self.async_show_form(
            step_id="search_station",
            data_schema=schema,
            errors=errors,
        )
