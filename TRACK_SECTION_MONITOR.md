# Track Section Monitor

The Track Section Monitor feature allows you to monitor trains along a defined stretch of track using Train Describer berth data enriched with VSTP (Very Short Term Plan) schedule information. This enables real-time alerts for specific service types like freight, RHTT (Rail Head Treatment Trains), steam specials, and named trains.

## Features

- **Real-time train tracking** through signalling berths
- **Service classification** using VSTP schedule data and headcode patterns
- **Intelligent alerts** for freight, special services, and charter trains
- **Rich train information** including origin, destination, operator, and service type
- **Home Assistant events** for automation triggers
- **Multiple track sections** can be monitored simultaneously

## Prerequisites

To use the Track Section Monitor, you need:

1. **Train Describer feed enabled** - Provides berth occupancy data
2. **VSTP feed enabled** (recommended) - Provides schedule enrichment
3. **TD area IDs** - Know which Train Describer areas cover your section
4. **STANOX code** - The station code for the center of your track section

## Configuration

### Step 1: Enable VSTP Feed

1. Go to **Settings → Devices & Services → Network Rail Integration**
2. Click **Configure**
3. Select **Configure VSTP Feed**
4. Enable the **Enable VSTP Feed** option
5. Click **Submit**

The VSTP feed provides real-time train schedule data including:
- Train origin and destination
- Train category and service type
- Scheduled platform and timing information
- Train operator details

### Step 2: Add a Track Section

1. In the integration configuration menu, select **Add Track Section**
2. Search for the station at the center of your track section
3. Select the station from the search results
4. Configure the track section:
   - **Name**: Give it a friendly name (e.g., "Canterbury West Platforms")
   - **Berth Range**: Number of berths to monitor in each direction (default: 3)
   - **TD Areas**: Comma-separated TD area IDs (e.g., "SK, CT")
5. Click **Submit**

### Step 3: Configure Alerts

1. Select **Configure Track Section Alerts**
2. Choose the track section to configure
3. Select which service types should trigger alerts:
   - **Freight**: All freight trains (0xxx, 4xxx, 6xxx, 7xxx headcodes)
   - **RHTT**: Rail Head Treatment Trains (3Hxx, 3Yxx headcodes)
   - **Steam**: Steam charter services
   - **Charter**: General charter/special services (1Zxx headcodes)
   - **Pullman**: Luxury/Pullman services
   - **Royal Train**: Royal train services (1X99 headcode)
4. Click **Submit**

## Service Classification

The integration automatically classifies trains based on VSTP data and headcode patterns:

### Train Categories (VSTP CIF)

| Category | Type | Description |
|----------|------|-------------|
| OO, OW | Ordinary Passenger | Stopping passenger services |
| XC, XX | Express Passenger | Express passenger services |
| XZ | Sleeper | Overnight sleeper services |
| BR, BS | Bus | Bus replacement services |
| EE, EL, ES | Empty Coaching Stock | Empty train movements |
| JJ, PM | Postal | Mail trains |
| PP, PV | Parcels | Parcel trains |
| B-S | Freight | Various freight categories |
| XY | Freight Special | Special freight movements |

### Headcode Patterns

| Pattern | Service Type | Examples |
|---------|--------------|----------|
| 0xxx, 4xxx, 6xxx, 7xxx | Freight | 6M94, 4O14, 0Z76 |
| 3Hxx, 3Yxx | RHTT | 3H01, 3Y22 |
| 1Zxx | Charter/Steam | 1Z42, 1Z90 |
| 1X99 | Royal Train | 1X99 |
| 5xxx | Empty Coaching Stock | 5Q88 |
| 1xxx, 2xxx | Passenger | 1F42, 2C19 |

### Special Services

The integration can detect:
- **RHTT (Rail Head Treatment Trains)**: Track cleaning trains
- **Steam**: Historic/preserved steam locomotives
- **Charter**: Special charter services
- **Pullman**: Luxury dining trains (e.g., Orient Express)
- **Royal Train**: Services carrying members of the Royal Family

## Entities

### Track Section Sensor

Each configured track section creates a sensor:

**Entity ID**: `sensor.network_rail_integration_track_section_<section_name>`

**State**: Number of trains currently in the section

**Attributes**:
```yaml
trains_in_section:
  - train_id: "6M94"
    headcode: "6M94"
    current_berth: "SK:M123"
    current_platform: ""
    direction: "DOWN"
    entered_section_at: "2025-12-29T10:12:08"
    time_in_section_seconds: 145
    berths_visited:
      - "SK:M121"
      - "SK:M122"
      - "SK:M123"
    berths_ahead: []
    
    # VSTP enriched data (if available)
    service_type: "freight"
    category: "M"
    origin: "FLIXSTW"
    destination: "TRAFFPK"
    operator: "Freightliner"
    power_type: "D"
    train_class: "66"
    
    triggers_alert: true
    alert_reason: "Freight service"

section_config:
  name: "canterbury_west_section"
  center_stanox: "87654"
  berth_range: 3
  td_areas:
    - "SK"
    - "CT"

section_berths:
  - "SK:3645"
  - "SK:3646"
  - "SK:3647"
  # ... more berths

total_trains: 1
alert_trains: 1
```

## Events

### Track Alert Event

When a train matching alert criteria enters the section, the integration fires:

**Event**: `homeassistant_network_rail_uk_track_alert`

**Event Data**:
```yaml
section_name: "canterbury_west_section"
train_id: "6M94"
headcode: "6M94"
alert_type: "freight"
alert_reason: "Freight service"
current_berth: "SK:M123"
service_type: "freight"
origin: "FLIXSTW"
destination: "TRAFFPK"
operator: "Freightliner"
entered_at: "2025-12-29T10:12:08"
```

## Automation Examples

### Alert on Freight Trains

```yaml
automation:
  - alias: "Alert on freight train"
    trigger:
      - platform: event
        event_type: homeassistant_network_rail_uk_track_alert
        event_data:
          section_name: "canterbury_west_section"
          alert_type: "freight"
    action:
      - service: notify.mobile_app
        data:
          title: "Freight Train Alert"
          message: >
            Freight train {{ trigger.event.data.headcode }} 
            from {{ trigger.event.data.origin }} to {{ trigger.event.data.destination }}
            has entered the Canterbury West section
```

### Alert on Steam Specials

```yaml
automation:
  - alias: "Alert on steam special"
    trigger:
      - platform: event
        event_type: homeassistant_network_rail_uk_track_alert
    condition:
      - condition: template
        value_template: "{{ 'steam' in trigger.event.data.get('alert_reason', '').lower() }}"
    action:
      - service: notify.mobile_app
        data:
          title: "Steam Special Alert"
          message: >
            Steam special {{ trigger.event.data.headcode }} 
            has entered {{ trigger.event.data.section_name }}!
```

### Count Trains in Section

```yaml
sensor:
  - platform: template
    sensors:
      canterbury_freight_count:
        friendly_name: "Freight Trains in Canterbury Section"
        value_template: >
          {{ state_attr('sensor.network_rail_integration_track_section_canterbury_west', 'trains_in_section')
             | selectattr('service_type', 'equalto', 'freight')
             | list | length }}
```

### Track Average Time in Section

```yaml
sensor:
  - platform: template
    sensors:
      canterbury_avg_time:
        friendly_name: "Average Time in Section"
        unit_of_measurement: "s"
        value_template: >
          {% set trains = state_attr('sensor.network_rail_integration_track_section_canterbury_west', 'trains_in_section') %}
          {% if trains %}
            {{ (trains | map(attribute='time_in_section_seconds') | list | sum / trains | length) | round(0) }}
          {% else %}
            0
          {% endif %}
```

## Dashboard Card Examples

### Simple Card

```yaml
type: entities
title: Canterbury West Track Section
entities:
  - entity: sensor.network_rail_integration_track_section_canterbury_west
    name: Trains in Section
  - type: attribute
    entity: sensor.network_rail_integration_track_section_canterbury_west
    attribute: alert_trains
    name: Alert Trains
```

### Detailed Train List

```yaml
type: markdown
content: |
  ## Trains in Canterbury West Section
  
  {% set trains = state_attr('sensor.network_rail_integration_track_section_canterbury_west', 'trains_in_section') %}
  {% if trains %}
    {% for train in trains %}
      ### {{ train.headcode }} {% if train.triggers_alert %}⚠️{% endif %}
      - **Service**: {{ train.service_type | default('Unknown') }}
      - **From**: {{ train.origin | default('Unknown') }}
      - **To**: {{ train.destination | default('Unknown') }}
      - **Berth**: {{ train.current_berth }}
      - **Time in section**: {{ (train.time_in_section_seconds / 60) | round(1) }} minutes
      {% if train.triggers_alert %}
      - **Alert**: {{ train.alert_reason }}
      {% endif %}
      ---
    {% endfor %}
  {% else %}
    *No trains currently in section*
  {% endif %}
```

### Alert History

```yaml
type: logbook
entities:
  - sensor.network_rail_integration_track_section_canterbury_west
hours_to_show: 24
```

## Troubleshooting

### No trains appearing in section

**Check:**
1. **Train Describer enabled**: Verify TD feed is receiving messages
2. **TD areas configured**: Ensure correct TD area IDs are specified
3. **Section berths**: Check that berths are being calculated correctly from SMART data
4. **VSTP enabled**: While optional, VSTP significantly improves tracking

**View debug logs**:
```yaml
logger:
  default: info
  logs:
    network_rail_integration: debug
```

### Trains not triggering alerts

**Check:**
1. **Alert services configured**: Verify alert types are enabled for the section
2. **VSTP data available**: Alerts work best with VSTP schedule data
3. **Service classification**: Check if train is being classified correctly

**Test with template**:
```yaml
{% set trains = state_attr('sensor.network_rail_integration_track_section_canterbury_west', 'trains_in_section') %}
{{ trains | tojson }}
```

### Section berths not calculated

**Check:**
1. **SMART data loaded**: The integration needs SMART topology data
2. **Valid STANOX**: Ensure the center STANOX is correct
3. **Manual TD areas**: If SMART data unavailable, specify TD areas manually

**Refresh SMART data**:
```yaml
service: network_rail_integration.refresh_smart_data
```

### VSTP data not enriching trains

**Check:**
1. **VSTP feed enabled**: Verify in integration options
2. **VSTP messages received**: Check debug logs for VSTP processing
3. **Schedule cache**: VSTP stores schedules for current day only

## Advanced Configuration

### Multiple Track Sections

You can configure multiple track sections to monitor different areas:

```yaml
# Track section 1: Canterbury West platforms
Name: Canterbury West Platforms
Center: Canterbury West (87654)
Range: 2
TD Areas: SK, CT
Alerts: Freight, RHTT, Steam

# Track section 2: Main line through Dover
Name: Dover Mainline
Center: Dover Priory (88210)
Range: 5
TD Areas: RW
Alerts: Freight, Royal Train
```

### Custom Alert Logic

Use template conditions for complex alert logic:

```yaml
automation:
  - alias: "Custom freight alert"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_track_section_canterbury_west
    condition:
      - condition: template
        value_template: >
          {% set trains = state_attr(trigger.entity_id, 'trains_in_section') %}
          {{ trains | selectattr('is_freight', 'equalto', true) | list | length > 2 }}
    action:
      - service: notify.mobile_app
        data:
          title: "Multiple Freight Trains"
          message: "3 or more freight trains in Canterbury section!"
```

## API Reference

### Service: `network_rail_integration.refresh_smart_data`

Manually refresh SMART topology data used for berth mapping.

**Parameters**: None

**Example**:
```yaml
service: network_rail_integration.refresh_smart_data
```

## Performance Considerations

- **Memory usage**: Each train in a section requires ~2KB of memory
- **Update frequency**: Sensors update in real-time with TD messages
- **VSTP cache**: Schedules are cached in memory for the current day
- **Section limit**: Recommended maximum of 10 track sections per integration

## Privacy & Data

- All train tracking is anonymous (train IDs/headcodes only)
- No personal data is collected or stored
- VSTP schedule data is public information from Network Rail
- Data is processed locally in Home Assistant

## Support

For issues or questions:
- GitHub Issues: https://github.com/tombanbury-cyber/homeassistant-network-rail-uk/issues
- Documentation: https://github.com/tombanbury-cyber/homeassistant-network-rail-uk

## See Also

- [Train Describer Documentation](TRAIN_DESCRIBER.md)
- [Network Diagrams Documentation](NETWORK_DIAGRAMS.md)
- [Automation Examples](AUTOMATION_EXAMPLES.md)
- [Dashboard Examples](DASHBOARD_EXAMPLES.md)
