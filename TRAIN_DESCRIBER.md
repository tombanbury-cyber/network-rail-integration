# Train Describer Feed

The Train Describer (TD) feed provides real-time signalling data from Network Rail's train describer systems across the UK. This data shows the movement of trains through "berths" (signalling locations) and is useful for creating detailed network diagrams and tracking train positions at a granular level.

## Overview

The Train Describer feed complements the Train Movements feed by providing:
- **Real-time berth occupancy** - Know which trains are in which signalling berths
- **Berth step events** - Track trains moving between berths
- **Signalling state information** - Monitor signal aspects, track circuits, and other signalling elements
- **Network visualization** - Build live railway network diagrams showing train positions

## Message Types

The TD feed uses two classes of messages:

### C-Class Messages (Berth Operations)

| Type | Name | Description |
|------|------|-------------|
| CA | Berth Step | Moves a train description from one berth to another |
| CB | Berth Cancel | Removes a train description from a berth |
| CC | Berth Interpose | Inserts a new train description into a berth |
| CT | Heartbeat | Periodic status message from a train describer |

### S-Class Messages (Signalling State)

| Type | Name | Description |
|------|------|-------------|
| SF | Signalling Update | Updates a single signalling element |
| SG | Signalling Refresh | Provides a refresh of signalling data |
| SH | Signalling Refresh Finished | Signals the end of a refresh batch |

## Configuration

### Enabling Train Describer

1. Open your Network Rail Integration configuration
2. Select **"Configure Train Describer"**
3. Enable **"Enable Train Describer Feed"**
4. Optionally specify TD area IDs to filter (see below)
5. Save the configuration

The integration will automatically subscribe to the `TD_ALL_SIG_AREA` topic and start receiving messages.

### Filtering by TD Area

TD areas represent geographical signalling areas (e.g., "SK", "G1", "RW"). You can:

- **Leave empty** to receive all TD messages from all areas
- **Specify areas** (comma-separated) to receive only messages from those areas
  - Example: `SK, G1, RW`
  - This reduces the message volume if you're only interested in specific regions

## Entities Created

When Train Describer is enabled, the following entities are created:

### Train Describer Status Sensor

**Entity ID**: `sensor.network_rail_integration_train_describer_status`

Shows the last TD message received and provides overall statistics.

**Attributes**:
- `msg_type`: Type of last message (CA, CB, CC, CT, SF, SG, SH)
- `area_id`: TD area ID
- `time`: Message timestamp (milliseconds since epoch)
- `time_local`: Local time of message
- `message_count`: Total TD messages received
- `berth_count`: Number of currently occupied berths
- Message-specific fields (e.g., `from_berth`, `to_berth`, `description`)

### TD Area Sensors

**Entity ID**: `sensor.network_rail_integration_td_area_<area_id>`

One sensor is created for each configured TD area (if area filtering is enabled).

**Attributes** (Enhanced in v1.8.0):
- `area_id`: The TD area ID
- `station_name`: Station name (if available from SMART data)
- `station_code`: Station code or TD area ID
- `selected_platforms`: List of platforms being tracked, or "all" if none configured
- `berth_count`: Number of occupied berths in this area
- `occupied_berths`: Dictionary of berth ID → train description (backward compatibility)
- **NEW in v1.8.0** - `platforms`: Dictionary of platform states:
  ```python
  {
    "1": {
      "platform_id": "1",
      "current_train": "2A01",  # Train description from TD feed
      "current_event": "arrive",  # or "interpose", "step", null
      "last_updated": "2025-12-22T10:30:15+00:00",
      "status": "active"  # or "idle"
    },
    "2": {
      "platform_id": "2",
      "current_train": null,
      "current_event": null,
      "last_updated": "2025-12-22T10:25:00+00:00",
      "status": "idle"
    }
  }
  ```
- **NEW in v1.8.0** - `recent_events`: List of recent TD events with platform associations:
  ```python
  [
    {
      "event_type": "step",  # or "cancel", "interpose"
      "train_id": "2A01",
      "timestamp": "2025-12-22T10:30:15+00:00",
      "area_id": "SK",
      "from_platform": "1",
      "to_platform": "2",
      "from_berth": "M123",
      "to_berth": "M124"
    },
    # ... up to configured history size (default 10)
  ]
  ```
- **event_history_size**: Maximum number of events kept in history
- `last_msg_type`: Last message type received for this area
- `last_time_local`: Local time of last message
- Message-specific fields from last message

## Platform Tracking

The Train Describer integration automatically tracks all platforms in configured TD areas. Platform tracking uses SMART berth topology data to associate berths with platform numbers.

### Platform State Tracking

For each platform discovered in a TD area, the sensor tracks:
- **current_train**: The train description currently occupying the platform
- **current_event**: The most recent event type (arrive, interpose, step)
- **last_updated**: Timestamp of the last platform activity
- **status**: Either "active" (train present) or "idle" (platform empty)

### Event History

The sensor maintains a configurable history of recent TD events (configured via **Event History Size** setting, default: 10, range: 1-50), with each event including:
- Event type (step, cancel, interpose)
- Train ID (description from TD feed)
- Timestamp
- Platform associations (from_platform, to_platform, or platform) when available
- Berth information (from_berth, to_berth)

Events are stored in a circular buffer and include all events for the TD area. You can filter events by platform in your templates and automations.

## Using TD Data

### Dashboard Cards

Display platform states in a dashboard:

```yaml
type: entities
title: Platform Status - TD Area SK
entities:
  - entity: sensor.network_rail_integration_td_area_sk
    type: attribute
    attribute: platforms
```

Display recent events:

```yaml
type: entities
title: Recent Train Events - TD Area SK
entities:
  - entity: sensor.network_rail_integration_td_area_sk
    type: attribute
    attribute: recent_events
```

Display berth occupancy in a dashboard (backward compatibility):

```yaml
type: entities
title: TD Area SK - Occupied Berths
entities:
  - entity: sensor.network_rail_integration_td_area_sk
    type: attribute
    attribute: occupied_berths
```

Show TD message statistics:

```yaml
type: glance
title: Train Describer Status
entities:
  - entity: sensor.network_rail_integration_train_describer_status
    name: Last Message
  - entity: sensor.network_rail_integration_train_describer_status
    name: Messages
    attribute: message_count
  - entity: sensor.network_rail_integration_train_describer_status
    name: Occupied Berths
    attribute: berth_count
```

### Automations

Get notified when a train arrives at a specific platform:

```yaml
automation:
  - alias: "Notify when train arrives at Platform 1"
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
          message: >
            Train {{ state_attr('sensor.network_rail_integration_td_area_sk', 'platforms')['1'].current_train }}
            arriving at Platform 1
```

Monitor when any platform becomes active:

```yaml
automation:
  - alias: "Alert when any platform becomes active"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_td_area_sk
    condition:
      - condition: template
        value_template: >
          {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
          {% if platforms %}
            {{ platforms.values() | selectattr('status', 'equalto', 'active') | list | length > 0 }}
          {% else %}
            false
          {% endif %}
    action:
      - service: notify.mobile_app
        data:
          message: >
            {% set platforms = state_attr('sensor.network_rail_integration_td_area_sk', 'platforms') %}
            {% set active = platforms.values() | selectattr('status', 'equalto', 'active') | list %}
            {{ active | length }} platform(s) active
```

Filter events for specific platforms in templates:

```yaml
automation:
  - alias: "Notify for events on platforms 1-3"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_td_area_sk
    action:
      - service: notify.mobile_app
        data:
          message: >
            {% set events = state_attr('sensor.network_rail_integration_td_area_sk', 'recent_events') %}
            {% set filtered = events | selectattr('to_platform', 'in', ['1', '2', '3']) | list %}
            {{ filtered | length }} recent events on platforms 1-3
```

Get notified when a train enters a specific berth (classic method):

```yaml
automation:
  - alias: "Train entered berth 3647"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_td_area_sk
    condition:
      - condition: template
        value_template: "{{ '3647' in state_attr('sensor.network_rail_integration_td_area_sk', 'occupied_berths') }}"
    action:
      - service: notify.mobile_app
        data:
          message: "Train {{ state_attr('sensor.network_rail_integration_td_area_sk', 'occupied_berths')['3647'] }} entered berth 3647"
```

### Network Diagrams

The berth state data can be used to create live network diagrams using custom cards or scripts. The `occupied_berths` attribute provides a real-time snapshot of which trains are where.

Example of accessing berth data in a template:

```yaml
{% set berths = state_attr('sensor.network_rail_integration_td_area_sk', 'occupied_berths') %}
{% if berths %}
  Trains in area SK:
  {% for berth_id, description in berths.items() %}
    - Berth {{ berth_id }}: {{ description }}
  {% endfor %}
{% else %}
  No trains in area SK
{% endif %}
```

## TD Areas

Common TD area codes include:

- **London and South East**: G1, G3, SE, TH, VN, WD, WK
- **Anglia**: ANG, IP, NW, SN
- **Western**: BD, CW, DY, EX, NW, OX, RG, SW
- **Midlands**: BM, BR, CR, DB, LE, NC, NT, SH, WM
- **North West**: BN, CH, LL, LV, MR, WG
- **North East**: DH, HD, HT, LS, NE, SX, YK
- **Scotland**: AB, DU, ED, GW, IN, PA
- **Wales**: CF, CY, MC, NP, SW

Refer to the [Open Rail Data Wiki](https://wiki.openraildata.com/index.php?title=TD) for a complete list of TD areas.

## Technical Details

### Message Format

Train Describer messages are received as JSON objects. Example CA message (Berth Step):

```json
{
  "CA_MSG": {
    "time": "1349696911000",
    "area_id": "SK",
    "msg_type": "CA",
    "from": "3647",
    "to": "3649",
    "descr": "1F42"
  }
}
```

### Berth State Tracking

The integration maintains an in-memory state of all occupied berths:
- **CA (Step)**: Clears the `from` berth and sets the `to` berth
- **CB (Cancel)**: Clears the specified berth
- **CC (Interpose)**: Sets the specified berth

This state can be accessed via the sensor attributes for building visualizations.

### Performance Considerations

The TD feed can be high-volume, especially if tracking all areas:
- Use area filtering to reduce message volume
- TD messages are processed asynchronously to avoid blocking Home Assistant
- Only berth occupancy (C-Class messages) is tracked in state; signalling messages are available in sensor attributes but not stored long-term

## Troubleshooting

### No TD messages received

If the Train Describer Status sensor shows "Waiting for messages" or "No messages":

1. **Check TD is enabled**: Ensure Train Describer is enabled in the configuration
2. **Check connection status**: Verify `binary_sensor.network_rail_integration_feed_connected` shows "Connected"
3. **Check credentials**: Confirm your Network Rail credentials have access to the TD feed
4. **Review debug logs**: Check the `sensor.network_rail_integration_debug_log` entity for detailed information:
   - Look for "Subscribing to Train Describer feed" message - confirms subscription attempt
   - Look for "Successfully subscribed to Train Describer feed" - confirms successful subscription
   - Look for "Received dict payload, checking if TD message" - confirms messages are being received
   - Look for "Parsed TD message" - confirms TD messages are being parsed
   - Look for "Publishing TD message" - confirms messages are passing filters
   - Look for "TD message filtered out" - indicates messages are being filtered by area settings
5. **Check Home Assistant logs**: Enable debug logging for more details:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.network_rail_integration: debug
   ```
6. **Verify area filters**: If you've configured specific TD areas, ensure they're correct:
   - Area codes are case-sensitive (should be uppercase, e.g., "SK", "G1")
   - Leave area filter empty to receive all TD messages
   - Check the debug log for "TD filters: areas=" to see active filters

### Common Issues and Solutions

**Issue**: Sensor shows "Waiting for messages" after connection
- **Solution**: TD messages may be sparse during quiet periods. Wait a few minutes or check during peak times.

**Issue**: Debug log shows "Message was not a valid TD message"
- **Solution**: This is normal - some non-TD messages are received on the feed. Only valid TD messages will be processed.

**Issue**: Debug log shows "TD message filtered out"
- **Solution**: Your area filter is excluding messages. Either:
  - Remove area filters to receive all messages
  - Add the required area codes to your filter configuration

**Issue**: Subscription errors in logs
- **Solution**: Check your Network Rail credentials and ensure your account has access to the Train Describer feed.

### High CPU usage

If the TD feed is causing performance issues:
1. Enable area filtering to reduce message volume
2. Track only the specific areas you need
3. Consider limiting the number of area sensors created

### Missing berth data

If berths are not showing in `occupied_berths`:
- The berth may have been occupied before Home Assistant started
- CC (interpose) messages are used to populate berths; if a train was already in place, you may need to wait for the next movement
- Some areas may have sparse TD coverage

### Debug Logging

The integration includes a debug log sensor (`sensor.network_rail_integration_debug_log`) that captures:
- Connection status and subscription confirmations
- TD message receipt and parsing
- Filter application and message counts
- Error conditions

View the sensor's attributes in Developer Tools → States to see the full log history.

## References

- [Network Rail Open Data](https://www.networkrail.co.uk/who-we-are/transparency-and-ethics/transparency/open-data-feeds/)
- [Open Rail Data Wiki - TD](https://wiki.openraildata.com/index.php?title=TD)
- [C-Class Messages](https://wiki.openraildata.com/index.php?title=C_Class_Messages)
- [S-Class Messages](https://wiki.openraildata.com/index.php/S_Class_Messages)
