# Repository Pattern — Implementation Guide

## What Changed

The project was refactored from a direct-ORM routing pattern to a Repository Pattern.
All database access logic is now centralized in `app/repository/` instead of living inside route handlers.

---

## Architecture — Before vs After

### Before
```
Route Handler → SQLAlchemy Session (direct queries inline)
```
```python
# app/routing/product.py — direct ORM in routes
@router.get("")
def get_all_product(db: Session = Depends(get_db)):
    return db.query(ProductSchema).all()  # DB logic in route
```

### After
```
Route Handler → ProductRepository → SQLAlchemy Session
```
```python
# app/routing/product.py — thin route, delegates to repository
@router.get("")
def get_all_products(repo: ProductRepository = Depends(get_product_repo)):
    return repo.get_all()

# app/repository/product.py — all DB logic here
def get_all(self) -> list[Product]:
    return self.db.query(Product).all()
```

---

## Project Structure

```
app/
├── repository/
│   ├── __init__.py          # Exports ProductRepository
│   └── product.py           # ProductRepository class — all product DB operations
├── routing/
│   └── product.py           # Thin HTTP handlers — inject repo via Depends()
```

---

## ProductRepository — Method Reference

File: `app/repository/product.py`

| Method | Signature | Returns | Raises |
|---|---|---|---|
| `get_all` | `() → list[Product]` | All product rows | — |
| `get_by_id` | `(id: int) → Product` | Single product | 404 if not found |
| `create` | `(data: ProductCreate) → Product` | Created product | — |
| `update` | `(id: int, data: ProductUpdate) → Product` | Updated product | 404 if not found, 400 if no fields |
| `delete` | `(id: int) → None` | Nothing | 404 if not found |

---

## How Dependency Injection Works

```python
# Dependency chain in app/routing/product.py

def get_product_repo(db: Session = Depends(get_db)) -> ProductRepository:
    return ProductRepository(db)

@router.get("/{id}")
def get_product_by_id(id: int, repo: ProductRepository = Depends(get_product_repo)):
    return repo.get_by_id(id)
```

FastAPI resolves the chain automatically:
```
Request → get_product_repo() → get_db() → yields Session → ProductRepository(session)
```

---

## Why Repository Pattern

| Concern | Before | After |
|---|---|---|
| **Testability** | Must spin up real DB to test routes | Mock `ProductRepository` — no DB needed |
| **Single Responsibility** | Routes mixed HTTP + DB logic | Routes = HTTP only, Repos = DB only |
| **Reusability** | Same query written multiple times | One place to change query logic |
| **Swap-ability** | ORM tightly coupled to routes | Change DB layer without touching routes |

---

## Adding a New Resource (e.g., Orders)

Follow this exact pattern:

### Step 1 — Create the repository
```python
# app/repository/order.py
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.database.schema.order import Order
from app.models.order import OrderCreate, OrderUpdate

class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Order]:
        return self.db.query(Order).all()

    def get_by_id(self, id: int) -> Order:
        order = self.db.query(Order).filter(Order.id == id).first()
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        return order

    def create(self, data: OrderCreate) -> Order:
        order = Order(**data.model_dump())
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def delete(self, id: int) -> None:
        order = self.get_by_id(id)
        self.db.delete(order)
        self.db.commit()
```

### Step 2 — Export from `__init__.py`
```python
# app/repository/__init__.py
from .product import ProductRepository
from .order import OrderRepository

__all__ = ["ProductRepository", "OrderRepository"]
```

### Step 3 — Create thin routes
```python
# app/routing/order.py
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.auth.auth import get_current_user
from app.database.db import get_db
from app.models.order import OrderCreate, OrderResponse
from app.repository.order import OrderRepository

router = APIRouter(prefix="/api/v1/order", tags=["orders"])

def get_order_repo(db: Session = Depends(get_db)) -> OrderRepository:
    return OrderRepository(db)

@router.get("", response_model=list[OrderResponse], dependencies=[Depends(get_current_user)])
def get_all_orders(repo: OrderRepository = Depends(get_order_repo)):
    return repo.get_all()

@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_current_user)])
def add_order(order: OrderCreate, repo: OrderRepository = Depends(get_order_repo)):
    return repo.create(order)
```

### Step 4 — Register in app factory
```python
# app/app.py
from app.routing import product, order

app.include_router(product.router)
app.include_router(order.router)
```

---

## Testing with the Repository Pattern

Because routes now depend on `ProductRepository` (an injectable class), you can override it in tests without a real database:

```python
# tests/test_product_routes.py
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from main import app
from app.repository.product import ProductRepository
from app.routing.product import get_product_repo

client = TestClient(app)

def test_get_all_products():
    mock_repo = MagicMock(spec=ProductRepository)
    mock_repo.get_all.return_value = [
        {"id": 1, "name": "Test", "description": "Desc", "price": 9.99, "quantity": 5}
    ]

    app.dependency_overrides[get_product_repo] = lambda: mock_repo
    response = client.get("/api/v1/product", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    mock_repo.get_all.assert_called_once()
    app.dependency_overrides.clear()
```

---

## Rules (enforced via `.claude/rules/routing.md`)

- Routes must **never** import SQLAlchemy or query the DB directly
- Every route injects its repository via `Depends(get_<resource>_repo)`
- Every route must have `dependencies=[Depends(get_current_user)]`
- `get_by_id()` owns the 404 raise — callers do not need to check for None
- New repositories always follow: `__init__(self, db: Session)` + one method per operation
