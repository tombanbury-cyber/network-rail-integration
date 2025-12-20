"""Constants for the Network Rail integration."""

DOMAIN = "network_rail_integration"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TOPIC = "topic"
CONF_STANOX_FILTER = "stanox_filter"
CONF_STATIONS = "stations"  # List of station configs
CONF_TOC_FILTER = "toc_filter"
CONF_EVENT_TYPES = "event_types"
CONF_FIX_DST_QUIRK = "fix_dst_quirk"

DEFAULT_TOPIC = "TRAIN_MVT_ALL_TOC"

NR_HOST = "publicdatafeeds.networkrail.co.uk"
NR_PORT = 61618

DISPATCH_MOVEMENT = f"{DOMAIN}_movement"
DISPATCH_CONNECTED = f"{DOMAIN}_connected"
