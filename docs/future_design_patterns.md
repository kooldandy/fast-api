# Future Design Patterns — Scope & Roadmap

Patterns considered for this project beyond the current implementation. Each entry covers what it adds, how it fits the existing architecture, and when to introduce it.

**Current patterns already in place:**
- Layered Architecture (config / auth / database / models / repository / routing)
- Repository Pattern (`app/repository/`)
- Dependency Injection (FastAPI `Depends`)
- Singleton (`@lru_cache` on config, `limiter` in `app/utils/`)
- Factory (FastAPI app factory in `app/app.py`)

---

## 1. Service Layer

**Priority:** High — add when first business rule appears  
**Effort:** Low

### What it adds
A layer between routes and repositories for business logic. Currently routes call repositories directly — fine for pure CRUD, but as rules grow ("no duplicate product names", "archive instead of delete", "block creation when quantity is 0"), there is no clean place for them to live.

### Architecture
```
Route → Service → Repository → DB
```

### Implementation
```python
# app/service/product.py
class ProductService:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    def create(self, data: ProductCreate) -> Product:
        existing = self.repo.get_by_name(data.name)
        if existing:
            raise HTTPException(status_code=409, detail="Product already exists")
        return self.repo.create(data)

    def delete(self, id: int) -> None:
        # example: soft-delete instead of hard-delete
        product = self.repo.get_by_id(id)
        product.deleted_at = datetime.utcnow()
        self.repo.save(product)
```

```python
# app/routing/product.py — inject service instead of repo directly
def get_product_service(repo: ProductRepository = Depends(get_product_repo)) -> ProductService:
    return ProductService(repo)

@router.post("")
def add_product(product: ProductCreate, service: ProductService = Depends(get_product_service)):
    return service.create(product)
```

### When to introduce
The moment any route handler contains an `if` statement that is not HTTP-concern logic (not a 404 check, not a 400 validation). That logic belongs in the service.

### Tradeoff
Adds a layer for a currently pure-CRUD app. The overhead is worthwhile as soon as business rules appear — without it, logic leaks into routes or repositories.

---

## 2. Unit of Work

**Priority:** Medium — add when second resource is introduced  
**Effort:** Medium

### What it adds
Wraps multiple repository operations into a single atomic transaction. When `Orders` are added that decrement product `quantity`, both operations must succeed or both must roll back. The current single-session approach works for one resource but becomes fragile across two.

### Implementation
```python
# app/database/unit_of_work.py
from contextlib import contextmanager
from sqlalchemy.orm import Session
from app.repository.product import ProductRepository
from app.repository.order import OrderRepository

class UnitOfWork:
    def __init__(self, db: Session):
        self.db = db
        self.products = ProductRepository(db)
        self.orders = OrderRepository(db)

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()


def get_uow(db: Session = Depends(get_db)) -> UnitOfWork:
    return UnitOfWork(db)
```

```python
# usage in service
class OrderService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    def place_order(self, order_data: OrderCreate) -> Order:
        product = self.uow.products.get_by_id(order_data.product_id)
        if product.quantity < order_data.quantity:
            raise HTTPException(400, "Insufficient stock")
        product.quantity -= order_data.quantity
        order = self.uow.orders.create(order_data)
        self.uow.commit()
        return order
```

### When to introduce
When a second resource is added (e.g., Orders, Users) that must interact with products in the same transaction.

### Tradeoff
Overhead for a single-resource app. Essential for multi-resource atomic operations.

---

## 3. Background Tasks

**Priority:** High — can be added immediately  
**Effort:** Zero (built into FastAPI, no new dependency)

### What it adds
Runs work after the HTTP response is sent — audit logging, email notifications, cache invalidation, webhook calls. Directly addresses the "no audit trail" gap in `docs/Improvement/1_app_improvement.md`.

### Implementation
```python
# app/routing/product.py
from fastapi import BackgroundTasks

@router.post("", status_code=status.HTTP_201_CREATED)
def add_product(
    request: Request,
    product: ProductCreate,
    background_tasks: BackgroundTasks,
    repo: ProductRepository = Depends(get_product_repo),
):
    result = repo.create(product)
    background_tasks.add_task(audit_log, action="product.created", resource_id=result.id, request=request)
    return result


# app/utils/audit.py
import logging

audit_logger = logging.getLogger("audit")

def audit_log(action: str, resource_id: int, request: Request) -> None:
    user_sub = getattr(request.state, "user_sub", "unknown")
    audit_logger.info("action=%s resource_id=%s user=%s", action, resource_id, user_sub)
```

### When to introduce
Immediately — there is no reason to delay. It closes the audit trail gap with no added dependencies or complexity.

### Tradeoff
None for low-throughput use. For high-throughput production, offload heavy background work to a proper task queue (Celery + Redis, AWS SQS) so Lambda timeouts don't cut background tasks short.

---

## 4. Circuit Breaker

**Priority:** Medium — add before production traffic  
**Effort:** Low (one dependency: `pybreaker`)

### What it adds
Protects the app when Auth0's JWKS endpoint is unreachable. Currently every request with an expired signing key hits Auth0 directly. If Auth0 is degraded, all authenticated requests hang until they time out — causing cascading failures.

A circuit breaker trips after N consecutive failures, returning a fast error for subsequent requests until Auth0 recovers.

### Implementation
```python
# pip install pybreaker
# requirements.txt: pybreaker==1.2.0

# app/auth/auth.py
from pybreaker import CircuitBreaker, CircuitBreakerError

auth_breaker = CircuitBreaker(fail_max=3, reset_timeout=30)

@auth_breaker
def _fetch_signing_key(token: str):
    return jwks_client.get_signing_key_from_jwt(token)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        signing_key = _fetch_signing_key(token)
    except CircuitBreakerError:
        raise HTTPException(status_code=503, detail="Auth service temporarily unavailable")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token signature or claims")
    ...
```

### When to introduce
Before the first production deployment. Auth0 outages are rare but real — without this the entire API goes down with it.

### Tradeoff
Adds `pybreaker` dependency. Requires tuning `fail_max` and `reset_timeout` to match Auth0's typical recovery time.

---

## 5. CQRS — Command Query Responsibility Segregation

**Priority:** Low — skip for current scale  
**Effort:** High

### What it adds
Separates read models (queries) from write models (commands). Read paths can be optimized independently (caching, read replicas, denormalized views) from write paths (validation, events, transactions).

### When to introduce
Only when read and write workloads diverge significantly — e.g., the product list endpoint becomes the bottleneck but write operations remain infrequent. At current scale this is over-engineering.

### Tradeoff
Significant complexity increase. Separate read/write models, separate handlers, potential eventual consistency issues. Not justified until profiling shows a clear read/write bottleneck.

---

## Implementation Roadmap

| Pattern | Add When | Closes Gap In |
|---|---|---|
| **Background Tasks** | Now | `docs/Improvement/1_app_improvement.md` — no audit trail |
| **Service Layer** | First business rule added | Nothing yet — future-proofing |
| **Circuit Breaker** | Before production | `docs/Improvement/1_app_improvement.md` — no Auth0 resilience |
| **Unit of Work** | Second resource added (Orders / Users) | Multi-resource transaction safety |
| **CQRS** | Only if read/write profiling demands it | Not currently tracked |

---

## Notes

- **Service Layer** and **Repository Pattern** are complementary — do not skip Service Layer once business logic appears; putting it in routes or repositories creates the same coupling problem Repository Pattern was introduced to solve.
- **Background Tasks** vs **Task Queue**: FastAPI `BackgroundTasks` runs in the same process as the request. On Lambda, if the Lambda instance is recycled before the background task finishes, the task is lost. For critical work (order confirmation emails, financial audit logs), use AWS SQS or SNS instead.
- **Circuit Breaker** state is in-memory per Lambda instance. On Lambda, each instance has its own breaker — a widespread Auth0 outage would need to trip the breaker on every instance independently. For shared circuit state, use Redis or AWS Parameter Store to store breaker status.
