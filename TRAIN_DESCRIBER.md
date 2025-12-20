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

**Attributes**:
- `area_id`: The TD area ID
- `berth_count`: Number of occupied berths in this area
- `occupied_berths`: Dictionary of berth ID → train description
- `last_msg_type`: Last message type received for this area
- `last_time_local`: Local time of last message
- Message-specific fields from last message

## Using TD Data

### Dashboard Cards

Display berth occupancy in a dashboard:

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

Get notified when a train enters a specific berth:

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

1. Ensure Train Describer is enabled in the configuration
2. Check that your Network Rail credentials have access to the TD feed
3. Verify the connection status: `binary_sensor.network_rail_integration_feed_connected`
4. Check logs for subscription errors

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

## References

- [Network Rail Open Data](https://www.networkrail.co.uk/who-we-are/transparency-and-ethics/transparency/open-data-feeds/)
- [Open Rail Data Wiki - TD](https://wiki.openraildata.com/index.php?title=TD)
- [C-Class Messages](https://wiki.openraildata.com/index.php?title=C_Class_Messages)
- [S-Class Messages](https://wiki.openraildata.com/index.php/S_Class_Messages)
