import jwt
from fastapi import status, HTTPException, Depends
from typing import Any, Dict
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config.app_config import get_app_config
from app.utils.redis_client import get_redis

config = get_app_config()
security = HTTPBearer()

AUTH0_DOMAIN = config.auth0_domain
API_AUDIENCE = config.auth0_audience
JWKS_URL = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
ISSUER = f"https://{AUTH0_DOMAIN}/"

jwks_client = jwt.PyJWKClient(JWKS_URL)


def revoke_token(jti: str, ttl_seconds: int) -> None:
    """Blacklist a token by its jti claim. TTL should match the token's remaining lifetime."""
    get_redis().setex(f"revoked:{jti}", ttl_seconds, "1")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Validates the Auth0 Access Token and checks the revocation blacklist.
    Requires the jti claim to be enabled in Auth0 API Settings for revocation to work.
    Returns the decoded token payload containing user info.
    """
    token = credentials.credentials
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=API_AUDIENCE,
            issuer=ISSUER,
        )

        jti = payload.get("jti")
        if jti and get_redis().exists(f"revoked:{jti}"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except HTTPException:
        raise
    except Exception:  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature or claims",
        )
