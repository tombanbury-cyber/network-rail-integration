# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.15.0] - 2026-01-08

### Added - Phase 1: Enhanced Network Diagram Berth Topology with Station Attribution

- **Sequential Berth Lists**: Network Diagrams now include `up_berths` and `down_berths` attributes
  - Complete ordered lists of ALL berths in the specified range
  - Follows actual track topology using SMART berth connection data
  - Includes station attribution (`stanox`, `stanme`) for each berth
  - Shows which berths are at stations vs. between stations
  - Enables building detailed topological diagrams like Herne Bay example
  
- **Station Attribution**: Enhanced berth objects with station identification
  - `stanox`: STANOX code if berth is at a station, `null` if between stations
  - `stanme`: Station name if berth is at a station, `null` if between stations
  - Applied to `center_berths`, `up_berths`, `down_berths`, and station berths in `up_stations`/`down_stations`
  
- **New Utility Function**: `get_sequential_berths()` in `smart_utils.py`
  - Implements breadth-first traversal of berth connections
  - Supports "up" and "down" directions
  - Configurable maximum berths to collect
  - Includes platform information when available

### Changed

- **Backward Compatible**: All existing attributes and fields remain unchanged
  - Existing dashboard cards and automations continue to work
  - New attributes are additions only, no breaking changes
  - Sensor state (occupied berth count) unchanged

### Documentation

- Updated [NETWORK_DIAGRAMS.md](NETWORK_DIAGRAMS.md) with Phase 1 sequential berth documentation
- Added examples showing how to use `up_berths` and `down_berths` in templates
- Added visual example of station attribution in berth lists

## [1.14.0] - 2026-01-07

### Added
- **Network Diagrams with Alerts**: Merged Track Section Monitor functionality into Network Diagrams
  - Network Diagrams now support intelligent train tracking and alerts
  - Configurable alert types: freight, RHTT, steam, charter, pullman, royal train
  - VSTP schedule enrichment for trains in diagram areas
  - Per-train attributes including origin, destination, operator, service type
  - Time tracking for trains in diagram area
  - Home Assistant event firing (`homeassistant_network_rail_uk_track_alert`) when alert trains enter diagram
  - Alert configuration in diagram add/edit flows
  
### Changed
- **Network Diagram Configuration**: Enhanced with alert service checkboxes
  - Alert services can be enabled per diagram during creation or editing
  - Alert configuration is optional - diagrams work as before if alerts are disabled
  - Diagram range increased to support 1-10 stations (previously 1-5)
  
### Enhanced
- **NetworkDiagramSensor**: Extended to include train tracking capabilities
  - Added `trains_in_diagram` attribute when alerts are enabled
  - Added `total_trains` and `alert_trains` counts
  - Added `alert_services_enabled` configuration display
  - Integration with VSTP manager for schedule enrichment
  - Per-train details including time in area, berths visited, and service classification
  
### Documentation
- Updated [NETWORK_DIAGRAMS.md](NETWORK_DIAGRAMS.md) with alert configuration and automation examples
- Updated [README.md](README.md) to highlight unified functionality
- Added automation examples for diagram alerts
- Added dashboard examples showing alert trains

### Notes
- Track Section Monitor remains available for backward compatibility
- Existing Track Section configurations continue to work unchanged
- For new setups, Network Diagrams with alerts are recommended for most use cases
- Alerts require VSTP feed to be enabled for service classification

## [1.12.0] - 2025-12-29

### Added
- **Track Section Monitor**: Comprehensive feature for monitoring trains along defined track sections
  - Real-time train tracking through Train Describer berth data
  - Automatic service classification (freight, passenger, ECS, RHTT, steam, charter, royal train)
  - VSTP schedule enrichment with origin, destination, operator, and timing data
  - Configurable alerts for specific service types (freight, RHTT, steam, pullman, royal train)
  - Home Assistant event system (`homeassistant_network_rail_uk_track_alert`) for automation
  - Multiple concurrent track section monitoring
  - See [TRACK_SECTION_MONITOR.md](TRACK_SECTION_MONITOR.md) for full documentation

- **VSTP Feed Support**: Very Short Term Plan schedule data integration
  - Subscribe to `VSTP_ALL` topic via STOMP
  - Parse and store VSTP schedule messages (CIF format in JSON)
  - Index schedules by train_uid and headcode
  - Automatic schedule validity checking for current day
  - Schedule lookup methods for correlating live trains with schedules

- **Service Classification Module** (`service_classifier.py`):
  - Train category classification from VSTP CIF codes
  - Headcode pattern matching for service identification
  - Special service detection (RHTT, steam, royal train, named trains, pullman)
  - Support for both VSTP category codes and headcode-based detection
  - Freight train detection (0xxx, 4xxx, 6xxx, 7xxx patterns)
  - Charter train detection (1Zxx patterns)
  - Empty coaching stock detection (5xxx patterns)

- **VSTP Manager Module** (`vstp_manager.py`):
  - VstpManager class for VSTP schedule management
  - Schedule caching with automatic daily cleanup
  - Schedule indexing by train UID and headcode
  - Origin/destination extraction from schedules
  - Next scheduled stop calculation

- **Configuration Flow Enhancements**:
  - "Configure VSTP Feed" menu option to enable/disable VSTP subscription
  - "Add Track Section" multi-step wizard (station search → configuration)
  - "Remove Track Section" for managing configured sections
  - "Configure Track Section Alerts" for per-section alert settings
  - Alert service type selectors (freight, RHTT, steam, charter, pullman, royal train)

- **New Constants**:
  - `CONF_ENABLE_VSTP`: Enable VSTP feed
  - `CONF_TRACK_SECTIONS`: Track section configurations
  - `CONF_TRACK_SECTION_*`: Track section configuration keys
  - `DEFAULT_VSTP_TOPIC`: VSTP_ALL topic
  - `DISPATCH_VSTP`: VSTP message dispatcher
  - `DISPATCH_TRACK_SECTION`: Track section event dispatcher

- **TrackSectionSensor Entity**:
  - Tracks trains entering, moving through, and leaving defined sections
  - State: Number of trains currently in section
  - Rich attributes: trains list with service details, section config, alert counts
  - Integration with VSTP manager for schedule enrichment
  - Automatic SMART data berth calculation
  - Event firing for matching alert services

### Changed
- **Hub**: Added VSTP topic subscription (subscription ID 3)
- **Hub**: VSTP message routing to VstpManager
- **Hub**: Message handling now checks VSTP first, then TD, then train movements
- **Init**: Initialize VSTP manager when enabled in options
- **Sensor**: Register TrackSectionSensor entities for each configured section
- **Manifest**: Version bumped to 1.12.0

### Technical Details
- VSTP messages processed in real-time via STOMP subscription
- Schedule data indexed in memory for fast lookups
- Service classification uses both VSTP CIF categories and headcode patterns
- Track sections calculate berths using SMART topology data
- Events fired asynchronously for automation triggers
- All new features are optional and backwards compatible

## [1.11.2] - 2025-12-23

### Fixed
- **Train Describer List-Format Messages**: Fixed issue where Train Describer messages arriving in list format were not being received
  - TD messages from Network Rail arrive in list format (similar to train movements), not as bare dicts
  - Previously, the code only checked for TD messages when payload was a bare dict, missing list-wrapped TD messages
  - Added detection logic to identify and process TD messages within lists by checking for keys ending in `_MSG`
  - Each TD message in the list is now validated and processed through `_handle_td_message()`
  - Debug logging now shows "Received list with TD messages" when list-format TD messages are detected
  - This fix enables TD sensors to populate with berth occupancy data and display message counts correctly

## [1.11.0] - 2025-12-22

### Changed
- **BREAKING CHANGE**: Removed TD Platforms configuration feature
  - The platform configuration UI (Configure TD Platforms) has been removed
  - All platforms in configured TD areas are now automatically tracked
  - The `selected_platforms` attribute has been removed from TD area sensors
  - Platform and event filtering is now done in templates/automations for maximum flexibility
  - Existing configurations with platform settings will continue to work (settings are ignored)
  
### Removed
- `CONF_TD_PLATFORMS` configuration constant
- `DEFAULT_PLATFORM_RANGE_MIN` and `DEFAULT_PLATFORM_RANGE_MAX` constants
- `async_step_configure_td_platforms()` config flow method
- Platform filtering from `get_event_history()` and `get_all_platform_states()` methods
- `initialize_platform_states()` method from BerthState class

### Migration Guide
- No action required - existing installations will continue to work
- Remove any references to `selected_platforms` attribute in your templates/automations
- Update templates to filter platforms as needed using Jinja2 filters:
  ```yaml
  # Old (no longer available):
  {{ state_attr('sensor.td_area_sk', 'selected_platforms') }}
  
  # New (filter in template):
  {% set events = state_attr('sensor.td_area_sk', 'recent_events') %}
  {{ events | selectattr('to_platform', 'in', ['1', '2', '3']) | list }}
  ```

## [1.6.2] - 2025-12-21

### Fixed
- **Train Movement Data Reception**: Fixed issue where train movement data was not being processed when Train Describer feed was enabled
  - Previously, when a dict payload was received, the code assumed it was always a Train Describer message
  - If the dict was not a valid TD message, the handler would return without processing other message types
  - Now, if a dict payload is not a valid TD message, processing continues to handle it as other message types
  - This ensures train movement messages in dict format are not incorrectly filtered out
- Improved message handling logic to properly distinguish between TD messages and other dict payloads

## [1.6.0] - 2025-12-21

### Added
- **Debug Log Sensor**: New sensor entity that displays recent log messages within the Home Assistant UI
  - Shows the last 50 log entries in a circular buffer
  - Displays most recent log entry as the sensor state
  - Exposes all log entries via entity attributes with timestamp, level, and message
  - Makes debugging connection and subscription issues easier without checking log files
- New `debug_log.py` module with:
  - `DebugLogSensor` entity class for displaying logs in the UI
  - `DebugLogger` helper class that wraps the standard Python logger
  - Support for DEBUG, INFO, WARNING, and ERROR log levels
- Enhanced logging throughout the integration with dual output to both standard logs and debug sensor
- Updated README with Debug Log Sensor documentation section

### Changed
- Updated key logging calls in `hub.py` to use the new debug logger
- Improved integration initialization to connect debug sensor after platform setup

## [1.5.0] - 2024-12-20

### Added
- **Train Describer feed support**: Subscribe to Network Rail's Train Describer (TD) feed to track train positions through signalling berths
- New configuration option to enable/disable Train Describer feed
- TD area filtering to track specific signalling areas
- New sensors:
  - `sensor.network_rail_integration_train_describer_status` - Overall TD status and statistics
  - `sensor.network_rail_integration_td_area_<area_id>` - Area-specific sensors with berth occupancy data
- Berth state tracking for creating live network diagrams
- Support for all TD message types:
  - C-Class: CA (berth step), CB (berth cancel), CC (berth interpose), CT (heartbeat)
  - S-Class: SF (signalling update), SG (signalling refresh), SH (signalling refresh finished)
- Comprehensive Train Describer documentation in `TRAIN_DESCRIBER.md`
- New `td_parser.py` module for parsing and filtering TD messages
- Area-specific event dispatching for TD messages

### Changed
- Updated README with Train Describer feature information
- Updated configuration flow to include Train Describer options
- Enhanced hub to support multiple concurrent STOMP subscriptions
- Improved sensor setup to dynamically create TD sensors when enabled

### Technical Details
- Topic: `TD_ALL_SIG_AREA` for Train Describer messages
- Dual subscription support: Train Movements + Train Describer
- In-memory berth state tracking with efficient updates
- Area-based filtering to reduce message volume

## [1.4.0] - Previous Release

### Changed
- Standardized entity naming convention to `sensor.network_rail_integration_<name>`
- Improved station sensor naming with slugified station names

## [1.3.0] - Previous Release

### Added
- Multi-station tracking support
- Station search functionality with STANOX database
- Per-station sensor entities

## [1.2.0] - Previous Release

### Added
- Global filters for TOC and event types
- Configurable options via config flow

## [1.1.0] - Previous Release

### Added
- Binary sensor for feed connection status
- Enhanced attributes for train movements

## [1.0.0] - Initial Release

### Added
- Basic train movement tracking
- STOMP connection to Network Rail
- Last movement sensor
