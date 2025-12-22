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
    CONF_TD_EVENT_HISTORY_SIZE,
    CONF_TD_PLATFORMS,
    CONF_TOC_FILTER,
    CONF_TOPIC,
    CONF_USERNAME,
    CONF_DIAGRAM_CONFIGS,
    CONF_DIAGRAM_ENABLED,
    CONF_DIAGRAM_STANOX,
    CONF_DIAGRAM_RANGE,
    DEFAULT_TOPIC,
    DEFAULT_TD_EVENT_HISTORY_SIZE,
    DEFAULT_PLATFORM_RANGE_MIN,
    DEFAULT_PLATFORM_RANGE_MAX,
    DOMAIN,
)
from .stanox_utils import search_stanox, get_formatted_station_name


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
        self._discovered_platforms: dict[str, list[str]] = {}  # area_id -> list of platform IDs
        self._current_diagram_action: str | None = None  # Track current diagram action
        self._diagram_to_edit: dict | None = None  # Track diagram being edited
    
    def _migrate_diagram_config(self, opts: dict) -> dict:
        """Migrate old single-diagram format to new list format if needed.
        
        Args:
            opts: The options dictionary to migrate
            
        Returns:
            The migrated options dictionary
        """
        if CONF_DIAGRAM_ENABLED in opts and CONF_DIAGRAM_CONFIGS not in opts:
            # Migrate old format to new format
            diagram_configs = []
            if opts.get(CONF_DIAGRAM_ENABLED, False):
                old_stanox = opts.get(CONF_DIAGRAM_STANOX)
                old_range = opts.get(CONF_DIAGRAM_RANGE, 1)
                if old_stanox:
                    diagram_configs.append({
                        "stanox": old_stanox,
                        "enabled": True,
                        "range": old_range
                    })
            opts = opts.copy()
            opts[CONF_DIAGRAM_CONFIGS] = diagram_configs
            # Remove old keys
            opts.pop(CONF_DIAGRAM_ENABLED, None)
            opts.pop(CONF_DIAGRAM_STANOX, None)
            opts.pop(CONF_DIAGRAM_RANGE, None)
        return opts
    
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
            elif action == "configure_td_platforms":
                return await self.async_step_configure_td_platforms()
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
        
        # Perform migration if needed
        opts = self._migrate_diagram_config(opts)
        if opts != self.config_entry.options:
            # Options were migrated, update entry
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=opts
            )
        
        # Show network diagram status
        diagram_configs = opts.get(CONF_DIAGRAM_CONFIGS, [])
        if diagram_configs:
            enabled_count = sum(1 for d in diagram_configs if d.get("enabled", False))
            description += f"\n\nNetwork Diagrams: {enabled_count}/{len(diagram_configs)} enabled"
            for diagram in diagram_configs:
                stanox = diagram.get("stanox", "")
                enabled = diagram.get("enabled", False)
                diagram_range = diagram.get("range", 1)
                status = "✓" if enabled else "✗"
                station_name = get_formatted_station_name(stanox) or stanox
                description += f"\n  {status} {station_name} ({stanox}, range: {diagram_range})"
        
        schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"label": "Add Station", "value": "add_station"},
                            {"label": "Remove Station", "value": "remove_station"},
                            {"label": "Configure Filters (TOC, Event Types)", "value": "configure_filters"},
                            {"label": "Configure Train Describer", "value": "configure_train_describer"},
                            {"label": "Configure TD Platforms", "value": "configure_td_platforms"},
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
            
            # Store event history size
            opts[CONF_TD_EVENT_HISTORY_SIZE] = user_input.get(CONF_TD_EVENT_HISTORY_SIZE, DEFAULT_TD_EVENT_HISTORY_SIZE)
            
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
                vol.Optional(
                    CONF_TD_EVENT_HISTORY_SIZE,
                    default=opts.get(CONF_TD_EVENT_HISTORY_SIZE, DEFAULT_TD_EVENT_HISTORY_SIZE)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=50,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
            }
        )
        return self.async_show_form(
            step_id="configure_train_describer",
            data_schema=schema,
            description_placeholders={
                "description": "Enable Train Describer feed to track train positions through signalling berths. This is useful for creating network diagrams.\n\nLeave TD areas empty to receive all messages, or specify specific area IDs (e.g., 'SK', 'G1', 'RW') to filter.\n\nEvent history size controls how many recent TD events are kept for each area (default: 10, range: 1-50)."
            }
        )
    
    async def async_step_configure_network_diagrams(self, user_input=None) -> FlowResult:
        """Configure Network Diagram sensor options - main menu."""
        opts = self.config_entry.options.copy()
        
        # Perform migration if needed
        opts = self._migrate_diagram_config(opts)
        if opts != self.config_entry.options:
            # Options were migrated, update entry
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=opts
            )
        
        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                self._current_diagram_action = "add"
                return await self.async_step_add_diagram()
            elif action == "edit":
                return await self.async_step_edit_diagram()
            elif action == "delete":
                return await self.async_step_delete_diagram()
            elif action == "done":
                return await self.async_step_init()
        
        # Build description showing current diagrams
        diagram_configs = opts.get(CONF_DIAGRAM_CONFIGS, [])
        description = "Manage Network Diagram sensors. Each diagram shows train positions on a map of berth connections.\n\n"
        
        if diagram_configs:
            description += f"Currently configured diagrams ({len(diagram_configs)}):\n"
            for diagram in diagram_configs:
                stanox = diagram.get("stanox", "")
                enabled = diagram.get("enabled", False)
                diagram_range = diagram.get("range", 1)
                status = "✓ Enabled" if enabled else "✗ Disabled"
                station_name = get_formatted_station_name(stanox) or stanox
                description += f"  • {station_name} ({stanox}) - Range: {diagram_range} - {status}\n"
        else:
            description += "No diagrams configured yet. Add a diagram to get started."
        
        # Build action selector
        action_options = [
            {"label": "Add New Diagram", "value": "add"},
            {"label": "Edit Diagram", "value": "edit"},
            {"label": "Delete Diagram", "value": "delete"},
            {"label": "Done (Return to Main Menu)", "value": "done"},
        ]
        
        schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=action_options,
                        mode=selector.SelectSelectorMode.LIST,
                    ),
                ),
            }
        )
        
        return self.async_show_form(
            step_id="configure_network_diagrams",
            data_schema=schema,
            description_placeholders={"description": description}
        )
    
    async def async_step_add_diagram(self, user_input=None) -> FlowResult:
        """Add a new network diagram."""
        errors = {}
        opts = self.config_entry.options.copy()
        diagram_configs = opts.get(CONF_DIAGRAM_CONFIGS, [])
        
        if user_input is not None:
            # User selected a STANOX from search results
            if "selected_stanox" in user_input and user_input["selected_stanox"]:
                stanox = user_input["selected_stanox"]
                
                # Check if diagram for this STANOX already exists
                if any(d.get("stanox") == stanox for d in diagram_configs):
                    errors["selected_stanox"] = "diagram_already_exists"
                else:
                    # Add the new diagram
                    new_diagram = {
                        "stanox": stanox,
                        "enabled": user_input.get("diagram_enabled", True),
                        "range": user_input.get("diagram_range", 1),
                    }
                    diagram_configs.append(new_diagram)
                    opts[CONF_DIAGRAM_CONFIGS] = diagram_configs
                    
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, options=opts
                    )
                    return await self.async_step_configure_network_diagrams()
            
            # User entered a search query
            if "station_query" in user_input and user_input["station_query"]:
                query = user_input["station_query"]
                self._search_results = await self.hass.async_add_executor_job(
                    search_stanox, query, 50
                )
                
                if not self._search_results:
                    errors["station_query"] = "no_results"
        
        # Build schema with search results if available
        if self._search_results:
            station_options = [
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
                            options=station_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    vol.Optional("diagram_enabled", default=True): bool,
                    vol.Optional("diagram_range", default=1): selector.NumberSelector(
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
                    vol.Required("station_query"): str,
                    vol.Optional("diagram_enabled", default=True): bool,
                    vol.Optional("diagram_range", default=1): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=5,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                }
            )
        
        return self.async_show_form(
            step_id="add_diagram",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "description": "Search for a station to use as the center of the diagram. The range controls how many stations in each direction to include (1-5)."
            }
        )
    
    async def async_step_edit_diagram(self, user_input=None) -> FlowResult:
        """Edit an existing network diagram."""
        errors = {}
        opts = self.config_entry.options.copy()
        diagram_configs = opts.get(CONF_DIAGRAM_CONFIGS, [])
        
        # If no diagrams exist, show error and return
        if not diagram_configs:
            return self.async_show_form(
                step_id="edit_diagram",
                data_schema=vol.Schema({}),
                errors={"base": "no_diagrams_configured"},
                description_placeholders={
                    "description": "No diagrams are configured yet. Please add a diagram first."
                }
            )
        
        if user_input is not None:
            # If we have diagram_index, we're updating the diagram
            if "diagram_enabled" in user_input and self._diagram_to_edit is not None:
                # Update the diagram
                stanox = self._diagram_to_edit.get("stanox")
                for diagram in diagram_configs:
                    if diagram.get("stanox") == stanox:
                        # Update individual keys to preserve any future additions
                        diagram["enabled"] = user_input.get("diagram_enabled", True)
                        diagram["range"] = user_input.get("diagram_range", 1)
                        break
                
                opts[CONF_DIAGRAM_CONFIGS] = diagram_configs
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=opts
                )
                self._diagram_to_edit = None
                return await self.async_step_configure_network_diagrams()
            
            # User selected a diagram to edit
            if "select_diagram" in user_input and user_input["select_diagram"]:
                selected_stanox = user_input["select_diagram"]
                # Find the selected diagram
                for diagram in diagram_configs:
                    if diagram.get("stanox") == selected_stanox:
                        self._diagram_to_edit = diagram
                        break
        
        # If we're editing a specific diagram, show edit form
        if self._diagram_to_edit is not None:
            stanox = self._diagram_to_edit.get("stanox", "")
            station_name = get_formatted_station_name(stanox) or stanox
            
            schema = vol.Schema(
                {
                    vol.Optional(
                        "diagram_enabled",
                        default=self._diagram_to_edit.get("enabled", True)
                    ): bool,
                    vol.Optional(
                        "diagram_range",
                        default=self._diagram_to_edit.get("range", 1)
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
                step_id="edit_diagram",
                data_schema=schema,
                errors=errors,
                description_placeholders={
                    "description": f"Editing diagram for: {station_name} ({stanox})\n\nAdjust the enabled status and range as needed."
                }
            )
        
        # Show selection of diagrams to edit
        diagram_options = [
            {
                "label": f"{get_formatted_station_name(d.get('stanox')) or d.get('stanox')} ({d.get('stanox')}) - Range: {d.get('range', 1)} - {'Enabled' if d.get('enabled', False) else 'Disabled'}",
                "value": d.get("stanox", ""),
            }
            for d in diagram_configs
        ]
        
        schema = vol.Schema(
            {
                vol.Required("select_diagram"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=diagram_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )
        
        return self.async_show_form(
            step_id="edit_diagram",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "description": "Select a diagram to edit."
            }
        )
    
    async def async_step_delete_diagram(self, user_input=None) -> FlowResult:
        """Delete a network diagram."""
        errors = {}
        opts = self.config_entry.options.copy()
        diagram_configs = opts.get(CONF_DIAGRAM_CONFIGS, [])
        
        # If no diagrams exist, show error and return
        if not diagram_configs:
            return self.async_show_form(
                step_id="delete_diagram",
                data_schema=vol.Schema({}),
                errors={"base": "no_diagrams_configured"},
                description_placeholders={
                    "description": "No diagrams are configured yet. Please add a diagram first."
                }
            )
        
        if user_input is not None:
            if "delete_diagram" in user_input and user_input["delete_diagram"]:
                stanox_to_delete = user_input["delete_diagram"]
                # Remove the diagram
                diagram_configs = [d for d in diagram_configs if d.get("stanox") != stanox_to_delete]
                opts[CONF_DIAGRAM_CONFIGS] = diagram_configs
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=opts
                )
                return await self.async_step_configure_network_diagrams()
        
        # Show selection of diagrams to delete
        diagram_options = [
            {
                "label": f"{get_formatted_station_name(d.get('stanox')) or d.get('stanox')} ({d.get('stanox')}) - Range: {d.get('range', 1)}",
                "value": d.get("stanox", ""),
            }
            for d in diagram_configs
        ]
        
        schema = vol.Schema(
            {
                vol.Required("delete_diagram"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=diagram_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )
        
        return self.async_show_form(
            step_id="delete_diagram",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "description": "⚠️ Warning: This action cannot be undone.\n\nSelect a diagram to delete."
            }
        )
    
    async def async_step_configure_td_platforms(self, user_input=None) -> FlowResult:
        """Configure platform tracking for TD areas."""
        errors = {}
        
        if user_input is not None:
            opts = self.config_entry.options.copy()
            
            # Get selected area
            selected_area = user_input.get("td_area")
            if selected_area:
                # Get selected platforms
                selected_platforms = user_input.get("selected_platforms", [])
                
                # Update platform configuration
                td_platforms = opts.get(CONF_TD_PLATFORMS, {})
                if selected_platforms:
                    td_platforms[selected_area] = selected_platforms
                elif selected_area in td_platforms:
                    # Remove area if no platforms selected
                    del td_platforms[selected_area]
                
                opts[CONF_TD_PLATFORMS] = td_platforms
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=opts
                )
                return self.async_create_entry(title="", data=opts)
            else:
                errors["td_area"] = "no_area_selected"
        
        opts = self.config_entry.options
        td_areas = opts.get(CONF_TD_AREAS, [])
        td_platforms_config = opts.get(CONF_TD_PLATFORMS, {})
        
        # If no TD areas configured, show error
        if not td_areas:
            return self.async_show_form(
                step_id="configure_td_platforms",
                data_schema=vol.Schema({}),
                errors={"base": "no_td_areas"},
                description_placeholders={
                    "description": "No TD areas are configured. Please configure TD areas first in 'Configure Train Describer'."
                }
            )
        
        # Try to discover platforms using SMART data
        smart_manager = self.hass.data.get(DOMAIN, {}).get(f"{self.config_entry.entry_id}_smart_manager")
        
        if smart_manager and smart_manager.is_available():
            # Discover platforms from SMART data
            from .smart_utils import get_platforms_for_area
            graph = smart_manager.get_graph()
            
            for area_id in td_areas:
                if area_id not in self._discovered_platforms:
                    platforms = get_platforms_for_area(graph, area_id)
                    self._discovered_platforms[area_id] = platforms
        else:
            # SMART data not available, use default platform list
            for area_id in td_areas:
                if area_id not in self._discovered_platforms:
                    # Provide default set of platform numbers
                    self._discovered_platforms[area_id] = [
                        str(i) for i in range(DEFAULT_PLATFORM_RANGE_MIN, DEFAULT_PLATFORM_RANGE_MAX + 1)
                    ]
        
        # Build schema for area and platform selection
        area_options = [
            {
                "label": f"{area_id} ({len(td_platforms_config.get(area_id, []))} platforms configured)",
                "value": area_id,
            }
            for area_id in td_areas
        ]
        
        # Get currently selected area (from previous input or first area)
        current_area = user_input.get("td_area") if user_input else (td_areas[0] if td_areas else None)
        
        # Build platform options for selected area
        platform_options = []
        if current_area and current_area in self._discovered_platforms:
            platform_options = [
                {"label": f"Platform {p}", "value": p}
                for p in self._discovered_platforms[current_area]
            ]
        
        # Get currently selected platforms for this area
        current_platforms = td_platforms_config.get(current_area, []) if current_area else []
        
        schema_dict = {
            vol.Required("td_area", default=current_area): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=area_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
        }
        
        if platform_options:
            schema_dict[vol.Optional("selected_platforms", default=current_platforms)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=platform_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            )
        
        schema = vol.Schema(schema_dict)
        
        # Build description showing current configuration
        description = "Select a TD area and choose which platforms to track.\n\n"
        if smart_manager and smart_manager.is_available():
            description += "Platforms discovered from SMART berth topology data.\n\n"
        else:
            description += "SMART data not available. Showing default platform list (1-10).\n\n"
        
        if td_platforms_config:
            description += "Current configuration:\n"
            for area_id, platforms in td_platforms_config.items():
                description += f"  • {area_id}: {', '.join(platforms)}\n"
        else:
            description += "No platforms configured yet. All platforms will be tracked by default."
        
        return self.async_show_form(
            step_id="configure_td_platforms",
            data_schema=schema,
            errors=errors,
            description_placeholders={"description": description}
        )
