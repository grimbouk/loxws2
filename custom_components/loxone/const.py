"""Constants for the Loxone Home Assistant integration."""

from datetime import timedelta

DOMAIN = "loxone"
DEFAULT_TITLE = "Loxone Miniserver"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_USE_TLS = "use_tls"
CONF_VERIFY_SSL = "verify_ssl"

PLATFORMS = [
    "light",
    "sensor",
    "binary_sensor",
    "cover",
    "climate",
    "scene",
]

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
