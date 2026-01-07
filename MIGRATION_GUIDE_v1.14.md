# Migration Guide: v1.13 to v1.14

## Summary

Version 1.14.0 merges the functionality of Track Section Monitor into Network Diagrams, providing a unified experience for train tracking, alerts, and dashboard visualization.

## What's New

### Network Diagrams with Alerts

Network Diagrams can now be configured with **intelligent alerts** for specific train types:
- Freight trains
- RHTT (Rail Head Treatment Trains)
- Steam charter services
- General charter trains
- Pullman/luxury services
- Royal trains

When alerts are enabled:
- Trains in the diagram area are tracked with full VSTP enrichment
- Service classification determines which trains should trigger alerts
- Home Assistant events (`homeassistant_network_rail_uk_track_alert`) are fired
- Per-train details are exposed in sensor attributes

### Enhanced Sensor Attributes

Network Diagram sensors with alerts enabled now include:
- `trains_in_diagram`: List of trains currently in the diagram area
- `total_trains`: Count of all trains in diagram
- `alert_trains`: Count of trains matching alert criteria
- `alert_services_enabled`: Configuration showing which alert types are active

Each train in `trains_in_diagram` includes:
- Basic info: headcode, current berth, time in area
- VSTP enrichment: origin, destination, operator, service type
- Alert status: whether it triggers an alert and why

## Migration Paths

### For New Users

**Recommended**: Use Network Diagrams with alerts enabled
- Configure a network diagram for your station
- Enable desired alert types during configuration
- Use the same automations and dashboard cards

### For Existing Track Section Monitor Users

**No action required** - Your existing Track Section configurations continue to work unchanged.

**Optional**: Migrate to Network Diagrams for these benefits:
- Visual berth occupancy display
- Adjacent station connectivity
- Single configuration point for both visualization and alerts
- Simplified dashboard setup

### For Existing Network Diagram Users

**No action required** - Your existing diagrams work unchanged.

**Optional**: Enable alerts by editing your diagram configuration:
1. Go to Settings → Devices & Services → Network Rail Integration
2. Click Configure
3. Select "Configure Network Diagrams"
4. Choose "Edit Diagram"
5. Select your diagram
6. Check the alert types you want to enable
7. Save

## Configuration Examples

### Creating a New Diagram with Alerts

1. Navigate to Settings → Devices & Services → Network Rail Integration
2. Click Configure
3. Select "Configure Network Diagrams"
4. Choose "Add Diagram"
5. Search for your station
6. Enable the diagram
7. Set range (1-10 stations in each direction)
8. Check alert types:
   - ☑ Freight
   - ☑ Steam
   - ☐ RHTT
   - ☐ Charter
   - ☐ Pullman
   - ☐ Royal Train
9. Click Submit

### Automation Example

```yaml
automation:
  - alias: "Freight train in diagram area"
    trigger:
      - platform: event
        event_type: homeassistant_network_rail_uk_track_alert
        event_data:
          diagram_stanox: "32000"
          alert_type: "freight"
    action:
      - service: notify.mobile_app
        data:
          title: "Freight Alert"
          message: >
            {{ trigger.event.data.headcode }} freight train 
            from {{ trigger.event.data.origin }} 
            to {{ trigger.event.data.destination }}
```

### Dashboard Example

```yaml
type: markdown
content: |
  ## Alert Trains in Area
  
  {% set trains = state_attr('sensor.network_rail_integration_diagram_32000', 'trains_in_diagram') %}
  {% set alerts = trains | selectattr('triggers_alert') | list if trains else [] %}
  
  {% if alerts %}
    {% for train in alerts %}
      ### {{ train.headcode }} ⚠️
      - **Type**: {{ train.service_type }}
      - **Route**: {{ train.origin }} → {{ train.destination }}
      - **Alert**: {{ train.alert_reason }}
      - **Time**: {{ (train.time_in_diagram_seconds / 60) | round(1) }} min
    {% endfor %}
  {% else %}
    No alert trains
  {% endif %}
```

## Event Structure

The `homeassistant_network_rail_uk_track_alert` event contains:

```yaml
diagram_stanox: "32000"        # STANOX of diagram center
train_id: "6M94"               # Train identifier
headcode: "6M94"               # Train headcode
alert_type: "freight"          # Type of service
alert_reason: "Freight service" # Why it triggered
current_berth: "SK:M123"       # Current berth location
service_type: "freight"        # Classified service type
origin: "FLIXSTW"             # Origin station
destination: "TRAFFPK"         # Destination station
operator: "Freightliner"       # Train operator
entered_at: "2026-01-07T10:12:08" # Entry timestamp
```

## Breaking Changes

**None** - This is a backward-compatible enhancement.

- Existing Track Section Monitor configurations continue to work
- Existing Network Diagram configurations continue to work
- New alert features are opt-in

## Requirements

For alerts to work, you need:
- Train Describer feed enabled
- VSTP feed enabled (for service classification)
- TD areas configured to cover your diagram area

Without VSTP, trains will still be tracked but service classification and enrichment won't be available.

## Troubleshooting

### Alerts not working

Check:
1. VSTP feed is enabled (Settings → Configure VSTP Feed)
2. Train Describer is enabled
3. TD areas are configured
4. Alert types are checked in diagram configuration

### Trains not appearing in diagram

Check:
1. Alerts are enabled for the diagram (edit diagram to verify)
2. TD messages are being received (check Train Describer status sensor)
3. Berths are within the diagram range

### Events not firing

Check:
1. VSTP feed is enabled for service classification
2. Train matches configured alert types
3. Event listener is configured correctly in automation

## Support

- GitHub Issues: https://github.com/tombanbury-cyber/homeassistant-network-rail-uk/issues
- Documentation: [NETWORK_DIAGRAMS.md](NETWORK_DIAGRAMS.md)
- Examples: [AUTOMATION_EXAMPLES.md](AUTOMATION_EXAMPLES.md)
