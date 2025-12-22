# Automation Examples

This document provides practical examples for creating automations using the Network Rail Integration, including platform tracking features.

## Platform-Based Automations

### Notify When Train Arrives at Specific Platform

Get a notification when a train arrives at Platform 1:

```yaml
automation:
  - alias: "Train Arrival - Platform 1"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_td_area_sk
    condition:
      - condition: template
        value_template: >
          {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
          {{ platforms is not none and '1' in platforms and 
             platforms['1'].current_event == 'arrive' and
             platforms['1'].status == 'active' }}
    action:
      - service: notify.mobile_app
        data:
          title: "Train Arriving"
          message: >
            Train {{ state_attr('sensor.network_rail_integration_td_area_sk', 'platforms')['1'].current_train }}
            is arriving at Platform 1
```

### Monitor Multiple Platforms

Get notified when trains arrive at any of several platforms:

```yaml
automation:
  - alias: "Train Arrivals - Platforms 1-3"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_td_area_sk
    condition:
      - condition: template
        value_template: >
          {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
          {% if platforms %}
            {% set platform_list = ['1', '2', '3'] %}
            {% set active_platforms = platform_list | select('in', platforms) | 
               select('match', '^.*$') | list %}
            {{ active_platforms | length > 0 and 
               active_platforms | map('extract', platforms) | 
               selectattr('status', 'equalto', 'active') | list | length > 0 }}
          {% else %}
            false
          {% endif %}
    action:
      - service: notify.mobile_app
        data:
          title: "Train Activity"
          message: >
            {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
            {% set platform_list = ['1', '2', '3'] %}
            {% set active = [] %}
            {% for p_id in platform_list %}
              {% if p_id in platforms and platforms[p_id].status == 'active' %}
                {% set active = active + [p_id] %}
              {% endif %}
            {% endfor %}
            Platform(s) {{ active | join(', ') }} active
```

### Track Platform Departures

Detect when a train departs from a platform (platform becomes idle after being active):

```yaml
automation:
  - alias: "Train Departure - Platform 2"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_td_area_sk
    condition:
      - condition: template
        value_template: >
          {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
          {{ platforms is not none and '2' in platforms and 
             platforms['2'].status == 'idle' and
             platforms['2'].current_train == none }}
    action:
      - service: notify.mobile_app
        data:
          title: "Platform Clear"
          message: "Platform 2 is now clear"
```

## Event History Automations

### Recent Activity Summary

Create a summary of recent train activity:

```yaml
automation:
  - alias: "Hourly Train Activity Summary"
    trigger:
      - platform: time_pattern
        hours: "*"
    action:
      - service: notify.mobile_app
        data:
          title: "Train Activity Summary"
          message: >
            {% set events = state_attr('sensor.network_rail_integration_td_area_sk', 'recent_events') %}
            {% if events %}
              {{ events | length }} events in the last hour.
              Last event: Train {{ events[-1].train_id }} - {{ events[-1].event_type }}
            {% else %}
              No recent activity
            {% endif %}
```

### Detect Train Movements Between Specific Platforms

Track trains moving from Platform 1 to Platform 2:

```yaml
automation:
  - alias: "Train Movement - Platform 1 to 2"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_td_area_sk
    condition:
      - condition: template
        value_template: >
          {% set events = state_attr('sensor.network_rail_integration_td_area_sk', 'recent_events') %}
          {% if events and events | length > 0 %}
            {% set last_event = events[-1] %}
            {{ last_event.event_type == 'step' and
               last_event.from_platform == '1' and
               last_event.to_platform == '2' }}
          {% else %}
            false
          {% endif %}
    action:
      - service: notify.mobile_app
        data:
          title: "Train Movement"
          message: >
            {% set events = state_attr('sensor.network_rail_integration_td_area_sk', 'recent_events') %}
            {% set last_event = events[-1] %}
            Train {{ last_event.train_id }} moved from Platform 1 to Platform 2
```

## Train Movement Automations

### Station Arrival Notification

Get notified when a specific train arrives at a tracked station:

```yaml
automation:
  - alias: "My Train Arrives at Euston"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_euston
    condition:
      - condition: template
        value_template: >
          {{ trigger.to_state.state == 'ARRIVAL' and
             trigger.to_state.attributes.train_id == '1A23' }}
    action:
      - service: notify.mobile_app
        data:
          title: "Train Arrival"
          message: >
            Your train ({{ trigger.to_state.attributes.train_id }}) has arrived at
            {{ trigger.to_state.attributes.station_name }} on platform
            {{ trigger.to_state.attributes.platform }}
```

### Delayed Train Alert

Alert when a train is running late:

```yaml
automation:
  - alias: "Late Train Alert"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_euston
    condition:
      - condition: template
        value_template: >
          {{ trigger.to_state.attributes.variation_status == 'LATE' and
             trigger.to_state.attributes.timetable_variation | int > 5 }}
    action:
      - service: notify.mobile_app
        data:
          title: "Train Delayed"
          message: >
            Train {{ trigger.to_state.attributes.train_id }} is running
            {{ trigger.to_state.attributes.timetable_variation }} minutes late
```

### Track Specific TOC

Monitor trains from a specific Train Operating Company:

```yaml
automation:
  - alias: "Great Western Railway Arrivals"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_paddington
    condition:
      - condition: template
        value_template: >
          {{ trigger.to_state.state == 'ARRIVAL' and
             trigger.to_state.attributes.toc_name == 'Great Western Railway' }}
    action:
      - service: notify.mobile_app
        data:
          title: "GWR Train Arrival"
          message: >
            GWR train {{ trigger.to_state.attributes.train_id }} arrived at
            Platform {{ trigger.to_state.attributes.platform }}
```

## Dashboard Integration

### Platform Status Card

Display current platform states:

```yaml
type: markdown
title: Platform Status
content: >
  {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
  {% if platforms %}
    {% for p_id, p_state in platforms.items() %}
      **Platform {{ p_id }}**: 
      {% if p_state.status == 'active' %}
        🚂 Train {{ p_state.current_train }} ({{ p_state.current_event }})
      {% else %}
        ✓ Clear
      {% endif %}
    {% endfor %}
  {% else %}
    No platform data available
  {% endif %}
```

### Recent Events Timeline

Show recent train events:

```yaml
type: markdown
title: Recent Train Events
content: >
  {% set events = state_attr('sensor.network_rail_integration_td_area_sk', 'recent_events') %}
  {% if events %}
    {% for event in events[-5:] | reverse %}
      - **{{ event.timestamp | timestamp_custom('%H:%M') }}**: 
        Train {{ event.train_id }} - {{ event.event_type }}
        {% if event.platform %} (Platform {{ event.platform }}){% endif %}
        {% if event.from_platform and event.to_platform %}
          (Platform {{ event.from_platform }} → {{ event.to_platform }})
        {% endif %}
    {% endfor %}
  {% else %}
    No recent events
  {% endif %}
```

## Advanced Examples

### Countdown to Platform Clearance

Estimate when a platform will be clear based on typical dwell time:

```yaml
template:
  - sensor:
      - name: "Platform 1 Estimated Clear Time"
        state: >
          {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
          {% if platforms and '1' in platforms and platforms['1'].status == 'active' %}
            {% set last_updated = platforms['1'].last_updated | as_datetime %}
            {% if last_updated %}
              {% set dwell_time = 120 %}  {# 2 minutes in seconds #}
              {% set clear_time = last_updated + timedelta(seconds=dwell_time) %}
              {{ clear_time.strftime('%H:%M:%S') }}
            {% else %}
              Unknown
            {% endif %}
          {% else %}
            Platform clear
          {% endif %}
        icon: mdi:clock-outline
```

### Platform Occupancy Statistics

Track platform usage over time:

```yaml
template:
  - sensor:
      - name: "Platform 1 Activity Count"
        state: >
          {% set events = state_attr('sensor.network_rail_integration_td_area_sk', 'recent_events') %}
          {% if events %}
            {{ events | selectattr('to_platform', 'equalto', '1') | list | length +
               events | selectattr('from_platform', 'equalto', '1') | list | length }}
          {% else %}
            0
          {% endif %}
        unit_of_measurement: "events"
```

### Multi-Station Tracking

Compare activity across multiple TD areas:

```yaml
automation:
  - alias: "Compare Station Activity"
    trigger:
      - platform: time_pattern
        minutes: "/15"
    action:
      - service: notify.mobile_app
        data:
          title: "Station Activity Comparison"
          message: >
            {% set sk_events = state_attr('sensor.network_rail_integration_td_area_sk', 'recent_events') | length %}
            {% set g1_events = state_attr('sensor.network_rail_integration_td_area_g1', 'recent_events') | length %}
            SK: {{ sk_events }} events, G1: {{ g1_events }} events
```

## Tips and Best Practices

1. **Use Template Sensors**: Create template sensors to simplify complex automations
2. **Filter in Templates**: Filter platforms and events in your templates for maximum flexibility (e.g., `events | selectattr('to_platform', 'in', ['1', '2', '3'])`)
3. **Test with History**: Use Developer Tools → Template to test your templates with actual sensor data
4. **Combine with Train Movements**: Use both TD and Train Movements data for comprehensive tracking
5. **Event History Size**: Adjust event history size based on your automation needs (higher for analytics, lower for simple notifications)
6. **Platform Mapping**: SMART data provides berth-to-platform mapping, but accuracy varies by station

## Troubleshooting

### Platform Data Not Showing

- Ensure SMART data is available and loaded (check logs)
- Verify TD areas are correctly configured
- Confirm berth-to-platform mapping exists for your station (SMART data may not have mappings for all stations)

### Events Not Appearing in History

- Check event history size configuration
- Ensure TD feed is receiving messages (check TD Status sensor)
- Review debug logs for message processing information

### Template Errors

- Always check if attributes exist before accessing them
- Use `is not none` checks for optional fields
- Test templates in Developer Tools before using in automations
- Check entity names match your actual sensor IDs
