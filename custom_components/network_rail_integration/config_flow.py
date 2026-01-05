"""Config flow for Network Rail Integration."""

from __future__ import annotations

import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_TD,
    CONF_ENABLE_VSTP,
    CONF_EVENT_TYPES,
    CONF_PASSWORD,
    CONF_STANOX_FILTER,
    CONF_STATIONS,
    CONF_TD_AREAS,
    CONF_TD_EVENT_HISTORY_SIZE,
    CONF_TD_MAX_BATCH_SIZE,
    CONF_TD_MAX_MESSAGES_PER_SECOND,
    CONF_TD_UPDATE_INTERVAL,
    CONF_TOC_FILTER,
    CONF_TOPIC,
    CONF_USERNAME,
    CONF_DIAGRAM_CONFIGS,
    CONF_DIAGRAM_ENABLED,
    CONF_DIAGRAM_STANOX,
    CONF_DIAGRAM_RANGE,
    CONF_TRACK_SECTIONS,
    CONF_TRACK_SECTION_NAME,
    CONF_TRACK_SECTION_CENTER_STANOX,
    CONF_TRACK_SECTION_BERTH_RANGE,
    CONF_TRACK_SECTION_TD_AREAS,
    CONF_TRACK_SECTION_ALERT_SERVICES,
    CONF_ENABLE_DEBUG_SENSOR,
    CONF_ENABLE_TD_RAW_JSON,
    DEFAULT_TOPIC,
    DEFAULT_TD_EVENT_HISTORY_SIZE,
    DEFAULT_TD_MAX_BATCH_SIZE,
    DEFAULT_TD_MAX_MESSAGES_PER_SECOND,
    DEFAULT_TD_UPDATE_INTERVAL,
    DOMAIN,
)
from .stanox_utils import search_stanox, get_formatted_station_name_async


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
        self._current_diagram_action: str | None = None  # Track current diagram action
        self._diagram_to_edit: dict | None = None  # Track diagram being edited
        self._track_section_center: dict | None = None  # Track selected center for track section
        self._track_section_to_configure: str | None = None  # Track section being configured
    
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
            elif action == "configure_vstp":
                return await self.async_step_configure_vstp()
            elif action == "configure_network_diagrams":
                return await self.async_step_configure_network_diagrams()
            elif action == "add_track_section":
                return await self.async_step_add_track_section()
            elif action == "remove_track_section":
                return await self.async_step_remove_track_section()
            elif action == "configure_track_section_alerts":
                return await self.async_step_configure_track_section_alerts()
            elif action == "configure_advanced":
                return await self.async_step_configure_advanced()
            
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
        
        # Add VSTP status if enabled
        if opts.get(CONF_ENABLE_VSTP, False):
            description += f"\n\nVSTP Feed: Enabled"
        
        # Add Track Section status
        from .const import CONF_TRACK_SECTIONS
        track_sections = opts.get(CONF_TRACK_SECTIONS, [])
        if track_sections:
            description += f"\n\nTrack Sections: {len(track_sections)} configured"
            for section in track_sections:
                name = section.get("name", "Unknown")
                stanox = section.get("center_stanox", "")
                description += f"\n  • {name} (center: {stanox})"
        
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
                station_name = await get_formatted_station_name_async(stanox) or stanox
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
                            {"label": "Configure VSTP Feed", "value": "configure_vstp"},
                            {"label": "Configure Network Diagrams", "value": "configure_network_diagrams"},
                            {"label": "Add Track Section", "value": "add_track_section"},
                            {"label": "Remove Track Section", "value": "remove_track_section"},
                            {"label": "Configure Track Section Alerts", "value": "configure_track_section_alerts"},
                            {"label": "Advanced Settings", "value": "configure_advanced"},
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
                self._search_results = await search_stanox(query, 50)
                
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
                self._search_results = await search_stanox(query, 50)
                
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
            
            # Store rate limiting settings
            opts[CONF_TD_UPDATE_INTERVAL] = user_input.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL)
            opts[CONF_TD_MAX_BATCH_SIZE] = user_input.get(CONF_TD_MAX_BATCH_SIZE, DEFAULT_TD_MAX_BATCH_SIZE)
            opts[CONF_TD_MAX_MESSAGES_PER_SECOND] = user_input.get(CONF_TD_MAX_MESSAGES_PER_SECOND, DEFAULT_TD_MAX_MESSAGES_PER_SECOND)
            
            # Store raw JSON sensor toggle
            opts[CONF_ENABLE_TD_RAW_JSON] = user_input.get(CONF_ENABLE_TD_RAW_JSON, True)
            
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
                vol.Optional(
                    CONF_TD_UPDATE_INTERVAL,
                    default=opts.get(CONF_TD_UPDATE_INTERVAL, DEFAULT_TD_UPDATE_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=300,
                        step=0.5,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Optional(
                    CONF_TD_MAX_BATCH_SIZE,
                    default=opts.get(CONF_TD_MAX_BATCH_SIZE, DEFAULT_TD_MAX_BATCH_SIZE)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=200,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Optional(
                    CONF_TD_MAX_MESSAGES_PER_SECOND,
                    default=opts.get(CONF_TD_MAX_MESSAGES_PER_SECOND, DEFAULT_TD_MAX_MESSAGES_PER_SECOND)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=100,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Optional(
                    CONF_ENABLE_TD_RAW_JSON,
                    default=opts.get(CONF_ENABLE_TD_RAW_JSON, True)
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="configure_train_describer",
            data_schema=schema,
            description_placeholders={
                "description": "Enable Train Describer feed to track train positions through signalling berths.\n\n"
                              "**TD Areas**: Comma-separated list (e.g., 'SK, G1, RW'). Leave empty to track all areas.\n\n"
                              "**Event History Size**: Number of recent TD events kept per area (1-50, default: 10).\n\n"
                              "**Enable Raw JSON Sensor**: Creates a sensor showing raw JSON from Train Describer messages (useful for debugging, default: enabled).\n\n"
                              "**Performance Settings** (prevent GUI lockup with high-volume feeds):\n"
                              "• **Update Interval**: Minimum seconds between sensor updates (1-10s, default: 3s). Higher = less CPU usage.\n"
                              "• **Max Batch Size**: Messages collected before dispatch (10-200, default: 50). Higher = more efficient batching.\n"
                              "• **Max Messages/Second**: Rate limit threshold (5-100, default: 20). Messages beyond this are dropped with warning."
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
                station_name = await get_formatted_station_name_async(stanox) or stanox
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
        
        _LOGGER.info("async_step_add_diagram called with user_input: %s", user_input)
        _LOGGER.info("Current diagram_configs: %s", diagram_configs)
        
        if user_input is not None:
            # User selected a STANOX from search results
            if "selected_stanox" in user_input and user_input["selected_stanox"]:
                stanox = user_input["selected_stanox"]
                
                _LOGGER.info("User selected stanox: %s", stanox)
                
                # Check if diagram for this STANOX already exists
                if any(d.get("stanox") == stanox for d in diagram_configs):
                    errors["selected_stanox"] = "diagram_already_exists"
                    _LOGGER.warning("Diagram for stanox %s already exists", stanox)
                else:
                    # Add the new diagram
                    new_diagram = {
                        "stanox": stanox,
                        "enabled": user_input.get("diagram_enabled", True),
                        "range": user_input.get("diagram_range", 1),
                    }
                    _LOGGER.info("Creating new diagram:  %s", new_diagram)
                    diagram_configs.append(new_diagram)
                    opts[CONF_DIAGRAM_CONFIGS] = diagram_configs
                    
                    _LOGGER.info("Updated diagram_configs: %s", diagram_configs)
                    _LOGGER.info("Updated opts: %s", opts)
                    
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, options=opts
                    )
                    _LOGGER.info("Config entry updated, returning to configure_network_diagrams")
                    return await self.async_step_configure_network_diagrams()
            
            # User entered a search query
            if "station_query" in user_input and user_input["station_query"]:
                query = user_input["station_query"]
                _LOGGER.info("User searching for station: %s", query)
                self._search_results = await search_stanox(query, 50)
                _LOGGER.info("Search returned %d results", len(self._search_results))
                
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
            station_name = await get_formatted_station_name_async(stanox) or stanox
            
            schema = vol.Schema(
                {
                    vol.Optional(
                        "diagram_enabled",
                        default=self._diagram_to_edit.get("enabled", True)
                    ): bool,
                    vol.Optional(
                        "diagram_range",
                        default=self._diagram_to_edit.get("range", 4)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=10,
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
        diagram_options = []
        for d in diagram_configs:
            stanox = d.get('stanox', '')
            station_name = await get_formatted_station_name_async(stanox) or stanox
            diagram_options.append({
                "label": f"{station_name} ({stanox}) - Range: {d.get('range', 1)} - {'Enabled' if d.get('enabled', False) else 'Disabled'}",
                "value": stanox,
            })
        
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
        diagram_options = []
        for d in diagram_configs:
            stanox = d.get('stanox', '')
            station_name = await get_formatted_station_name_async(stanox) or stanox
            diagram_options.append({
                "label": f"{station_name} ({stanox}) - Range: {d.get('range', 1)}",
                "value": stanox,
            })
        
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
    
    async def async_step_configure_vstp(self, user_input=None) -> FlowResult:
        """Configure VSTP feed options."""
        if user_input is not None:
            opts = self.config_entry.options.copy()
            opts[CONF_ENABLE_VSTP] = user_input.get(CONF_ENABLE_VSTP, False)
            
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=opts
            )
            return self.async_create_entry(title="", data=opts)
        
        opts = self.config_entry.options
        
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLE_VSTP,
                    default=opts.get(CONF_ENABLE_VSTP, False)
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="configure_vstp",
            data_schema=schema,
            description_placeholders={
                "description": "Enable VSTP (Very Short Term Plan) feed to receive real-time train schedule data.\n\nThis provides additional information about trains including:\n- Origin and destination\n- Train category and service type\n- Scheduled platform and timing\n- Train operator\n\nVSTP data is used by Track Section Monitor to enrich train information and detect special services (freight, RHTT, steam, etc.)."
            }
        )
    
    async def async_step_add_track_section(self, user_input=None) -> FlowResult:
        """Add a new track section to monitor."""
        errors = {}
        
        if user_input is not None:
            # User selected a STANOX from search results
            if "selected_stanox" in user_input and user_input["selected_stanox"]:
                stanox = user_input["selected_stanox"]
                station_name = "Unknown"
                for result in self._search_results:
                    if result["stanox"] == stanox:
                        station_name = result["stanme"]
                        break
                
                # Store selected center station and move to next step
                self._track_section_center = {
                    "stanox": stanox,
                    "name": station_name
                }
                return await self.async_step_add_track_section_config()
            
            # User entered a search query
            if "station_query" in user_input and user_input["station_query"]:
                query = user_input["station_query"]
                self._search_results = await search_stanox(query, 50)
                
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
            step_id="add_track_section",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "description": "Search for a station to use as the center of the track section.\n\nThe track section will monitor trains passing through berths near this station."
            }
        )
    
    async def async_step_add_track_section_config(self, user_input=None) -> FlowResult:
        """Configure track section details."""
        if user_input is not None:
            opts = self.config_entry.options.copy()
            track_sections = opts.get(CONF_TRACK_SECTIONS, [])
            
            # Parse comma-separated TD areas
            td_areas_str = user_input.get("td_areas", "")
            if td_areas_str:
                td_areas = [area.strip().upper() for area in td_areas_str.split(",") if area.strip()]
            else:
                td_areas = []
            
            # Create new track section
            track_section = {
                "name": user_input.get("name"),
                "center_stanox": self._track_section_center["stanox"],
                "berth_range": user_input.get("berth_range", 3),
                "td_areas": td_areas,
                "alert_services": {
                    "freight": False,
                    "rhtt": False,
                    "steam": False,
                    "charter": False,
                    "pullman": False,
                    "royal_train": False,
                }
            }
            
            track_sections.append(track_section)
            opts[CONF_TRACK_SECTIONS] = track_sections
            
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=opts
            )
            return self.async_create_entry(title="", data=opts)
        
        center_name = self._track_section_center.get("name", "Unknown")
        center_stanox = self._track_section_center.get("stanox", "")
        
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("berth_range", default=3): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=10,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Optional("td_areas", default=""): str,
            }
        )
        
        return self.async_show_form(
            step_id="add_track_section_config",
            data_schema=schema,
            description_placeholders={
                "description": f"Configure track section centered at: {center_name} ({center_stanox})\n\n"
                               f"**Name**: Give this track section a friendly name (e.g., 'Canterbury West Platforms')\n\n"
                               f"**Berth Range**: Number of berths to monitor in each direction from the center (default: 3)\n\n"
                               f"**TD Areas**: Comma-separated list of Train Describer area IDs to monitor (e.g., 'SK, CT'). Leave empty to auto-detect from SMART data."
            }
        )
    
    async def async_step_remove_track_section(self, user_input=None) -> FlowResult:
        """Remove a track section from monitoring."""
        opts = self.config_entry.options.copy()
        track_sections = opts.get(CONF_TRACK_SECTIONS, [])
        
        if not track_sections:
            return await self.async_step_init()
        
        if user_input is not None:
            if "remove_section" in user_input and user_input["remove_section"]:
                section_name = user_input["remove_section"]
                track_sections = [s for s in track_sections if s.get("name") != section_name]
                opts[CONF_TRACK_SECTIONS] = track_sections
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=opts
                )
                return self.async_create_entry(title="", data=opts)
        
        # Build list of track sections to remove
        options = []
        for section in track_sections:
            name = section.get("name", "Unknown")
            stanox = section.get("center_stanox", "")
            station_name = await get_formatted_station_name_async(stanox) or stanox
            options.append({
                "label": f"{name} (center: {station_name} - {stanox})",
                "value": name,
            })
        
        schema = vol.Schema(
            {
                vol.Required("remove_section"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )
        
        return self.async_show_form(
            step_id="remove_track_section",
            data_schema=schema,
        )
    
    async def async_step_configure_track_section_alerts(self, user_input=None) -> FlowResult:
        """Configure which service types trigger alerts for track sections."""
        opts = self.config_entry.options.copy()
        track_sections = opts.get(CONF_TRACK_SECTIONS, [])
        
        if not track_sections:
            return await self.async_step_init()
        
        if user_input is not None:
            section_name = user_input.get("section_name")
            
            # If section_name is in user_input, we're on the selection step
            # If not, we're on the configuration step
            if section_name and not any(k.startswith("alert_") for k in user_input.keys()):
                # Selection step - move to configuration
                self._track_section_to_configure = section_name
                # Recursively call to show configuration form
                return await self.async_step_configure_track_section_alerts()
            else:
                # Configuration step - save the alert settings
                # Use stored section name from selection step
                section_name = getattr(self, "_track_section_to_configure", None)
                if not section_name:
                    return await self.async_step_init()
                
                # Find the section and update alert services
                for section in track_sections:
                    if section.get("name") == section_name:
                        section["alert_services"] = {
                            "freight": user_input.get("alert_freight", False),
                            "rhtt": user_input.get("alert_rhtt", False),
                            "steam": user_input.get("alert_steam", False),
                            "charter": user_input.get("alert_charter", False),
                            "pullman": user_input.get("alert_pullman", False),
                            "royal_train": user_input.get("alert_royal_train", False),
                        }
                        break
                
                opts[CONF_TRACK_SECTIONS] = track_sections
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=opts
                )
                # Clear the stored section name
                self._track_section_to_configure = None
                return self.async_create_entry(title="", data=opts)
        
        # Check if we're on selection step or configuration step
        if not hasattr(self, "_track_section_to_configure") or self._track_section_to_configure is None:
            # Selection step: show list of sections to choose from
            options = []
            for section in track_sections:
                name = section.get("name", "Unknown")
                stanox = section.get("center_stanox", "")
                station_name = await get_formatted_station_name_async(stanox) or stanox
                options.append({
                    "label": f"{name} (center: {station_name})",
                    "value": name,
                })
            
            schema = vol.Schema(
                {
                    vol.Required("section_name"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            )
            
            return self.async_show_form(
                step_id="configure_track_section_alerts",
                data_schema=schema,
                description_placeholders={
                    "description": "Select a track section to configure alert settings."
                }
            )
        
        # Configuration step: show alert settings for selected section
        section_name = self._track_section_to_configure
        section = next((s for s in track_sections if s.get("name") == section_name), None)
        
        if not section:
            # Section not found, reset and go back
            self._track_section_to_configure = None
            return await self.async_step_init()
        
        alert_services = section.get("alert_services", {})
        
        schema = vol.Schema(
            {
                vol.Optional("alert_freight", default=alert_services.get("freight", False)): bool,
                vol.Optional("alert_rhtt", default=alert_services.get("rhtt", False)): bool,
                vol.Optional("alert_steam", default=alert_services.get("steam", False)): bool,
                vol.Optional("alert_charter", default=alert_services.get("charter", False)): bool,
                vol.Optional("alert_pullman", default=alert_services.get("pullman", False)): bool,
                vol.Optional("alert_royal_train", default=alert_services.get("royal_train", False)): bool,
            }
        )
        
        stanox = section.get("center_stanox", "")
        station_name = await get_formatted_station_name_async(stanox) or stanox
        
        return self.async_show_form(
            step_id="configure_track_section_alerts",
            data_schema=schema,
            description_placeholders={
                "description": f"Configure alert triggers for: {section_name} ({station_name})\n\n"
                               f"Select which service types should trigger alerts:\n\n"
                               f"**Freight**: All freight trains (0xxx, 4xxx, 6xxx, 7xxx headcodes)\n"
                               f"**RHTT**: Rail Head Treatment Trains (3Hxx, 3Yxx headcodes)\n"
                               f"**Steam**: Steam charter services (often 1Zxx headcodes)\n"
                               f"**Charter**: General charter/special services (1Zxx headcodes)\n"
                               f"**Pullman**: Luxury/Pullman services\n"
                               f"**Royal Train**: Royal train services (1X99 headcode)"
            }
        )
    
    async def async_step_configure_advanced(self, user_input=None) -> FlowResult:
        """Configure advanced settings (debug sensor, etc)."""
        if user_input is not None:
            opts = self.config_entry.options.copy()
            opts[CONF_ENABLE_DEBUG_SENSOR] = user_input.get(CONF_ENABLE_DEBUG_SENSOR, True)
            
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=opts
            )
            return self.async_create_entry(title="", data=opts)
        
        opts = self.config_entry.options
        
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLE_DEBUG_SENSOR,
                    default=opts.get(CONF_ENABLE_DEBUG_SENSOR, True)
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="configure_advanced",
            data_schema=schema,
            description_placeholders={
                "description": "Configure advanced integration settings.\n\n"
                              "**Enable Debug Log Sensor**: Creates a sensor showing recent debug logs in the UI (default: enabled).\n\n"
                              "Note: Disabling this sensor will reduce entity count but debug logs will still appear in Home Assistant logs."
            }
        )
