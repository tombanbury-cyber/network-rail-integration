# Network Rail Integration – Home Assistant Integration

Connects to Network Rail's public **STOMP** broker and subscribes to **Train Movements** (default topic: `TRAIN_MVT_ALL_TOC`).

## Entities

- **Binary sensor**: Feed connected
- **Sensor**: Last movement (state = `event_type`, with useful attributes)
- **Sensor (per station)**: One sensor per configured station showing movements for that specific station

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

## Logging

```yaml
logger:
  default: info
  logs:
    network_rail_integration: debug
```
