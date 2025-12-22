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
CONF_ENABLE_TD = "enable_td"  # Enable Train Describer feed
CONF_TD_AREAS = "td_areas"  # List of TD area IDs to track
CONF_TD_PLATFORMS = "td_platforms"  # Dict mapping area_id to list of platform IDs
CONF_TD_EVENT_HISTORY_SIZE = "td_event_history_size"  # Number of events to keep per area
CONF_DIAGRAM_CONFIGS = "diagram_configs"  # List of diagram configurations
# Deprecated constants (kept for migration)
CONF_DIAGRAM_ENABLED = "diagram_enabled"
CONF_DIAGRAM_STANOX = "diagram_stanox"
CONF_DIAGRAM_RANGE = "diagram_range"  # Number of stations each direction

# Default platform range when SMART data is not available
DEFAULT_PLATFORM_RANGE_MIN = 1
DEFAULT_PLATFORM_RANGE_MAX = 10

# Default Train Describer event history size
DEFAULT_TD_EVENT_HISTORY_SIZE = 10

DEFAULT_TOPIC = "TRAIN_MVT_ALL_TOC"
DEFAULT_TD_TOPIC = "TD_ALL_SIG_AREA"

NR_HOST = "publicdatafeeds.networkrail.co.uk"
NR_PORT = 61618

SMART_DATA_URL = "https://publicdatafeeds.networkrail.co.uk/ntrod/SupportingFileAuthenticate?type=SMART"
SMART_CACHE_FILE = "smart_data.json"
SMART_CACHE_EXPIRY_DAYS = 30

DISPATCH_MOVEMENT = f"{DOMAIN}_movement"
DISPATCH_CONNECTED = f"{DOMAIN}_connected"
DISPATCH_TD = f"{DOMAIN}_td"  # Train Describer messages
