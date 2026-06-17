import jwt
from fastapi import status, HTTPException, Depends
from typing import Any, Dict
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config.app_config import get_app_config

config = get_app_config()
security = HTTPBearer()

# Configuration from your Auth0 Dashboard
AUTH0_DOMAIN = config.auth0_domain
API_AUDIENCE = config.auth0_audience # Created in Auth0 -> APIs

# Auth0 publishes its public keys at this specific endpoint
JWKS_URL = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
ISSUER = f"https://{AUTH0_DOMAIN}/"

# Instantiating this globally ensures PyJWT handles caching correctly
jwks_client = jwt.PyJWKClient(JWKS_URL)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    FastAPI security dependency that validates the Auth0 Access Token.
    Returns the decoded token payload containing user info.
    """
    token = credentials.credentials
    try:
        # Fetch key from local cache (or JWKS URL if expired/missing)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Validate the token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=API_AUDIENCE,
            issuer=ISSUER
        )
        return payload  
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except Exception as e: # type: ignore
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature or claims"
        )
