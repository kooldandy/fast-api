# App Production Readiness — Improvement Plan

**Verdict: NOT production-ready.** Several critical and high-severity gaps must be addressed before pushing to production.

---

## Critical — Must Fix Before PROD

### 1. Secrets in `.env` / Version Control

The `.env` file contains plaintext credentials:

```
DB_PASSWORD=admin
AUTH0_DOMAIN=dev-k5bicoa4osz6ayfn.us.auth0.com
```

- `admin` is a weak DB password
- The Auth0 domain is `dev-*` — it's a **development tenant**, not a production one
- If `.env` is committed to git, credentials are exposed

**Fix:** Use AWS Secrets Manager or Parameter Store; never commit `.env`

---

### 2. Auto-Migration on Lambda Cold Start is a Race Condition

- [x] **Fixed:** Removed `run_alembic_migrations()` from `app/app.py` startup hook entirely. Migrations must be run via `alembic upgrade head` in CI/CD before deploying.

---

### 3. No Pagination on List Endpoint

- [x] **Fixed:** `GET /api/v1/product` now accepts `limit` (1–100, default 20) and `offset` (default 0) query params. Repository `get_all()` uses `.offset().limit()`. See `app/routing/product.py` and `app/repository/product.py`.

---

### 4. `price` Uses `float` Instead of `NUMERIC`

- [x] **Fixed:** `price` is now `Decimal` in Pydantic schemas (`app/models/product.py`) and `Numeric(10, 2)` in the ORM model (`app/database/schema/product.py`). Migration `a1c3e5f82d4b_price_float_to_numeric.py` alters the column type in PostgreSQL.

---

## High — Serious Production Risk

### 5. No Structured Logging

- [x] **Fixed:** Added HTTP middleware in `app/app.py` that logs every request with a UUID request ID, method, path, status code, and duration in ms. Request ID is also returned as `X-Request-ID` response header for tracing. SQLAlchemy error handler now logs the request ID alongside the error.

---

### 6. No Rate Limiting

- [x] **Fixed:** Added `slowapi==0.1.9` with IP-based rate limiting via `get_remote_address`. Limits per endpoint:
  - `GET /` and `GET /{id}` — 60/minute
  - `POST /` and `PATCH /{id}` — 20/minute
  - `DELETE /{id}` — 10/minute
  - Exceeding the limit returns HTTP 429 automatically.
  - Limiter registered in `app/utils/limiter.py`, wired into `app/app.py` via `SlowAPIMiddleware`.
  - **Production note:** IP-based limiting does not work correctly behind API Gateway — all Lambda invocations appear to come from the same internal IP, so the rate limit becomes shared across all users rather than per-caller. Two options for production:
    1. **API Gateway throttling (recommended):** Set burst and rate limits at the API Gateway stage level — no code change needed, enforced before Lambda is even invoked.
    2. **Per-user limiting in code:** Replace `get_remote_address` in `app/utils/limiter.py` with a custom key function that extracts the Auth0 `sub` claim from the `Authorization` header. Requires Redis as the storage backend (in-memory store does not persist across Lambda cold starts).

---

### 7. Database Connection Pool Not Tuned for Lambda

- [x] **Fixed:** `app/database/db.py` now detects Lambda via `AWS_EXECUTION_ENV` / `LAMBDA_TASK_ROOT` env vars and uses `NullPool` on Lambda. Local dev retains the default connection pool for performance.

---

### 8. CORS is Too Permissive

- [x] **Fixed:** `app/app.py` now explicitly lists `allow_methods=["GET", "POST", "PATCH", "DELETE"]` and `allow_headers=["Authorization", "Content-Type"]` instead of `["*"]`.

---

### 9. No Request Validation Error Customization

- [x] **Fixed:** Added `RequestValidationError` handler in `app/app.py` that returns clean `{"detail": "Validation failed", "errors": [{"field": "...", "message": "..."}]}` responses instead of verbose Pydantic internals.

---

### 10. No Meaningful Health Check for DB

- [x] **Fixed:** `GET /health` in `app/app.py` now executes `SELECT 1` against the database. Returns `{"status": "ok", "database": "ok"}` on success or HTTP 503 `{"status": "error", "database": "unreachable"}` on failure.

---

## Medium — Important but Won't Cause Immediate Outages

| Issue | Status | Notes |
|---|---|---|
| No request ID / correlation ID tracing | ✅ Fixed | UUID injected per request via middleware, returned as `X-Request-ID` header |
| No timeout on DB queries | ⬜ Pending | Add `connect_args={"options": "-c statement_timeout=5000"}` to engine |
| No soft delete / audit trail | ⬜ Pending | Add `deleted_at` column and filter in repository |
| `utils/` directory is empty | ⬜ Pending | Remove or populate |
| `app_env` flag is read but never used | ✅ Fixed | Now controls `persistAuthorization` in Swagger UI |
| No test suite | ⬜ Pending | See `docs/repository_pattern.md` for testing approach with mocked repo |
| Swagger UI has `persistAuthorization: True` | ✅ Fixed | Now `False` when `app_env == "production"` |

---

## What Is Already Good

| Strength | Why It Matters |
|---|---|
| Auth0 RS256 JWT with JWKS caching | Correct asymmetric auth pattern |
| SQLAlchemy 2.0 `Mapped` types | Modern, type-safe ORM usage |
| Pydantic v2 field validation | Strong input validation at the API boundary |
| Alembic migrations with `NullPool` | Correct pattern for schema versioning |
| Mangum + Lambda adapter | Clean serverless deployment approach |
| Layered architecture + Repository Pattern | Easy to extend and test independently |
| `@lru_cache` on config | Efficient — avoids re-reading env on every request |

---

## Prioritized Fix Roadmap

### Phase 1 — Before Any PROD Deploy (Blocking)

- [ ] Move secrets to AWS Secrets Manager / Parameter Store
- [ ] Switch Auth0 tenant from `dev-*` to a production tenant
- [x] Move Alembic migrations out of app startup into CI/CD pipeline
- [x] Add pagination to `GET /api/v1/product`

### Phase 2 — Before First Real Traffic

- [x] Fix DB connection pooling for Lambda (`NullPool`)
- [x] Add structured logging with request tracing
- [x] Change `price` from `float` to `Decimal` / `NUMERIC(10, 2)`
- [x] Add DB health check to `GET /health`

### Phase 3 — Hardening

- [x] Add rate limiting (`slowapi` — IP-based, 10–60 req/min per endpoint)
- [x] Tighten CORS to explicit methods and headers
- [ ] Add integration and unit tests
- [ ] Add query timeout on DB operations
- [x] Add custom 422 validation error handler
- [x] Disable `persistAuthorization` in Swagger UI for production
