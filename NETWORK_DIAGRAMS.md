# Network Diagrams with SMART Data

This guide explains how to use the Network Rail Integration's **Network Diagram** feature to visualize train positions on a map of signalling berth connections.

## Overview

Network Rail's SMART (Signalling Maintenance and Renewal Technology) data provides detailed information about how signalling berths are connected to each other and to stations. Combined with the real-time Train Describer (TD) feed, this enables you to create live railway network diagrams similar to those used in signal boxes and on platforms.

## What is SMART Data?

SMART data contains:
- **Berth connections**: How berths link together (from berth → to berth)
- **STANOX associations**: Which berths belong to which stations
- **Platform mappings**: Which platform a berth represents
- **Line information**: Which railway line a berth connection represents

This data is updated monthly by Network Rail and is automatically downloaded and cached by the integration.

## What are Berths?

In UK railway signalling, a **berth** is a section of track between signals. When a train occupies a berth, it appears on the Train Describer feed with a 4-character **headcode** (e.g., "1F42", "2C45").

Examples:
- **M123** - A berth in the Manchester area (TD area "SK")
- **G669** - A berth in the Clapham Junction area (TD area "G1")
- **3647** - A berth in the Sheffield area (TD area "SK")

## Enabling Network Diagrams

### Prerequisites

1. **Train Describer must be enabled** - Network diagrams rely on live TD data
2. **Configure TD areas** - Make sure you're tracking the TD areas for your station

### Configuration Steps

1. Go to **Settings → Devices & Services → Network Rail Integration**
2. Click **Configure**
3. Select **Configure Network Diagrams**
4. Enable network diagrams and search for your station
5. Set the range (number of adjacent stations to include)
6. Save

### Configuration Options

- **Enable/Disable**: Toggle the network diagram sensor on/off
- **Center Station**: The STANOX code of the station to center the diagram on
- **Range**: Number of stations up/down the line to include (1-10)
  - Range 1: Just the center station and immediate neighbors
  - Range 2: Center station and 2 stations in each direction
  - Range 10: Center station and 10 stations in each direction

### Alert Configuration (NEW in v1.14.0)

Network Diagrams can now be configured with **intelligent alerts** similar to Track Section Monitor. When alerts are enabled, the diagram will track trains in the diagram area and fire Home Assistant events when specific service types are detected.

**Alert Types:**
- **Freight**: All freight trains (0xxx, 4xxx, 6xxx, 7xxx headcodes)
- **RHTT**: Rail Head Treatment Trains (3Hxx, 3Yxx headcodes)
- **Steam**: Steam charter services (typically 1Zxx headcodes)
- **Charter**: General charter/special services (1Zxx headcodes)
- **Pullman**: Luxury/Pullman services
- **Royal Train**: Royal train services (1X99 headcode)

**Requirements for Alerts:**
- VSTP feed must be enabled for service classification
- Train Describer feed must be enabled
- TD areas must be configured to cover your diagram area

To enable alerts for a diagram:
1. Go to **Settings → Devices & Services → Network Rail Integration**
2. Click **Configure**
3. Select **Configure Network Diagrams**
4. Choose **Edit Diagram** to modify an existing diagram
5. Check the alert types you want to enable
6. Click **Submit**

When a train matching your alert criteria enters the diagram area, the integration will fire a `homeassistant_network_rail_uk_track_alert` event that you can use in automations.

## Understanding the Sensor

Once configured, a new sensor is created:

**Entity ID**: `sensor.network_rail_integration_diagram_<stanox>`

### State

The sensor's state is the **number of currently occupied berths** in the diagram area.

### Attributes

The sensor provides detailed attributes you can use to build custom visualizations:

```yaml
center_stanox: "32000"
center_name: "MANCR PIC"
center_berths:
  - berth_id: "M123"
    td_area: "SK"
    platform: "1"
    occupied: true
    headcode: "1F42"
  - berth_id: "M124"
    td_area: "SK"
    platform: "2"
    occupied: false
    headcode: null

up_stations:
  - stanox: "32009"
    name: "ARDWICKJN"
    berths:
      - berth_id: "M100"
        td_area: "SK"
        occupied: false
        headcode: null

down_stations:
  - stanox: "32050"
    name: "ASHBURYS"
    berths:
      - berth_id: "M200"
        td_area: "SK"
        occupied: true
        headcode: "2C45"

smart_data_available: true
smart_data_last_updated: "2025-01-15T10:30:00Z"
diagram_range: 1

# NEW in v1.14.0: Train tracking attributes (when alerts are enabled)
trains_in_diagram:
  - train_id: "6M94"
    headcode: "6M94"
    current_berth: "SK:M123"
    entered_diagram_at: "2025-12-29T10:12:08"
    time_in_diagram_seconds: 145
    berths_visited:
      - "SK:M121"
      - "SK:M122"
      - "SK:M123"
    
    # VSTP enriched data (if available)
    service_type: "freight"
    category: "M"
    origin: "FLIXSTW"
    destination: "TRAFFPK"
    operator: "Freightliner"
    description: "Freight Intermodal"
    
    triggers_alert: true
    alert_reason: "Freight service"

total_trains: 1
alert_trains: 1
alert_services_enabled:
  freight: true
  rhtt: false
  steam: true
```

## Creating a Lovelace Dashboard

### Simple Text Display

Show occupied berths:

```yaml
type: entities
entities:
  - entity: sensor.network_rail_integration_diagram_32000
    name: Occupied Berths at Manchester Piccadilly
```

### Custom Template Card

Display berth details with colors:

```yaml
type: markdown
content: |
  ## {{ state_attr('sensor.network_rail_integration_diagram_32000', 'center_name') }}
  
  ### Occupied Berths: {{ states('sensor.network_rail_integration_diagram_32000') }}
  
  {% for berth in state_attr('sensor.network_rail_integration_diagram_32000', 'center_berths') %}
  **{{ berth.berth_id }}** (Platform {{ berth.platform }}): 
  {% if berth.occupied %}
  🚂 {{ berth.headcode }}
  {% else %}
  ⚪ Empty
  {% endif %}
  {% endfor %}
  
  ### Up Line
  {% for station in state_attr('sensor.network_rail_integration_diagram_32000', 'up_stations') %}
  - **{{ station.name }}**: {{ station.berths | selectattr('occupied') | list | length }} occupied
  {% endfor %}
  
  ### Down Line
  {% for station in state_attr('sensor.network_rail_integration_diagram_32000', 'down_stations') %}
  - **{{ station.name }}**: {{ station.berths | selectattr('occupied') | list | length }} occupied
  {% endfor %}
```

### Visual Diagram (Advanced)

For a graphical representation, you can use the **Custom Button Card** or **Picture Elements Card** to create a visual diagram:

```yaml
type: picture-elements
image: /local/network_diagram_background.png
elements:
  - type: state-label
    entity: sensor.network_rail_integration_diagram_32000
    attribute: center_berths[0].headcode
    style:
      top: 50%
      left: 30%
      color: >
        {% if state_attr('sensor.network_rail_integration_diagram_32000', 'center_berths')[0].occupied %}
        red
        {% else %}
        green
        {% endif %}
```

## Automation with Diagram Alerts (NEW in v1.14.0)

When alerts are enabled for a diagram, the integration fires Home Assistant events that you can use to trigger automations.

### Alert on Freight Trains

```yaml
automation:
  - alias: "Alert on freight train in diagram"
    trigger:
      - platform: event
        event_type: homeassistant_network_rail_uk_track_alert
        event_data:
          diagram_stanox: "32000"
          alert_type: "freight"
    action:
      - service: notify.mobile_app
        data:
          title: "Freight Train Alert"
          message: >
            Freight train {{ trigger.event.data.headcode }} 
            from {{ trigger.event.data.origin }} to {{ trigger.event.data.destination }}
            has entered the Manchester Piccadilly diagram area
```

### Alert on Steam Specials

```yaml
automation:
  - alias: "Alert on steam special in diagram"
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
            has entered the diagram area!
```

### Display Alert Trains

Show trains currently in the diagram area that are triggering alerts:

```yaml
type: markdown
content: |
  ## Alert Trains in Diagram
  
  {% set trains = state_attr('sensor.network_rail_integration_diagram_32000', 'trains_in_diagram') %}
  {% set alert_trains = trains | selectattr('triggers_alert', 'equalto', true) | list if trains else [] %}
  {% if alert_trains %}
    {% for train in alert_trains %}
      ### {{ train.headcode }} ⚠️
      - **Service**: {{ train.service_type | default('Unknown') }}
      - **From**: {{ train.origin | default('Unknown') }}
      - **To**: {{ train.destination | default('Unknown') }}
      - **Alert**: {{ train.alert_reason }}
      - **Time in area**: {{ (train.time_in_diagram_seconds / 60) | round(1) }} minutes
      ---
    {% endfor %}
  {% else %}
    *No alert trains currently in diagram area*
  {% endif %}
```

## Refreshing SMART Data

SMART data is cached for 30 days. To manually refresh:

1. **Via Service Call**:
   - Go to **Developer Tools → Services**
   - Select `network_rail_integration.refresh_smart_data`
   - Click **Call Service**

2. **Via Automation**:
   ```yaml
   automation:
     - alias: "Refresh SMART Data Monthly"
       trigger:
         - platform: time
           at: "03:00:00"
       condition:
         - condition: template
           value_template: "{{ now().day == 1 }}"
       action:
         - service: network_rail_integration.refresh_smart_data
   ```

## Use Cases

### Station Platform Display

Create a live platform display showing which trains are at which platforms:

```yaml
type: entities
title: Manchester Piccadilly Platforms
entities:
  - type: custom:template-entity-row
    entity: sensor.network_rail_integration_diagram_32000
    name: "Platform 1"
    state: |
      {% set berths = state_attr('sensor.network_rail_integration_diagram_32000', 'center_berths') %}
      {% set platform_berth = berths | selectattr('platform', 'eq', '1') | list | first %}
      {% if platform_berth and platform_berth.occupied %}
      {{ platform_berth.headcode }}
      {% else %}
      Empty
      {% endif %}
```

### Train Movement Tracking

Track a specific train as it moves through berths:

```yaml
type: entities
title: Train 1F42 Position
entities:
  - entity: sensor.network_rail_integration_diagram_32000
    name: "Current Berth"
    state: |
      {% set all_berths = state_attr('sensor.network_rail_integration_diagram_32000', 'center_berths') %}
      {% for berth in all_berths %}
      {% if berth.headcode == '1F42' %}
      {{ berth.berth_id }} ({{ berth.platform }})
      {% endif %}
      {% endfor %}
```

### Adjacent Station Alert

Get notified when a train enters an adjacent station:

```yaml
automation:
  - alias: "Train Approaching Manchester"
    trigger:
      - platform: state
        entity_id: sensor.network_rail_integration_diagram_32000
    condition:
      - condition: template
        value_template: >
          {% set up_stations = state_attr('sensor.network_rail_integration_diagram_32000', 'up_stations') %}
          {{ up_stations | selectattr('berths', 'defined') | map(attribute='berths') | sum(start=[]) | selectattr('occupied') | list | length > 0 }}
    action:
      - service: notify.mobile_app
        data:
          title: "Train Approaching"
          message: "A train has entered an adjacent station"
```

## Technical Details

### SMART Data Structure

The raw SMART data contains records with these fields:

- **TD**: TD area code (e.g., "SK", "G1")
- **FROMBERTH**: Starting berth ID
- **TOBERTH**: Destination berth ID
- **STANOX**: Station STANOX code
- **STANME**: Station name
- **STEPTYPE**: Type of berth step
- **EVENT**: Event type (A=Arrival, D=Departure, etc.)
- **PLATFORM**: Platform number/letter
- **FROMLINE**: Line of origin
- **TOLINE**: Line of destination

### Graph Structure

Internally, SMART data is parsed into an efficient graph structure:

- **Berth Connections**: Map of berth → adjacent berths
- **STANOX to Berths**: Map of station → berths at that station
- **Berth to STANOX**: Reverse map of berth → station

This enables fast lookups when updating the sensor in response to TD messages.

### Performance

- SMART data is loaded asynchronously at startup
- The graph structure uses O(1) lookups for berth queries
- TD updates trigger immediate sensor state changes
- No polling - fully event-driven

## Troubleshooting

### "SMART data not available"

**Cause**: SMART data failed to download or hasn't downloaded yet.

**Solution**:
1. Check your Network Rail credentials are correct
2. Verify you have internet access
3. Check the logs for download errors
4. Try manually refreshing: `network_rail_integration.refresh_smart_data`

### No berths showing for my station

**Cause**: The station may not have berth data in SMART, or the STANOX is incorrect.

**Solution**:
1. Verify the STANOX code is correct
2. Check that Train Describer is enabled and tracking the right TD areas
3. Some smaller stations may not have detailed berth data

### Berth occupancy not updating

**Cause**: Train Describer feed not receiving messages for those berths.

**Solution**:
1. Enable Train Describer if not already enabled
2. Make sure you're tracking the correct TD areas
3. Check `sensor.network_rail_integration_train_describer_status` for TD activity

### Wrong stations in "up" vs "down" connections

**Cause**: The SMART data doesn't explicitly label direction; the integration uses a simple heuristic (even split) to divide adjacent stations.

**Solution**: This is a **known limitation**. Adjacent stations are correctly identified and shown, but may not be perfectly classified as "up" (towards London) or "down" (away from London). 

**Workaround**: Treat both "up_connections" and "down_connections" as simply "adjacent_stations". The important information is which stations are connected and their berth occupancy, not the specific direction label.

**Future Enhancement**: Proper direction classification would require additional metadata or manual configuration that is not currently available in SMART data alone.

## Reference: Traksy

For inspiration, check out [Traksy](https://traksy.uk/live/), which provides live railway diagrams using similar data sources. Their displays show how berth occupancy can be visualized on actual track diagrams.

## Related Documentation

- [TRAIN_DESCRIBER.md](TRAIN_DESCRIBER.md) - Train Describer feed documentation
- [README.md](README.md) - Main integration documentation
- [Open Rail Data SMART Documentation](https://wiki.openraildata.com/index.php/Reference_data)

## Services

### `network_rail_integration.refresh_smart_data`

Manually download and refresh SMART berth topology data.

**Parameters**: None

**Example**:
```yaml
service: network_rail_integration.refresh_smart_data
```

This service is useful for:
- Forcing a refresh before the 30-day cache expires
- Recovering from a failed initial download
- Updating after Network Rail publishes new SMART data
