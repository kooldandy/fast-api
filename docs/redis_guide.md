# Redis Integration Guide

Redis is a key-value store used for caching, shared state, and pub/sub. In this project it solves problems that PostgreSQL and Lambda's in-memory state cannot: shared rate limit counters, response caching, and token revocation.

---

## Redis = Infrastructure + Library

Redis is **not** a pure Python library. You need a running Redis server AND a Python client.

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI App (Lambda)                                   │
│                                                         │
│  pip install redis   ← Python client (talks to server)  │
│       │                                                 │
│       │  TCP (standard) or HTTPS (Upstash)              │
│       ▼                                                 │
│  Redis Server  ← must be running separately             │
│  (Docker / ElastiCache / Upstash)                       │
└─────────────────────────────────────────────────────────┘
```

---

## What Redis Solves in This Project

| Problem | Current State | With Redis |
|---|---|---|
| Rate limit state lost on Lambda recycle | In-memory, per-instance | Shared counter across all Lambda instances |
| Each Lambda cold-start re-fetches JWKS | One fetch per instance | Single cached key shared across all instances |
| Every `GET /product` hits PostgreSQL | No caching layer | Cache product list, invalidate on write |
| JWT tokens cannot be revoked server-side | No blacklist mechanism | Store revoked `jti` claims with TTL = token expiry |

---

## Infrastructure Options

### Local Development — fakeredis (No Server Needed)

`fakeredis` is a Python library that runs Redis entirely in-memory. No Docker, no server, no account.

```bash
pip install fakeredis
```

The `redis_client.py` singleton detects `app_env == "development"` and uses `fakeredis.FakeRedis` automatically — no `.env` change needed. State resets every time the server restarts, which is fine for local dev.

**If you want a persistent local Redis** (e.g. to test across restarts), Docker is an option when available:

```bash
docker run -d --name redis-dev -p 6379:6379 redis:alpine
```

Add to `.env` and switch `app_env` to a non-development value, or point to localhost directly.

---

### Production — Option A: AWS ElastiCache

```
Lambda (must be in VPC) ──TCP──► ElastiCache Redis (private subnet)
```

**Pros:** Low latency, AWS-managed, automatic failover  
**Cons:**
- Lambda must be inside a VPC → slower cold starts
- VPC Lambda needs NAT Gateway for internet access → ~$30+/month fixed cost
- Minimum instance cost: ~$15–25/month for `cache.t3.micro`

**Best for:** High-throughput APIs already in a VPC, or when you're using RDS (already in VPC anyway)

```python
# .env (production)
REDIS_URL=redis://your-elasticache-endpoint:6379
```

---

### Production — Option B: Upstash Redis (Recommended for Lambda)

```
Lambda (no VPC needed) ──HTTPS──► Upstash Redis (REST API)
```

**Pros:**
- HTTP/REST-based — no persistent TCP connection (perfect for Lambda's stateless model)
- No VPC required — works from anywhere over HTTPS
- Pay-per-request billing — Lambda-native, scales to zero
- Free tier: 10,000 requests/day
- TLS built-in

**Cons:** Slightly higher latency than ElastiCache (~5–15ms vs ~1ms) for very high-frequency access

**Cost:** Free tier → ~$0.20 per 100k requests

```bash
pip install upstash-redis
```

```python
# .env (production)
UPSTASH_REDIS_REST_URL=https://your-instance.upstash.io
UPSTASH_REDIS_REST_TOKEN=your-token
```

---

## Recommendation

| Environment | Redis Option | Why |
|---|---|---|
| Local dev | `fakeredis` (in-process) | Zero setup, no server, no Docker needed |
| Production (Lambda) | Upstash Redis | No VPC needed, serverless billing, HTTPS |
| Production (high throughput) | ElastiCache | Sub-millisecond latency, but requires VPC |

**Start with Upstash** — migration to ElastiCache is just swapping `REDIS_URL`. No code changes needed.

---

## Implementation

### 1. Add to requirements.txt

```
fakeredis==2.28.1     # in-process Redis for local dev (no server needed)
redis==5.2.1          # real Redis client for production
```

### 2. Add config fields

```python
# app/config/app_config.py
class AppConfig(BaseSettings):
    ...
    redis_url: str = "redis://localhost:6379"  # overridden in prod via env var
```

### 3. Redis client singleton

The singleton auto-selects the backend based on `app_env`:

```python
# app/utils/redis_client.py
import redis
from app.config.app_config import get_app_config

_client: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        config = get_app_config()
        if config.app_env == "development":
            import fakeredis
            _client = fakeredis.FakeRedis(decode_responses=True)
        else:
            _client = redis.from_url(config.redis_url, decode_responses=True)
    return _client
```

No code change needed when moving from local dev to production — just set `APP_ENV=production` and `REDIS_URL=rediss://your-upstash-url`.

---

## Use Case 1 — Shared Rate Limiting (Priority: High)

Current in-memory state is per-Lambda-instance. Under concurrent invocations, each instance has its own counter — a user can exceed the limit by hitting different instances.

```python
# app/utils/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config.app_config import get_app_config

config = get_app_config()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://" if config.app_env == "development" else config.redis_url,
)
```

- **Development:** `memory://` — in-process, resets on restart (consistent with `fakeredis` behaviour)
- **Production:** `config.redis_url` — shared counter across all Lambda instances

slowapi uses the `limits` library which supports Redis storage natively — no other changes needed.

---

## Use Case 2 — Response Caching (Priority: Medium)

Cache the product list to avoid hitting PostgreSQL on every read. Invalidate on any write operation.

```python
# app/repository/product.py
import json
from decimal import Decimal
from app.utils.redis_client import get_redis

CACHE_TTL = 60  # seconds

class ProductRepository:

    def get_all(self, limit: int = 20, offset: int = 0) -> list[Product]:
        cache_key = f"products:limit={limit}:offset={offset}"
        redis = get_redis()

        cached = redis.get(cache_key)
        if cached:
            # deserialize and return — no DB hit
            return [Product(**p) for p in json.loads(cached)]

        products = self.db.query(Product).offset(offset).limit(limit).all()
        redis.setex(
            cache_key,
            CACHE_TTL,
            json.dumps([
                {"id": p.id, "name": p.name, "description": p.description,
                 "price": str(p.price), "quantity": p.quantity}
                for p in products
            ])
        )
        return products

    def _invalidate_cache(self) -> None:
        redis = get_redis()
        keys = redis.keys("products:*")
        if keys:
            redis.delete(*keys)

    def create(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        self._invalidate_cache()
        return product

    def update(self, id: int, data: ProductUpdate) -> Product:
        ...
        self.db.commit()
        self.db.refresh(product)
        self._invalidate_cache()
        return product

    def delete(self, id: int) -> None:
        ...
        self.db.commit()
        self._invalidate_cache()
```

> **Note on Decimal serialization:** PostgreSQL `NUMERIC` maps to Python `Decimal`. JSON doesn't support `Decimal` natively — serialize with `str(p.price)` and deserialize with `Decimal(p["price"])`.

---

## Use Case 3 — JWT Token Revocation (Priority: Medium)

Auth0 tokens cannot be revoked server-side without a blacklist. If a user logs out or is suspended, their token remains valid until expiry. Redis solves this with a blacklist keyed on the `jti` (JWT ID) claim with TTL matching the token's expiry.

```python
# app/auth/auth.py
from app.utils.redis_client import get_redis

def revoke_token(jti: str, ttl_seconds: int) -> None:
    redis = get_redis()
    redis.setex(f"revoked:{jti}", ttl_seconds, "1")

def is_token_revoked(jti: str) -> bool:
    redis = get_redis()
    return redis.exists(f"revoked:{jti}") == 1

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(token, signing_key.key, algorithms=["RS256"], ...)

        # check revocation blacklist
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")

        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
```

> **Requires:** Auth0 tokens must include the `jti` claim. Enable this in the Auth0 Dashboard under API Settings → Enable Access Token Revocation.

---

## Use Case 4 — JWKS Key Caching (Priority: Low)

The current `PyJWKClient` caches JWKS keys in-process (per Lambda instance). With Redis, all instances share one cached copy and avoid redundant Auth0 fetches on cold starts.

This is low priority because `PyJWKClient`'s in-process cache already handles the common case well. Only implement if Auth0 rate-limits JWKS fetches under high cold-start volume.

---

## Health Check Update

Add Redis to the health check endpoint:

```python
# app/app.py
@app.get("/health", tags=["health"])
def health_check(db: Session = Depends(get_db)):
    health = {"status": "ok", "database": "ok", "cache": "ok"}

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check DB ping failed")
        health["database"] = "unreachable"
        health["status"] = "error"

    try:
        get_redis().ping()
    except Exception:
        logger.exception("Health check Redis ping failed")
        health["cache"] = "unreachable"
        health["status"] = "error"

    status_code = 200 if health["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=health)
```

---

## Architecture Impact

```
Before Redis:
  Request → Lambda (in-memory rate limit, no cache) → PostgreSQL

After Redis:
  Request → Lambda → Redis (rate limit check, cache hit?)
                       │ cache miss
                       ▼
                    PostgreSQL
```

---

## Implementation Roadmap

| Use Case | Status | Notes |
|---|---|---|
| Shared rate limiting | ✅ Done | `memory://` dev, `config.redis_url` prod — `app/utils/limiter.py` |
| Response caching | ✅ Done | 60s TTL on `get_all()`, cache invalidated on write — `app/repository/product.py` |
| JWT revocation blacklist | ✅ Done | `revoke_token()` + `jti` check in `get_current_user()` — `app/auth/auth.py` |
| Redis health check | ✅ Done | `GET /health` pings Redis, returns `{"cache": "ok\|unreachable"}` — `app/app.py` |
| JWKS key caching | ⬜ Low priority | Only needed if hitting Auth0 JWKS rate limits at high cold-start volume |

---

## Files Changed

| File | Change |
|---|---|
| `requirements.txt` | Added `redis==5.2.1`, `fakeredis==2.28.1` |
| `app/config/app_config.py` | Added `redis_url: str = "redis://localhost:6379"` |
| `app/utils/redis_client.py` | New — singleton, auto-selects `fakeredis` (dev) or real Redis (prod) |
| `app/utils/limiter.py` | `storage_uri="memory://"` in dev, `config.redis_url` in prod |
| `app/repository/product.py` | `get_all()` cache get/set, `_invalidate_cache()` on create/update/delete |
| `app/auth/auth.py` | `revoke_token()` helper + `jti` blacklist check in `get_current_user()` |
| `app/app.py` | `/health` pings Redis, reports `cache` status alongside `database` |
