from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config.app_config import get_app_config

config = get_app_config()

# Development: in-memory storage (no Redis server needed, state resets on restart)
# Production:  Redis storage via config.redis_url — shared across all Lambda instances
# For per-user limiting (recommended over IP-based behind API Gateway), swap
# key_func to extract the Auth0 sub claim from the Authorization header.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://" if config.app_env == "development" else config.redis_url,
)
