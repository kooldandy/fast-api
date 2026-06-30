---
paths:
  - "app/routing/**/*.py"
  - "app/repository/**/*.py"
---

# Routing & Repository Rules

## Routes (app/routing/)
- Routes handle HTTP concerns only — no direct DB queries, no ORM imports
- Every route must inject `ProductRepository` via `Depends(get_product_repo)` — never instantiate it directly
- Every route must have `dependencies=[Depends(get_current_user)]` — no unauthenticated endpoints
- Return correct HTTP status codes: 201 for POST, 204 for DELETE
- Routes should be thin: one line calling the repository method

## Repository (app/repository/)
- All data access logic lives here — routes must not import SQLAlchemy or query the DB directly
- `get_by_id()` raises 404 HTTPException when not found — callers don't need to check
- `update()` raises 400 HTTPException when no fields are provided
- New repositories follow the same class pattern: `__init__(self, db: Session)` + method per operation
- Export new repositories from `app/repository/__init__.py`

## Adding a New Resource
1. Create `app/repository/<resource>.py` with the repository class
2. Export it from `app/repository/__init__.py`
3. Create `app/routing/<resource>.py` with thin route handlers
4. Register the router in `app/app.py`
