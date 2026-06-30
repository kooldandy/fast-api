---
paths:
  - "app/auth/**/*.py"
---

# Auth Rules

- Auth0 RS256 JWT — do not switch to HS256 (symmetric keys are insecure for this pattern)
- JWKS client is a module-level singleton — do not instantiate it per-request
- get_current_user() must always validate: signature, audience, issuer, and expiry
- Return 401 (not 403) for auth failures — 403 is for authorization, 401 is for authentication
- Never log or return the raw JWT token in error responses
- The decoded payload contains the Auth0 `sub` claim (user ID) — use this for audit logging
