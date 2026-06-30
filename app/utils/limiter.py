from slowapi import Limiter
from slowapi.util import get_remote_address

# Key function uses client IP. Behind API Gateway/Lambda, Mangum forwards the
# real client IP via X-Forwarded-For, which get_remote_address reads correctly.
# For per-user limiting (recommended in production), swap key_func to extract
# the Auth0 sub claim from the Authorization header instead.
limiter = Limiter(key_func=get_remote_address)
