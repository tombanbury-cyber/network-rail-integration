"""Config flow for Network Rail Integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_TD,
    CONF_EVENT_TYPES,
    CONF_PASSWORD,
    CONF_STANOX_FILTER,
    CONF_STATIONS,
    CONF_TD_AREAS,
    CONF_TOC_FILTER,
    CONF_TOPIC,
    CONF_USERNAME,
    CONF_DIAGRAM_ENABLED,
    CONF_DIAGRAM_STANOX,
    CONF_DIAGRAM_RANGE,
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
        """Manage the options - main menu."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_station":
                return await self.async_step_add_station()
            elif action == "remove_station":
                return await self.async_step_remove_station()
            elif action == "configure_filters":
                return await self.async_step_configure_filters()
            elif action == "configure_train_describer":
                return await self.async_step_configure_train_describer()
            elif action == "configure_network_diagrams":
                return await self.async_step_configure_network_diagrams()
            
            return self.async_create_entry(title="", data=self.config_entry.options)
        
        opts = self.config_entry.options
        stations = opts.get(CONF_STATIONS, [])
        
        # Build description showing current stations
        description = "Configure train movement tracking options.\n\n"
        if stations:
            description += f"Currently tracking {len(stations)} station(s):\n"
            for station in stations:
                stanox = station.get("stanox", "")
                name = station.get("name", "Unknown")
                description += f"  • {name} ({stanox})\n"
        else:
            description += "No stations configured yet. Add stations to start tracking train movements."
        
        # Add TD status if enabled
        if opts.get(CONF_ENABLE_TD, False):
            td_areas = opts.get(CONF_TD_AREAS, [])
            description += f"\n\nTrain Describer: Enabled"
            if td_areas:
                description += f" (tracking {len(td_areas)} area(s))"
        
        # Add network diagram status if enabled
        from .const import CONF_DIAGRAM_ENABLED, CONF_DIAGRAM_STANOX
        if opts.get(CONF_DIAGRAM_ENABLED, False):
            diagram_stanox = opts.get(CONF_DIAGRAM_STANOX, "")
            description += f"\n\nNetwork Diagram: Enabled (center: {diagram_stanox})"
        
        schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"label": "Add Station", "value": "add_station"},
                            {"label": "Remove Station", "value": "remove_station"},
                            {"label": "Configure Filters (TOC, Event Types)", "value": "configure_filters"},
                            {"label": "Configure Train Describer", "value": "configure_train_describer"},
                            {"label": "Configure Network Diagrams", "value": "configure_network_diagrams"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    ),
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={"description": description}
        )
    
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
                    vol.Optional("station_query"): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required("station_query"): str,
                }
            )
        
        return self.async_show_form(
            step_id="search_station",
            data_schema=schema,
            errors=errors,
        )
    
    async def async_step_add_station(self, user_input=None) -> FlowResult:
        """Add a new station to track."""
        errors = {}
        
        if user_input is not None:
            # User selected a STANOX from search results
            if "selected_stanox" in user_input and user_input["selected_stanox"]:
                opts = self.config_entry.options.copy()
                stations = opts.get(CONF_STATIONS, [])
                
                # Find the station name from search results
                stanox = user_input["selected_stanox"]
                station_name = "Unknown"
                for result in self._search_results:
                    if result["stanox"] == stanox:
                        station_name = result["stanme"]
                        break
                
                # Check if station already exists
                if any(s.get("stanox") == stanox for s in stations):
                    errors["selected_stanox"] = "station_already_exists"
                else:
                    # Add the new station
                    stations.append({
                        "stanox": stanox,
                        "name": station_name,
                    })
                    opts[CONF_STATIONS] = stations
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, options=opts
                    )
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
                    vol.Optional("station_query"): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required("station_query"): str,
                }
            )
        
        return self.async_show_form(
            step_id="add_station",
            data_schema=schema,
            errors=errors,
        )
    
    async def async_step_remove_station(self, user_input=None) -> FlowResult:
        """Remove a station from tracking."""
        opts = self.config_entry.options.copy()
        stations = opts.get(CONF_STATIONS, [])
        
        if not stations:
            return await self.async_step_init()
        
        if user_input is not None:
            if "remove_stanox" in user_input and user_input["remove_stanox"]:
                stanox_to_remove = user_input["remove_stanox"]
                stations = [s for s in stations if s.get("stanox") != stanox_to_remove]
                opts[CONF_STATIONS] = stations
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=opts
                )
                return self.async_create_entry(title="", data=opts)
        
        # Build list of stations to remove
        options = [
            {
                "label": f"{s.get('name', 'Unknown')} ({s.get('stanox', '')})",
                "value": s.get("stanox", ""),
            }
            for s in stations
        ]
        
        schema = vol.Schema(
            {
                vol.Required("remove_stanox"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )
        
        return self.async_show_form(
            step_id="remove_station",
            data_schema=schema,
        )
    
    async def async_step_configure_filters(self, user_input=None) -> FlowResult:
        """Configure global filters (TOC, event types)."""
        if user_input is not None:
            opts = self.config_entry.options.copy()
            opts[CONF_TOC_FILTER] = user_input.get(CONF_TOC_FILTER, "")
            opts[CONF_EVENT_TYPES] = user_input.get(CONF_EVENT_TYPES, [])
            return self.async_create_entry(title="", data=opts)
        
        opts = self.config_entry.options
        schema = vol.Schema(
            {
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
        return self.async_show_form(step_id="configure_filters", data_schema=schema)
    
    async def async_step_configure_train_describer(self, user_input=None) -> FlowResult:
        """Configure Train Describer feed options."""
        if user_input is not None:
            opts = self.config_entry.options.copy()
            opts[CONF_ENABLE_TD] = user_input.get(CONF_ENABLE_TD, False)
            
            # Parse comma-separated TD areas
            td_areas_str = user_input.get(CONF_TD_AREAS, "")
            if td_areas_str:
                td_areas = [area.strip().upper() for area in td_areas_str.split(",") if area.strip()]
            else:
                td_areas = []
            opts[CONF_TD_AREAS] = td_areas
            
            return self.async_create_entry(title="", data=opts)
        
        opts = self.config_entry.options
        # Convert list of areas back to comma-separated string for display
        td_areas_list = opts.get(CONF_TD_AREAS, [])
        td_areas_str = ", ".join(td_areas_list) if td_areas_list else ""
        
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLE_TD,
                    default=opts.get(CONF_ENABLE_TD, False)
                ): bool,
                vol.Optional(
                    CONF_TD_AREAS,
                    default=td_areas_str,
                    description="Comma-separated list of TD area IDs to track (e.g., 'SK, G1, RW'). Leave empty to track all areas."
                ): str,
            }
        )
        return self.async_show_form(
            step_id="configure_train_describer",
            data_schema=schema,
            description_placeholders={
                "description": "Enable Train Describer feed to track train positions through signalling berths. This is useful for creating network diagrams.\n\nLeave TD areas empty to receive all messages, or specify specific area IDs (e.g., 'SK', 'G1', 'RW') to filter."
            }
        )
    
    async def async_step_configure_network_diagrams(self, user_input=None) -> FlowResult:
        """Configure Network Diagram sensor options."""
        errors = {}
        
        if user_input is not None:
            # User selected a STANOX from search results
            if "selected_stanox" in user_input and user_input["selected_stanox"]:
                opts = self.config_entry.options.copy()
                
                from .const import CONF_DIAGRAM_ENABLED, CONF_DIAGRAM_STANOX, CONF_DIAGRAM_RANGE
                
                opts[CONF_DIAGRAM_ENABLED] = user_input.get(CONF_DIAGRAM_ENABLED, False)
                opts[CONF_DIAGRAM_STANOX] = user_input["selected_stanox"]
                opts[CONF_DIAGRAM_RANGE] = user_input.get(CONF_DIAGRAM_RANGE, 1)
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=opts
                )
                return self.async_create_entry(title="", data=opts)
            
            # User entered a search query
            if "station_query" in user_input and user_input["station_query"]:
                query = user_input["station_query"]
                self._search_results = await self.hass.async_add_executor_job(
                    search_stanox, query, 50
                )
                
                if not self._search_results:
                    errors["station_query"] = "no_results"
        
        from .const import CONF_DIAGRAM_ENABLED, CONF_DIAGRAM_STANOX, CONF_DIAGRAM_RANGE
        
        opts = self.config_entry.options
        
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
                    vol.Optional(
                        CONF_DIAGRAM_ENABLED,
                        default=opts.get(CONF_DIAGRAM_ENABLED, False)
                    ): bool,
                    vol.Optional("selected_stanox"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    vol.Optional(
                        CONF_DIAGRAM_RANGE,
                        default=opts.get(CONF_DIAGRAM_RANGE, 1)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=5,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional("station_query"): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_DIAGRAM_ENABLED,
                        default=opts.get(CONF_DIAGRAM_ENABLED, False)
                    ): bool,
                    vol.Required("station_query"): str,
                    vol.Optional(
                        CONF_DIAGRAM_RANGE,
                        default=opts.get(CONF_DIAGRAM_RANGE, 1)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=5,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                }
            )
        
        return self.async_show_form(
            step_id="configure_network_diagrams",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "description": "Enable Network Diagram sensor to visualize train positions on a map of berth connections.\n\nSearch for a station to use as the center of the diagram, then set the range (number of stations in each direction to include)."
            }
        )
