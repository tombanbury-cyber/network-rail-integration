# Dashboard Examples

This document provides examples of how to display train movement information on your Home Assistant dashboard using the decoded attributes.

## Basic Entity Card

Display the last train movement with key information:

```yaml
type: entity
entity: sensor.network_rail_integration_euston
attribute: platform
name: Last Train at Euston
```

## Entity Card with Attributes

Show detailed information about the last train movement:

```yaml
type: entity
entity: sensor.network_rail_integration_euston
secondary_info: none
state_attribute: event_type
card_mod:
  style: |
    :host {
      --paper-item-icon-color: {% if is_state_attr('sensor.network_rail_integration_euston', 'variation_status', 'ON TIME') %} green {% elif is_state_attr('sensor.network_rail_integration_euston', 'variation_status', 'LATE') %} red {% else %} orange {% endif %};
    }
footer:
  type: attribute-list
  entity: sensor.network_rail_integration_euston
  attributes:
    - toc_name
    - platform
    - direction_description
    - actual_time_local
    - variation_status
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
  ## {{ state_attr('sensor.network_rail_integration_euston', 'station_name') }}
  
  **Last Train:** {{ state_attr('sensor.network_rail_integration_euston', 'event_type') }}
  
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

Automatically show all tracked stations:

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
  exclude: []
sort:
  method: name
```

## Platform-Specific Information Card

Focus on platform and direction information:

```yaml
type: entity
entity: sensor.network_rail_integration_euston
name: Euston Platform Info
secondary_info: |
  Platform {{ state_attr('sensor.network_rail_integration_euston', 'platform') or 'TBA' }} - 
  {{ state_attr('sensor.network_rail_integration_euston', 'direction_description') }}
icon: mdi:train
```

## Conditional Card for Active Trains

Only show when there's recent activity:

```yaml
type: conditional
conditions:
  - entity: sensor.network_rail_integration_euston
    state_not: unavailable
card:
  type: entity
  entity: sensor.network_rail_integration_euston
  name: Euston - Last Movement
  secondary_info: |
    {{ state_attr('sensor.network_rail_integration_euston', 'toc_name') }} - 
    Platform {{ state_attr('sensor.network_rail_integration_euston', 'platform') or 'TBA' }}
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
