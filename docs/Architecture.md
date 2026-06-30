# System Architecture — Product Management API

**Version:** 1.0  
**Stack:** FastAPI · PostgreSQL · Auth0 · AWS Lambda  
**Status:** Active development — pre-production

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Style](#2-architecture-style)
3. [Component Architecture](#3-component-architecture)
4. [Request Lifecycle](#4-request-lifecycle)
5. [Layer Responsibilities](#5-layer-responsibilities)
6. [Data Architecture](#6-data-architecture)
7. [Security Architecture](#7-security-architecture)
8. [Deployment Architecture](#8-deployment-architecture)
9. [Cross-Cutting Concerns](#9-cross-cutting-concerns)
10. [Technology Decisions](#10-technology-decisions)
11. [Architecture Decision Records](#11-architecture-decision-records)
12. [Known Trade-offs](#12-known-trade-offs)
13. [Future Architecture](#13-future-architecture)

---

## 1. System Overview

A RESTful HTTP API for product inventory management. All operations are authenticated via Auth0 JWT tokens. The API is deployed as an AWS Lambda function, backed by a managed PostgreSQL database, and fronted by API Gateway.

```
┌─────────────┐     HTTPS      ┌──────────────┐     invoke    ┌───────────────┐
│  Frontend   │ ─────────────► │ API Gateway  │ ────────────► │ Lambda (API)  │
│ localhost:  │                │  /prod/*     │               │  Mangum ASGI  │
│ 5174 / 3000 │                └──────────────┘               └───────┬───────┘
└─────────────┘                                                        │
                                                              ┌────────▼────────┐
                                                              │   PostgreSQL     │
                                                              │   (RDS/local)    │
                                                              └─────────────────┘

                                  Auth0 Tenant
                              ┌─────────────────┐
                              │ JWKS endpoint   │  ◄──── JWT validation
                              │ /.well-known/   │        on every request
                              │ jwks.json       │
                              └─────────────────┘
```

---

## 2. Architecture Style

**Pattern:** Layered Architecture + Repository Pattern  
**Communication:** Synchronous HTTP/REST  
**State:** Stateless application layer (state lives in PostgreSQL)

### Layer Stack

```
┌────────────────────────────────────────────┐
│             HTTP / Transport               │  FastAPI + Uvicorn / Mangum
├────────────────────────────────────────────┤
│          Middleware Chain                  │  CORS · Rate Limit · Logging
├────────────────────────────────────────────┤
│          Routing Layer                     │  FastAPI APIRouter (thin handlers)
├────────────────────────────────────────────┤
│          Repository Layer                  │  Data access — SQLAlchemy queries
├────────────────────────────────────────────┤
│          Database / ORM Layer              │  SQLAlchemy 2.0 · Alembic
├────────────────────────────────────────────┤
│          PostgreSQL                        │  Persistent store
└────────────────────────────────────────────┘
```

### Horizontal Concerns (applied across all layers)

```
Authentication   ── Auth0 JWT (RS256) validated before routing
Configuration    ── Pydantic BaseSettings, injected via @lru_cache
Error Handling   ── Global exception handlers in app factory
Observability    ── Structured request/response logging with request ID
```

---

## 3. Component Architecture

```
app/
├── app.py                    ← App factory: wires middleware, routers, handlers
│
├── config/
│   └── app_config.py         ← Pydantic BaseSettings; single source of truth for env
│
├── auth/
│   └── auth.py               ← Auth0 JWKS client; get_current_user() dependency
│
├── database/
│   ├── db.py                 ← Engine, SessionMaker, get_db() generator
│   └── schema/
│       └── product.py        ← SQLAlchemy ORM models (declarative, Mapped types)
│
├── models/
│   └── product.py            ← Pydantic schemas: request validation + response shape
│
├── repository/
│   └── product.py            ← ProductRepository: all DB queries live here
│
├── routing/
│   └── product.py            ← Thin HTTP handlers; delegates to repository
│
└── utils/
    ├── limiter.py            ← slowapi Limiter singleton (IP-based rate limiting)
    └── redis_client.py       ← Redis singleton — fakeredis (dev) or real Redis (prod)
```

### Component Dependency Graph

```
routing ──► repository ──► database/schema
   │              │               │
   ├──► models    └──► utils/     └──► database/db
   │              redis_client
   └──► auth ──► config
         │
         └──► utils/redis_client  (revocation blacklist check)
```

No circular dependencies. Each layer depends only on layers below it.

---

## 4. Request Lifecycle

### Authenticated CRUD Request (e.g. GET /api/v1/product)

```
Browser / Client
      │
      │  GET /api/v1/product
      │  Authorization: Bearer <jwt>
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Middleware Chain (applied in order)                            │
│                                                                 │
│  1. ServerErrorMiddleware      ← catches unhandled 500s        │
│  2. CORSMiddleware             ← validates origin, adds headers │
│  3. RequestLoggingMiddleware   ← assigns request_id, logs      │
│  4. SlowAPIMiddleware          ← checks rate limit by IP       │
│  5. ExceptionMiddleware        ← maps exceptions to responses  │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Router                                                 │
│                                                                 │
│  Dependency resolution (parallel):                              │
│    ├── get_current_user()                                       │
│    │     └── Extracts Bearer token                             │
│    │     └── Fetches signing key from Auth0 JWKS (cached)      │
│    │     └── Decodes + validates JWT (RS256, audience, issuer) │
│    │     └── Returns decoded payload (user sub, etc.)          │
│    │                                                            │
│    └── get_product_repo()                                       │
│          └── get_db() → yields SQLAlchemy Session              │
│          └── ProductRepository(session)                        │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Route Handler (app/routing/product.py)                         │
│                                                                 │
│  def get_all_products(request, limit, offset, repo):            │
│      return repo.get_all(limit=limit, offset=offset)           │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  ProductRepository (app/repository/product.py)                  │
│                                                                 │
│  def get_all(limit, offset):                                    │
│      cache_key = f"products:limit={limit}:offset={offset}"     │
│      cached = redis.get(cache_key)    ← cache hit?             │
│      if cached: return deserialize(cached)                      │
│                                                                 │
│      products = db.query(Product)...  ← cache miss → DB        │
│      redis.setex(cache_key, 60, serialize(products))           │
│      return products                                            │
└─────────────────────────────────────────────────────────────────┘
      │
      ├── cache hit ──► Redis (in-memory / Upstash)
      │
      └── cache miss ──► PostgreSQL
                              │
                              ▼
  Pydantic serializes ORM objects → JSON response
      │
      ▼
  200 OK + X-Request-ID header
```

### CORS Preflight (OPTIONS) Lifecycle

```
Browser
  │  OPTIONS /api/v1/product
  │  Origin: http://localhost:5174
  │  Access-Control-Request-Method: GET
  │  Access-Control-Request-Headers: authorization, accept
  ▼
CORSMiddleware
  ├── Origin in allow_origins? → YES
  ├── Method in allow_methods? → YES (GET)
  └── Returns 200 with Access-Control-Allow-* headers
      (request never reaches routing or auth layer)
```

---

## 5. Layer Responsibilities

### App Factory (`app/app.py`)
- Instantiates `FastAPI` with environment-aware config (`root_path`, `swagger_ui_parameters`)
- Registers middleware in correct order (CORS outermost → logging → rate limiter)
- Registers global exception handlers (SQLAlchemy errors → 500, validation errors → 422, rate limit → 429)
- Mounts routers
- **Does not** contain business logic, DB queries, or auth logic

### Config (`app/config/app_config.py`)
- Single `AppConfig` class backed by `pydantic-settings` `BaseSettings`
- Reads from `.env` file; all fields are typed
- Cached with `@lru_cache` — instantiated once per process
- **All other layers import config via `get_app_config()`** — never read env vars directly

### Auth (`app/auth/auth.py`)
- Owns the Auth0 JWT validation contract
- `PyJWKClient` instance is module-level (cached across requests)
- `get_current_user()` is a FastAPI dependency — injected into routes via `dependencies=[Depends(get_current_user)]`
- Returns decoded token payload; routes can extract `sub` (user ID), `email`, etc. from it
- **Does not** persist users — Auth0 is the identity store

### Database (`app/database/`)
- `db.py`: connection string assembly, engine creation, session factory
  - Uses `NullPool` on Lambda to avoid connection exhaustion
  - `get_db()` generator yields a session and always closes it (even on error)
- `schema/`: SQLAlchemy 2.0 declarative models using `Mapped[T]` type annotations
  - `Base` is the single `DeclarativeBase` — all models inherit from it
  - Migrations managed by Alembic — schema changes must go through a migration

### Models (`app/models/`)
- Pydantic v2 schemas: **not** the same as SQLAlchemy models
- Three-schema pattern per resource:
  - `ProductCreate` — POST request body (all fields required, validated)
  - `ProductUpdate` — PATCH request body (all fields optional)
  - `ProductResponse` — API response (includes `id`, ORM mode enabled)
- Field constraints enforced at the API boundary — not trusted from DB reads

### Repository (`app/repository/`)
- The **only** layer that interacts with SQLAlchemy sessions directly
- One class per resource: `ProductRepository(db: Session)`
- Methods map 1:1 to data operations: `get_all`, `get_by_id`, `create`, `update`, `delete`
- Raises `HTTPException` for not-found (404) and empty-patch (400) — routes do not check for `None`
- Pagination applied here: `offset(n).limit(n)` — never `.all()` without bounds

### Routing (`app/routing/`)
- **Thin handlers** — one line each, no business logic
- Responsible for: HTTP method binding, status codes, response model declaration
- All routes use `dependencies=[Depends(get_current_user)]` — authentication is never optional
- `request: Request` is the first parameter on all handlers (required by slowapi)

---

## 6. Data Architecture

### Entity Model

```
┌──────────────────────────────────┐
│           product                │
├──────────────────────────────────┤
│  id          INTEGER  PK AUTO    │
│  name        VARCHAR  NOT NULL   │
│  description VARCHAR  NOT NULL   │
│  price       NUMERIC(10,2) NN    │
│  quantity    INTEGER  NOT NULL   │
└──────────────────────────────────┘
```

### Data Flow: Write Path (POST /api/v1/product)

```
JSON body
  │
  ▼  Pydantic validates (ProductCreate)
  │   - name: 1–100 chars
  │   - description: 1–500 chars
  │   - price: Decimal > 0, max 10 digits, 2 decimal places
  │   - quantity: int >= 0
  ▼
ProductRepository.create(data)
  │
  ▼  SQLAlchemy maps Pydantic → ORM model
  │  db.add(product) → db.commit() → db.refresh(product)
  ▼
PostgreSQL persists row
  │
  ▼  ORM model → Pydantic ProductResponse (from_attributes=True)
  ▼
JSON response (201 Created)
```

### Migration Strategy

- Schema changes go through Alembic revision files in `alembic/versions/`
- Migrations run via `alembic upgrade head` in CI/CD pipeline — **never inside the app**
- `alembic/env.py` imports `Base.metadata` for autogenerate support
- `NullPool` used in `alembic/env.py` — correct for serverless/CI environments

### Migration History

| Revision | Description |
|---|---|
| `b379622f227c` | Initial schema — creates `product` table |
| `a1c3e5f82d4b` | Alters `price` column from `FLOAT` to `NUMERIC(10,2)` |

---

## 7. Security Architecture

### Authentication Flow

```
Client                    API                      Auth0
  │                        │                         │
  │── POST /login ─────────────────────────────────► │
  │◄── access_token (JWT) ──────────────────────────  │
  │                        │                         │
  │── GET /api/v1/product  │                         │
  │   Authorization:       │                         │
  │   Bearer <jwt> ───────►│                         │
  │                        │── fetch JWKS (cached) ──►│
  │                        │◄── public keys ─────────  │
  │                        │                         │
  │                        │  decode + verify JWT:   │
  │                        │  · RS256 signature      │
  │                        │  · audience claim       │
  │                        │  · issuer claim         │
  │                        │  · expiry               │
  │                        │  · jti revocation check │
  │                        │    (Redis blacklist)    │
  │                        │                         │
  │◄── 200 / 401 ──────────│                         │
```

### Security Controls

| Control | Implementation | Layer |
|---|---|---|
| Authentication | Auth0 RS256 JWT via JWKS | `app/auth/auth.py` |
| Token revocation | Redis `jti` blacklist — `revoke_token()` in auth.py | `app/auth/auth.py` + Redis |
| Transport security | HTTPS (API Gateway + ACM cert) | Infrastructure |
| CORS | Explicit origin allowlist, explicit methods | `app/app.py` |
| Rate limiting | IP-based, 10–60 req/min per endpoint | `app/utils/limiter.py` |
| Input validation | Pydantic v2 field constraints | `app/models/` |
| SQL injection prevention | SQLAlchemy ORM parameterized queries | `app/repository/` |
| Secret management | AWS Secrets Manager (production) | Infrastructure |
| Error information leakage | Generic error messages in handlers | `app/app.py` |

### JWT Token Validation (RS256)

```python
# RS256: asymmetric — Auth0 signs with private key, API verifies with public key
# Public keys fetched from: https://{AUTH0_DOMAIN}/.well-known/jwks.json
# PyJWKClient caches public keys — avoids fetching on every request
# Validated claims: signature · aud · iss · exp
```

### Rate Limits by Endpoint

| Endpoint | Limit | Reason |
|---|---|---|
| `GET /api/v1/product` | 60/min | Read-heavy, still bounded |
| `GET /api/v1/product/{id}` | 60/min | Same |
| `POST /api/v1/product` | 20/min | Write operation |
| `PATCH /api/v1/product/{id}` | 20/min | Write operation |
| `DELETE /api/v1/product/{id}` | 10/min | Destructive — most restricted |

> **Production note:** IP-based limiting is ineffective behind API Gateway (all traffic appears as internal IPs). Use API Gateway throttling or per-user limiting keyed on Auth0 `sub` claim.

---

## 8. Deployment Architecture

### Local Development

```
Developer Machine
  │
  uvicorn main:app --reload
  │
  ├── PostgreSQL  (localhost:5432/fastapidb)
  └── Redis       (fakeredis — in-process, no server needed; auto-selected when APP_ENV=development)
```

### AWS Production

```
                            ┌─────────────────────────────────────────────┐
                            │              AWS Account                    │
                            │                                             │
Internet ──► Route 53 ──► API Gateway (/prod stage)                      │
                            │         │                                   │
                            │         │ invoke                            │
                            │         ▼                                   │
                            │   Lambda Function                           │
                            │   ├── main.handler (Mangum)                │
                            │   ├── Runtime: Python 3.12                 │
                            │   └── Memory: configured per load          │
                            │         │                    │              │
                            │         │ VPC               │ HTTPS        │
                            │         ▼                   ▼              │
                            │   RDS PostgreSQL      Upstash Redis        │
                            │   (private subnet)    (serverless,         │
                            │                        no VPC needed)      │
                            │   Secrets Manager                          │
                            │   ├── DB credentials                       │
                            │   ├── Auth0 domain/audience                │
                            │   └── Redis URL / token                    │
                            └─────────────────────────────────────────────┘
```

### Redis Infrastructure Choice

| Option | Latency | Cost | VPC Required | Best For |
|---|---|---|---|---|
| **fakeredis (local)** | in-process | Free | No | Local dev — no server or Docker needed |
| **Upstash (prod)** | 5–15ms | Pay-per-request, free tier | No | Lambda — no VPC complexity |
| **ElastiCache (high traffic)** | <1ms | ~$15+/month | Yes | High-throughput, already in VPC |

**Selected: Upstash for production** — Lambda-native (HTTP-based, no persistent TCP), zero infrastructure config, scales to zero. See [redis_guide.md](./redis_guide.md) for full detail.

### Lambda Cold Start Sequence

```
Cold start
  │
  1. Module imports (FastAPI, SQLAlchemy, etc.)
  2. Config loaded via AppConfig (@lru_cache)
  3. Engine created (NullPool — no persistent connections)
  4. Auth0 JWKS client instantiated (module-level singleton)
  5. FastAPI middleware stack built (lazy, first request only)
  │
  ▼ Warm (subsequent invocations reuse the above)
```

> **Removed from cold start:** Alembic auto-migration. Previously `run_alembic_migrations()` ran on every Lambda startup — a race condition risk under concurrent cold starts. Migrations now run in CI/CD before deployment.

### Mangum ASGI Bridge

```python
# main.py
handler = Mangum(app)   # AWS Lambda handler
                        # Mangum translates API Gateway event → ASGI scope
                        # Forwards X-Forwarded-For as client host (used by rate limiter)
```

---

## 9. Cross-Cutting Concerns

### Structured Logging

Every request gets a UUID `request_id` assigned by the logging middleware. It is:
- Logged at request start (`request_start`) with method + path
- Logged at request end (`request_end`) with status code + duration in ms
- Returned to the client as `X-Request-ID` response header
- Included in error log lines for correlation

```
2026-06-30 10:00:01 INFO app.app request_start id=abc-123 method=GET path=/api/v1/product
2026-06-30 10:00:01 INFO app.app request_end id=abc-123 status=200 duration_ms=42
```

### Error Handling

| Exception | Handler | Response |
|---|---|---|
| `SQLAlchemyError` | Global handler in `app.py` | `500 {"detail": "Database error"}` |
| `RequestValidationError` | Global handler in `app.py` | `422 {"detail": "Validation failed", "errors": [...]}` |
| `RateLimitExceeded` | slowapi built-in | `429 Too Many Requests` |
| `HTTPException` | FastAPI built-in | `4xx` with `{"detail": "..."}` |
| Unhandled | `ServerErrorMiddleware` | `500` (no internals exposed) |

Custom 422 responses strip Pydantic internals and return only `field` and `message` per error — no stack traces or internal type names exposed to clients.

### Health Check

`GET /health` executes `SELECT 1` against the database before responding. Returns:

| State | Status Code | Body |
|---|---|---|
| All healthy | 200 | `{"status": "ok", "database": "ok", "cache": "ok"}` |
| DB unreachable | 503 | `{"status": "error", "database": "unreachable", "cache": "ok"}` |
| Redis unreachable | 503 | `{"status": "error", "database": "ok", "cache": "unreachable"}` |
| Both unreachable | 503 | `{"status": "error", "database": "unreachable", "cache": "unreachable"}` |

---

## 10. Technology Decisions

| Technology | Version | Role | Why |
|---|---|---|---|
| FastAPI | 0.136.3 | Web framework | Async-native, automatic OpenAPI, Pydantic v2 integration, Depends system |
| Pydantic v2 | 2.13.4 | Validation + serialization | Rust-core performance, typed field constraints, `from_attributes` ORM mode |
| SQLAlchemy 2.0 | 2.0.50 | ORM | `Mapped[T]` typed columns, modern session API, works with Alembic |
| Alembic | 1.18.4 | Schema migrations | Autogenerate from ORM metadata, revision-controlled history |
| PostgreSQL | — | Database | ACID compliance, `NUMERIC` type for decimal precision, production-grade |
| Auth0 | — | Identity provider | RS256 asymmetric JWT, JWKS rotation, MFA, no identity code to maintain |
| Mangum | 0.21.0 | Lambda adapter | Translates API Gateway events to ASGI — minimal overhead |
| slowapi | 0.1.9 | Rate limiting | Starlette-native, decorator-based, minimal boilerplate |
| Redis (Upstash) | — | Shared cache + rate limit state | Serverless Redis over HTTPS — no VPC, Lambda-native billing |
| uvicorn | 0.49.0 | ASGI server | Production-grade, supports reload for dev |

---

## 11. Architecture Decision Records

### ADR-001: Repository Pattern over direct ORM in routes

**Decision:** All SQLAlchemy queries are in `app/repository/`, never in route handlers.  
**Reason:** Routes became untestable — to test a route you needed a real database session. Repository pattern allows mocking the data layer in tests via `dependency_overrides`.  
**Consequence:** One extra layer of indirection. Acceptable trade-off — routes are now one-liners, all DB logic is in one predictable location.

---

### ADR-002: NullPool on Lambda, default pool locally

**Decision:** `create_engine(..., poolclass=NullPool)` when `AWS_EXECUTION_ENV` is set.  
**Reason:** Lambda functions have no persistent process. Default SQLAlchemy pool keeps connections open between requests within the same instance, but across concurrent cold starts this exhausts PostgreSQL's `max_connections`. `NullPool` opens and closes a connection per request — stateless, safe for Lambda.  
**Consequence:** Slightly higher per-request latency due to connection establishment. Mitigated in production by RDS Proxy.

---

### ADR-003: Alembic migrations removed from app startup

**Decision:** `run_alembic_migrations()` removed from `@app.on_event("startup")`.  
**Reason:** Multiple Lambda cold starts firing simultaneously would each attempt `alembic upgrade head` on the same database — a race condition that can corrupt migration state.  
**Consequence:** Migrations must be run as an explicit CI/CD step before deploying the Lambda. This is correct behavior — schema changes are deployment events, not runtime events.

---

### ADR-004: `price` as `NUMERIC(10,2)` not `FLOAT`

**Decision:** `price` column is `NUMERIC(10,2)` in PostgreSQL, `Decimal` in Python.  
**Reason:** `FLOAT` uses binary floating-point arithmetic. `0.1 + 0.2 = 0.30000000000000004`. For monetary values this is unacceptable — rounding errors compound over time and cause financial discrepancies.  
**Consequence:** `Decimal` is slightly more verbose than `float` in Python. No meaningful performance difference at this scale.

---

### ADR-006: Upstash Redis over ElastiCache for Lambda

**Decision:** Use Upstash Redis (HTTP/REST-based, serverless) over AWS ElastiCache for the Redis layer.  
**Reason:** ElastiCache requires Lambda to be inside a VPC. VPC Lambda has slower cold starts and needs a NAT Gateway (~$30+/month fixed cost) for internet access. Upstash Redis is accessed over HTTPS — no VPC, no persistent TCP connections, pay-per-request billing that scales to zero like Lambda itself.  
**Consequence:** Slightly higher latency (~5–15ms vs ~1ms for ElastiCache). Acceptable for rate limiting and caching at current scale. If throughput demands sub-millisecond cache latency, migrate to ElastiCache with RDS Proxy and accept the VPC complexity. Migration is a single `REDIS_URL` env var swap — no code changes.

---

### ADR-005: Auth0 over custom JWT implementation

**Decision:** Auth0 as the identity provider with RS256 JWT validation.  
**Reason:** Custom JWT implementations routinely have security vulnerabilities (algorithm confusion attacks, improper claim validation). Auth0 provides: key rotation via JWKS, MFA, social login, user management UI — all without writing auth code.  
**Consequence:** External dependency on Auth0's availability. Mitigated by JWKS key caching and (planned) circuit breaker.

---

## 12. Known Trade-offs

| Trade-off | Current State | Production Resolution |
|---|---|---|
| Rate limiting is IP-based | Ineffective behind API Gateway | Per-user key on Auth0 `sub` claim with Redis backend |
| In-memory rate limit state | Lost on Lambda recycle, not shared across instances | Upstash Redis — see [redis_guide.md](./redis_guide.md) |
| No soft delete / audit trail | Hard deletes, no history | Add `deleted_at` column + Background Tasks audit log |
| No DB query timeout | Slow query can hold Lambda for 15 min | `connect_args={"options": "-c statement_timeout=5000"}` |
| No test suite | Zero automated coverage | Repository Pattern enables mocking — tests are the next step |
| Secrets in `.env` | Dev only — `.gitignore`d | AWS Secrets Manager with `boto3` in production config |
| Single resource (product) | No cross-resource transactions | Unit of Work pattern when Orders/Users are added |

---

## 13. Future Architecture

Refer to [future_design_patterns.md](./future_design_patterns.md) for full implementation detail.

### Phase 1 — Pre-production hardening

```
Current:   Route → Repository → DB
Target:    Route → Service → Repository → DB
```

- **Service Layer:** Business logic home; keeps repositories pure data-access
- **Background Tasks:** Audit logging after write operations (no new dependency)
- **Circuit Breaker:** Auth0 JWKS call protection (`pybreaker`)
- **Redis (Upstash):** Shared rate limit state, response caching, JWT revocation blacklist — see [redis_guide.md](./redis_guide.md)

### Phase 2 — Scale readiness

```
Current:  Single Lambda → RDS (direct)
Target:   Lambda → RDS Proxy → RDS (connection pooling at infrastructure level)
```

- **RDS Proxy:** Solves connection exhaustion without `NullPool` trade-offs
- **Unit of Work:** When Orders resource added — multi-repo atomic transactions
- **Redis:** For shared rate limit state and session caching across Lambda instances

### Phase 3 — Observability

```
Current:  stdout structured logs → CloudWatch
Target:   Distributed tracing + metrics + alerts
```

- **AWS X-Ray** or **OpenTelemetry** for distributed tracing across Lambda invocations
- **CloudWatch Alarms** on 4xx/5xx rates, Lambda duration, DB connection count
- **Structured log format** migrated to JSON for CloudWatch Insights querying
