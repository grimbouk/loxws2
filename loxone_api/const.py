"""Constants for the Loxone Miniserver client."""

DEFAULT_PORT = 80
DEFAULT_TLS_PORT = 443
DEFAULT_WS_PATH = "/ws/rfc6455"
DEFAULT_STRUCT_PATH = "/data/LoxAPP3.json"

TOKEN_REFRESH_THRESHOLD = 300  # seconds before expiry when refresh should occur
PING_INTERVAL = 25
RECONNECT_DELAY = 10
