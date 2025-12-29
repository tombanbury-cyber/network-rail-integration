# Network Rail – Home Assistant Integration

Connects to Network Rail's public **STOMP** broker and subscribes to:
- **Train Movements** (default topic: `TRAIN_MVT_ALL_TOC`) - Real-time train arrival, departure, and passing events
- **Train Describer** (optional topic: `TD_ALL_SIG_AREA`) - Real-time signalling berth occupancy for network diagrams
- **VSTP** (optional topic: `VSTP_ALL`) - Very Short Term Plan schedule data for train enrichment (NEW in v1.12.0)
- **SMART Data** (NEW in v1.7.0) - Berth topology data for creating Traksy-style network diagrams

## Features

### Train Movements Feed
Track train movements at specific stations with detailed arrival/departure information, platform numbers, train operating companies, and timing data.

### Train Describer Feed (Enhanced in v1.8.0)
Monitor train positions through signalling berths for creating live railway network diagrams. **NEW in v1.8.0**: Track multiple platforms simultaneously with configurable event history. See [TRAIN_DESCRIBER.md](TRAIN_DESCRIBER.md) for details.

### Network Diagrams (NEW in v1.7.0)
Visualize train positions on a map of berth connections showing adjacent stations and real-time occupancy. Uses Network Rail's SMART data to build topology graphs. See [NETWORK_DIAGRAMS.md](NETWORK_DIAGRAMS.md) for detailed documentation.

### Track Section Monitor (NEW in v1.12.0)
Monitor trains along defined track sections with intelligent service classification and alerts. Enriched with VSTP schedule data to identify freight, RHTT, steam specials, and named trains. Fire Home Assistant events when specific service types enter your monitored sections. See [TRACK_SECTION_MONITOR.md](TRACK_SECTION_MONITOR.md) for comprehensive documentation.

**Key capabilities:**
- Real-time train tracking through signalling berths
- Automatic service classification (freight, passenger, ECS, RHTT, steam, charter)
- Configurable alerts for specific train types
- VSTP schedule enrichment (origin, destination, operator, timing)
- Home Assistant event triggers for automation
- Multiple concurrent track sections

## Entities

The integration creates the following entities:

### Train Movements
- **Binary sensor**: `binary_sensor.network_rail_integration_feed_connected` - Connection status to Network Rail feed
- **Sensor**: `sensor.network_rail_integration_last_movement` - Last movement seen across all stations
- **Sensor (per station)**: `sensor.network_rail_integration_<station_name>` - Last movement for each configured station

### Train Describer (when enabled)
- **Sensor**: `sensor.network_rail_integration_train_describer_status` - Overall TD status and statistics
- **Sensor (per area)**: `sensor.network_rail_integration_td_area_<area_id>` - Berth occupancy and platform tracking for specific TD areas (NEW in v1.8.0: includes platform states and event history)

### Network Diagrams (NEW in v1.7.0, when enabled)
- **Sensor**: `sensor.network_rail_integration_diagram_<stanox>` - Network diagram showing berth occupancy at a station and adjacent stations

### Track Section Monitor (NEW in v1.12.0, when configured)
- **Sensor (per section)**: `sensor.network_rail_integration_track_section_<section_name>` - Trains currently in the monitored track section with service classification and timing data

### Debug and Diagnostics
- **Sensor**: `sensor.network_rail_integration_debug_log` - Recent log messages for debugging (shows last 50 entries)

See [TRAIN_DESCRIBER.md](TRAIN_DESCRIBER.md) for more information about the Train Describer feed and multi-platform tracking.
See [TRACK_SECTION_MONITOR.md](TRACK_SECTION_MONITOR.md) for comprehensive Track Section Monitor documentation.

### Entity Naming

Starting from version 1.4.0, all entities follow the format `sensor.network_rail_integration_<name>` where `<name>` is the slugified station name (lowercase with spaces replaced by underscores).

**Examples:**
- Canterbury West → `sensor.network_rail_integration_canterbury_west`
- Euston → `sensor.network_rail_integration_euston`
- Kings Cross → `sensor.network_rail_integration_kings_cross`

**Note for upgrading users:** If you're upgrading from version 1.3.0 or earlier, you'll need to update your dashboard configurations and automations to use the new entity IDs. See [DASHBOARD_EXAMPLES.md](DASHBOARD_EXAMPLES.md) for updated examples.

### Available Attributes

Each sensor exposes detailed attributes about train movements that can be displayed on your dashboard:

**Platform and Direction Information:**
- `platform`: The platform number where the train is arriving/departing (e.g., "3", "4A")
- `direction_ind`: Raw direction code (U/D)
- `direction_description`: Human-readable direction (e.g., "UP (towards London)", "DOWN (away from London)")

**Train Operating Company:**
- `toc_id`: Raw TOC code (e.g., "79")
- `toc_name`: Train operator name (e.g., "c2c", "Great Western Railway", "ScotRail")

**Location Information:**
- `loc_stanox`: Station STANOX code
- `location_name`: Station name (e.g., "EUSTON", "MANCR PIC")
- `station_name`: Configured station name (station sensors only)

**Timing Information:**
- `event_type`: ARRIVAL, DEPARTURE, or PASS
- `planned_time_local`: Scheduled time in local timezone
- `actual_time_local`: Actual time in local timezone
- `timetable_variation`: Minutes early/late
- `variation_status`: ON TIME, EARLY, LATE, or OFF ROUTE

**Additional Details:**
- `train_id`: Unique train identifier
- `line_ind`: Raw line code
- `line_description`: Line description (e.g., "Fast line", "Slow line")
- `train_terminated`: Whether the train terminated at this location

These attributes allow you to create rich dashboard displays showing which trains are arriving at which platforms and in which direction they're traveling.

## Install (HACS)

1. Add this repository in HACS as a **Custom repository** (category: Integration).
2. Install.
3. Restart Home Assistant.
4. Add via **Settings → Devices & services → Add integration → Network Rail Integration**.

## Configuration

After adding the integration, open **Configure** to manage stations and filters:

### Managing Stations

You can track multiple stations simultaneously. Each configured station will have its own sensor entity showing the last train movement for that station.

**To add a station:**
1. Open the integration configuration
2. Select "Add Station"
3. Search for your station by name (e.g., "EUSTON", "MANC", "PADD")
4. Select the station from the search results
5. A new sensor entity will be created for that station

**To remove a station:**
1. Open the integration configuration
2. Select "Remove Station"
3. Choose the station to remove from the list
4. The corresponding sensor entity will be removed

### Global Filters

These filters apply to all tracked stations:

- `toc_filter`: Only keep movements for a single `toc_id`
- `event_types`: Only keep movements whose `event_type` is in the list (e.g., ARRIVAL, DEPARTURE)

Configure these via **Configure Filters (TOC, Event Types)** in the options menu.

### Configuring Train Describer

To enable Train Describer feed:

1. Open the integration configuration
2. Select "Configure Train Describer"
3. Enable the "Enable Train Describer Feed" checkbox
4. Optionally specify TD area IDs (comma-separated) to track specific areas
5. Set the event history size (default: 10, range: 1-50) to control how many recent events are kept
6. Save the configuration

See [TRAIN_DESCRIBER.md](TRAIN_DESCRIBER.md) for detailed information about the Train Describer feature.

**Note:** All platforms in configured TD areas are automatically tracked. You can filter platforms in your templates and automations for maximum flexibility. See [AUTOMATION_EXAMPLES.md](AUTOMATION_EXAMPLES.md) for examples.

### Configuring Network Diagrams (NEW in v1.7.0)

To enable Network Diagram sensor:

1. Open the integration configuration
2. Select "Configure Network Diagrams"
3. Enable the "Enable Network Diagrams" checkbox
4. Search for a station to use as the center of the diagram
5. Set the range (number of stations in each direction to include, 1-5)
6. Save the configuration

The Network Diagram sensor will:
- Show the count of occupied berths as its state
- Provide detailed attributes with berth occupancy for the center station and adjacent stations
- Update in real-time as trains move through berths
- Use SMART data to understand berth topology

See [NETWORK_DIAGRAMS.md](NETWORK_DIAGRAMS.md) for detailed information about creating network diagrams and using SMART data.

### Finding STANOX Codes

STANOX codes are unique identifiers for railway locations in the UK. This integration includes a searchable database of over 11,000 STANOX codes to help you find the right one:

1. In the integration options, check the **"Search for station by name"** box and save
2. You'll be taken to the search screen
3. Enter any part of a station name - note that station names are often abbreviated:
   - "EUSTON" finds London Euston (72410)
   - "MANC" finds Manchester stations (e.g., MANCR PIC - 32000)
   - "PADD" finds Paddington stations (e.g., PADDINGTN - 73000)
   - "LEEDS" finds Leeds stations
   - You can also enter the STANOX code directly to verify it
4. Select the station from the search results (up to 50 matches shown)
5. The STANOX code will be automatically set

## Services

The integration provides the following services:

### `network_rail_integration.refresh_smart_data`

Manually download and refresh SMART berth topology data used for network diagrams.

**Parameters**: None

**Example**:
```yaml
service: network_rail_integration.refresh_smart_data
```

This service is useful for:
- Forcing a refresh before the 30-day cache expires
- Recovering from a failed initial download  
- Updating after Network Rail publishes new SMART data

## Logging

To enable detailed logging in your Home Assistant logs:

```yaml
logger:
  default: info
  logs:
    network_rail_integration: debug
```

## Debug Log Sensor

The integration includes a debug log sensor (`sensor.network_rail_integration_debug_log`) that displays recent log messages directly in the Home Assistant UI. This makes it easier to debug connection issues and monitor the integration's activity without checking log files.

**Features:**
- Shows the most recent log message as the sensor state
- Stores the last 50 log entries (accessible via entity attributes)
- Includes timestamp, log level (DEBUG, INFO, WARNING, ERROR), and message for each entry
- Automatically captures key events like connection status, subscription updates, and errors

**Viewing the Debug Log:**
1. Go to **Settings → Devices & services → Network Rail Integration**
2. Click on the device to view its entities
3. Find `sensor.network_rail_integration_debug_log`
4. Click on the sensor to view all recent log entries in the attributes

This sensor is particularly useful for:
- Monitoring connection status to Network Rail feeds
- Debugging subscription issues
- Tracking when the integration receives data
- Identifying errors without needing SSH or file access
