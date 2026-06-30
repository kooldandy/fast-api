---
paths:
  - "app/database/**/*.py"
  - "alembic/**/*.py"
  - "alembic.ini"
---

# Database Rules

- Use SQLAlchemy 2.0 style: `Mapped[type]` with `mapped_column()` — never legacy `Column()`
- Always use `get_db()` generator as a FastAPI Depends — never instantiate sessions directly in routes
- Migrations run via `alembic upgrade head` in CI/CD pipeline — NEVER inside app startup
- Use `NullPool` in alembic env.py for migrations (already configured — do not remove)
- For monetary values use `NUMERIC(10, 2)` in migrations and `Decimal` in Python — never `Float`
- Session lifecycle: yield → rollback on error → close in finally (already in get_db())
- New ORM models must inherit from `Base` (imported from `app.database.schema`)
