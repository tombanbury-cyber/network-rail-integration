# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
