# Open Rail Data (Network Rail) – Home Assistant Integration

Connects to Network Rail's public **STOMP** broker and subscribes to **Train Movements** (default topic: `TRAIN_MVT_ALL_TOC`).

## Entities

- **Binary sensor**: Feed connected
- **Sensor**: Last movement (state = `event_type`, with useful attributes)

## Install (HACS)

1. Add this repository in HACS as a **Custom repository** (category: Integration).
2. Install.
3. Restart Home Assistant.
4. Add via **Settings → Devices & services → Add integration → Open Rail Data (Network Rail)**.

## Options

After adding the integration, open **Configure**:

- `stanox_filter`: Only keep movements for a single STANOX (`loc_stanox`) value.
- `toc_filter`: Only keep movements for a single `toc_id`.
- `event_types`: Only keep movements whose `event_type` is in the list.

## Logging

```yaml
logger:
  default: info
  logs:
    openraildata: debug
```
