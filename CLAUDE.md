# Product Management API — Claude Instructions

## Project Overview
FastAPI REST API for product management. PostgreSQL database, Auth0 JWT authentication, deployed on AWS Lambda via Mangum.

## Stack
- Python + FastAPI 0.136.3
- SQLAlchemy 2.0 (Mapped types), Alembic migrations
- PostgreSQL via psycopg2-binary
- Auth0 RS256 JWT authentication
- AWS Lambda + Mangum ASGI adapter
- Pydantic v2 for request/response validation

## Project Layout
```
main.py                  # Entry point — Lambda handler + local uvicorn
app/
  app.py                 # FastAPI factory, middleware, startup hooks
  config/app_config.py   # Pydantic BaseSettings, @lru_cache
  auth/auth.py           # Auth0 JWKS + PyJWT validation
  database/
    db.py                # Engine, session, get_db() generator
    schema/product.py    # SQLAlchemy ORM model
  models/product.py      # Pydantic request/response schemas
  repository/product.py  # Data access layer — ProductRepository class
  routing/product.py     # CRUD routes — prefix /api/v1/product (thin, delegates to repository)
alembic/                 # DB migrations — run via CI/CD, not app startup
```

## Commands
- Local dev: `uvicorn main:app --reload`
- Migrations: `alembic upgrade head` (run manually or in CI — NOT inside app)
- Install: `pip install -r requirements.txt`

## Code Conventions
- All routes require `Depends(get_current_user)` — never skip auth
- Use `get_product_or_404()` helper for any endpoint that fetches by ID
- SQLAlchemy 2.0 style: `Mapped[type]` columns, not `Column()`
- Pydantic v2: use `model_config = ConfigDict(from_attributes=True)` for ORM schemas
- Never commit `.env` — use AWS Secrets Manager in production

## Documentation Index (docs/)
Before suggesting fixes, improvements, or architectural changes — check these first:

| File | Contents |
|---|---|
| `docs/Improvement/1_app_improvement.md` | Full production readiness audit — critical/high/medium issues with a prioritized fix roadmap |
| `docs/CLAUDE_OPTIMIZATION.md` | All Claude Code config files added to this project and why |
| `docs/repository_pattern.md` | Repository pattern implementation — method reference, adding new resources, testing guide |
| `docs/future_design_patterns.md` | Future scope — Service Layer, Unit of Work, Background Tasks, Circuit Breaker, CQRS with implementation roadmap |
| `docs/Architecture.md` | Full system architecture — component map, request lifecycle, security, deployment, ADRs, trade-offs |
| `docs/data_migrations.md` | Data migration guide — 5 patterns (SQL fix, Python logic, batching, expand-contract, standalone scripts) |
| `docs/redis_guide.md` | Redis integration — infrastructure options (Docker/Upstash/ElastiCache), 4 use cases, full implementation roadmap |

Rules:
- Do not re-suggest improvements already tracked in `docs/Improvement/`
- When fixing an issue from the improvement list, mark it done in the relevant doc
- New architectural decisions should be documented in `docs/` before implementation

## Known Issues (Tracked in docs/Improvement/1_app_improvement.md)
- Auto-migration on Lambda cold start is a race condition — move to CI/CD
- GET / has no pagination — add limit/offset before production
- price field uses float — migrate to Decimal/NUMERIC(10,2)
- CORS allow_methods=["*"] — tighten before production
