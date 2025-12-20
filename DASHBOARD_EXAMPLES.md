# Dashboard Examples

This document provides examples of how to display train movement information on your Home Assistant dashboard using the decoded attributes.

## Understanding Entity IDs

After configuring stations in the integration, entities are created with the format:
- **Station sensors**: `sensor.network_rail_integration_<station_name>` (e.g., `sensor.network_rail_integration_euston`)
- **Last movement sensor**: `sensor.network_rail_integration_last_movement`
- **Connection status**: `binary_sensor.network_rail_integration_feed_connected`

Replace `<station_name>` in the examples below with your actual station name (lowercased and with spaces replaced by underscores).

## Basic Entity Card

Display the last train movement with key information:

```yaml
type: entity
entity: sensor.network_rail_integration_euston
name: Last Train at Euston
```

## Entities Card with Attributes

Show detailed information about the last train movement:

```yaml
type: entities
entities:
  - entity: sensor.network_rail_integration_euston
    name: Euston Station
    secondary_info: last-changed
    type: attribute
    attribute: event_type
  - type: attribute
    entity: sensor.network_rail_integration_euston
    attribute: toc_name
    name: Operator
  - type: attribute
    entity: sensor.network_rail_integration_euston
    attribute: platform
    name: Platform
  - type: attribute
    entity: sensor.network_rail_integration_euston
    attribute: direction_description
    name: Direction
  - type: attribute
    entity: sensor.network_rail_integration_euston
    attribute: actual_time_local
    name: Time
  - type: attribute
    entity: sensor.network_rail_integration_euston
    attribute: variation_status
    name: Status
```

## Glance Card for Multiple Stations

Monitor multiple stations at once:

```yaml
type: glance
title: Train Arrivals
entities:
  - entity: sensor.network_rail_integration_euston
    name: Euston
  - entity: sensor.network_rail_integration_kings_cross
    name: Kings Cross
  - entity: sensor.network_rail_integration_paddington
    name: Paddington
show_state: true
show_name: true
```

## Markdown Card with Template

Create a custom display using templates:

```yaml
type: markdown
content: |
  ## {{ state_attr('sensor.network_rail_integration_euston', 'station_name') or 'Euston' }}
  
  **Last Train:** {{ states('sensor.network_rail_integration_euston') }}
  
  **Platform:** {{ state_attr('sensor.network_rail_integration_euston', 'platform') or 'Not specified' }}
  
  **Operator:** {{ state_attr('sensor.network_rail_integration_euston', 'toc_name') }}
  
  **Direction:** {{ state_attr('sensor.network_rail_integration_euston', 'direction_description') }}
  
  **Time:** {{ state_attr('sensor.network_rail_integration_euston', 'actual_time_local') }}
  
  **Status:** {{ state_attr('sensor.network_rail_integration_euston', 'variation_status') }}
  {% if state_attr('sensor.network_rail_integration_euston', 'timetable_variation') %}
  ({{ state_attr('sensor.network_rail_integration_euston', 'timetable_variation') }} min)
  {% endif %}
```

## Auto-entities Card for Dynamic Display

Automatically show all tracked stations (requires HACS `auto-entities` card):

```yaml
type: custom:auto-entities
card:
  type: entities
  title: All Tracked Stations
filter:
  include:
    - entity_id: sensor.network_rail_integration_*
      not:
        entity_id: sensor.network_rail_integration_last_movement
show_empty: false
sort:
  method: name
```

## Platform-Specific Information Card

Focus on platform and direction information:

```yaml
type: tile
entity: sensor.network_rail_integration_euston
name: Euston Platform Info
icon: mdi:train
vertical: false
```

Or use an entities card for more detail:

```yaml
type: entities
title: Euston Platform Info
entities:
  - entity: sensor.network_rail_integration_euston
    name: Last Movement
    icon: mdi:train
  - type: attribute
    entity: sensor.network_rail_integration_euston
    attribute: platform
    name: Platform
  - type: attribute
    entity: sensor.network_rail_integration_euston
    attribute: direction_description
    name: Direction
```

## Conditional Card for Active Trains

Only show when there's recent activity:

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.network_rail_integration_euston
    state_not: unavailable
  - condition: state
    entity: sensor.network_rail_integration_euston
    state_not: unknown
card:
  type: entities
  title: Euston - Last Movement
  entities:
    - entity: sensor.network_rail_integration_euston
      name: Event Type
    - type: attribute
      entity: sensor.network_rail_integration_euston
      attribute: toc_name
      name: Operator
    - type: attribute
      entity: sensor.network_rail_integration_euston
      attribute: platform
      name: Platform
```

## Feed Connection Status

Monitor the connection to Network Rail's feed:

```yaml
type: entity
entity: binary_sensor.network_rail_integration_feed_connected
name: Network Rail Connection
icon: mdi:lan-connect
```

## Using Attributes in Automations

You can also use these attributes in automations:

```yaml
automation:
  - alias: "Notify when train arrives at platform"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_euston
    condition:
      - condition: template
        value_template: "{{ state_attr('sensor.network_rail_integration_euston', 'event_type') == 'ARRIVAL' }}"
      - condition: template
        value_template: "{{ state_attr('sensor.network_rail_integration_euston', 'platform') != None }}"
    action:
      - service: notify.mobile_app
        data:
          title: "Train Arrival"
          message: >
            {{ state_attr('sensor.network_rail_integration_euston', 'toc_name') }} train 
            arriving at platform {{ state_attr('sensor.network_rail_integration_euston', 'platform') }}
            heading {{ state_attr('sensor.network_rail_integration_euston', 'direction_description') }}
```

## Available Attributes Reference

All sensors expose these attributes:

### Platform & Direction
- `platform` - Platform number (e.g., "3", "4A")
- `direction_ind` - Raw code (U/D)
- `direction_description` - Human-readable (e.g., "UP (towards London)")

### Operator
- `toc_id` - Raw TOC code (e.g., "79")
- `toc_name` - Operator name (e.g., "c2c")

### Location
- `loc_stanox` - Location code
- `location_name` - Station name (e.g., "EUSTON")
- `station_name` - Configured name (station sensors only)

### Timing
- `event_type` - ARRIVAL, DEPARTURE, PASS
- `planned_time_local` - Scheduled time
- `actual_time_local` - Actual time
- `timetable_variation` - Minutes early/late
- `variation_status` - ON TIME, EARLY, LATE, OFF ROUTE

### Other
- `train_id` - Unique identifier
- `line_ind` - Raw line code
- `line_description` - Line name (e.g., "Fast line")
- `train_terminated` - Boolean
