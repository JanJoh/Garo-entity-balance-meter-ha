DOMAIN = "garo_entity_balance_meter"
PLATFORMS: list[str] = ["sensor", "update"]
MANUFACTURER = "GARO"
PRODUCT_NAME = "Entity Balance"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SLOW_SCAN_INTERVAL = "slow_scan_interval"
CONF_IGNORE_TLS_ERRORS = "ignore_tls_errors"
CONF_USE_HTTP = "use_http"
CONF_ENABLE_DLM = "enable_dlm"

# Keys that belong in entry.data (connection identity and secrets), never in entry.options.
DATA_KEYS = (CONF_HOST, CONF_USERNAME, CONF_PASSWORD)

DEFAULT_SCAN_INTERVAL = 15
DEFAULT_SLOW_SCAN_INTERVAL = 300
DEFAULT_ENABLE_DLM = True

# DLM sensors become unavailable when the newest "DLM limits" log line is older than this.
DLM_STALE_SECONDS = 300

API_PATH = "/status/energy-meter"
