# Network Rail Integration – Home Assistant Integration

Connects to Network Rail's public **STOMP** broker and subscribes to **Train Movements** (default topic: `TRAIN_MVT_ALL_TOC`).

## Entities

- **Binary sensor**: Feed connected
- **Sensor**: Last movement (state = `event_type`, with useful attributes)

## Install (HACS)

1. Add this repository in HACS as a **Custom repository** (category: Integration).
2. Install.
3. Restart Home Assistant.
4. Add via **Settings → Devices & services → Add integration → Network Rail Integration**.

## Options

After adding the integration, open **Configure**:

- `stanox_filter`: Only keep movements for a single STANOX (`loc_stanox`) value.
  - You can enter a STANOX code directly (e.g., `72410` for London Euston)
  - Or use the **"Search for station by name"** option to find the STANOX code by searching for the station name
- `toc_filter`: Only keep movements for a single `toc_id`.
- `event_types`: Only keep movements whose `event_type` is in the list.

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
