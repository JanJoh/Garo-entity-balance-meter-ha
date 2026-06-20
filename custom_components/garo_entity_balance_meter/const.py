DOMAIN = "garo_entity_balance_meter"
PLATFORMS: list[str] = ["sensor"]
MANUFACTURER = "GARO"
PRODUCT_NAME = "Entity Balance"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SLOW_SCAN_INTERVAL = "slow_scan_interval"
CONF_IGNORE_TLS_ERRORS = "ignore_tls_errors"
CONF_USE_HTTP = "use_http"

DEFAULT_SCAN_INTERVAL = 15
DEFAULT_SLOW_SCAN_INTERVAL = 300

API_PATH = "/status/energy-meter"
