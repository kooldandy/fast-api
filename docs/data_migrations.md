# Data Migrations Guide

Alembic manages both schema changes (DDL) and data fixes (DML). This guide covers when and how to use each approach, with patterns specific to this project.

---

## Schema Migration vs Data Migration

| Type | SQL | Example | Alembic? |
|---|---|---|---|
| **Schema migration** | DDL — `ALTER`, `CREATE`, `DROP` | Add a column, change a type | Always |
| **Data migration** | DML — `UPDATE`, `INSERT`, `DELETE` | Fix bad values, backfill a column | Usually |
| **One-off prod fix** | DML | Fix a single corrupted record | Standalone script |

---

## Decision Tree

```
Is this fix needed in ALL environments (dev, staging, prod)?
  │
  ├── YES → Alembic revision
  │           │
  │           ├── Small dataset (<10k rows)?
  │           │     └── op.execute() with raw SQL
  │           │
  │           ├── Needs Python logic (loops, conditionals)?
  │           │     └── op.get_bind() + Session
  │           │
  │           └── Large dataset (>10k rows)?
  │                 └── Batch loop inside revision
  │
  └── NO → Standalone script in scripts/
              │
              ├── Can it be reversed?
              │     ├── YES → document the reverse command
              │     └── NO  → take a DB snapshot first
              │
              └── Run manually — do NOT put in Alembic chain
```

---

## Pattern 1 — Simple SQL Fix (Small Dataset)

Use `op.execute()` with raw SQL. Fastest approach for straightforward fixes.

```python
# alembic/versions/c2d4f6a83e1c_fix_negative_prices.py
"""fix negative prices

Revision ID: c2d4f6a83e1c
Revises: a1c3e5f82d4b
Create Date: 2026-07-01
"""
from alembic import op

revision = "c2d4f6a83e1c"
down_revision = "a1c3e5f82d4b"


def upgrade() -> None:
    # Validate before
    conn = op.get_bind()
    count = conn.execute("SELECT COUNT(*) FROM product WHERE price <= 0").scalar()
    print(f"[data-fix] Found {count} products with invalid price")

    op.execute("""
        UPDATE product
        SET price = 0.01
        WHERE price <= 0
    """)

    print("[data-fix] Fix applied")


def downgrade() -> None:
    # Original values are lost — downgrade is not possible
    # Restore from DB snapshot if rollback is needed
    pass
```

**Key points:**
- Always add a `SELECT COUNT(*)` validation before the fix — confirms the problem exists
- `downgrade()` is usually `pass` for data fixes — original values are gone
- Add a print statement so migration logs show what happened

---

## Pattern 2 — Python Logic Fix

When the fix requires Python business logic, string manipulation, or conditional branching.

```python
# alembic/versions/d3e5f7b94c2d_normalize_product_names.py
"""normalize product names to title case

Revision ID: d3e5f7b94c2d
Revises: c2d4f6a83e1c
Create Date: 2026-07-01
"""
from alembic import op
from sqlalchemy.orm import Session

revision = "d3e5f7b94c2d"
down_revision = "c2d4f6a83e1c"


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    rows = session.execute(
        "SELECT id, name FROM product WHERE name != initcap(name)"
    ).fetchall()

    print(f"[data-fix] Normalizing {len(rows)} product names")

    for row in rows:
        session.execute(
            "UPDATE product SET name = :name WHERE id = :id",
            {"name": row.name.strip().title(), "id": row.id},
        )

    session.commit()
    print("[data-fix] Done")


def downgrade() -> None:
    pass  # cannot recover original casing
```

---

## Pattern 3 — Large Dataset (Batched)

Never update millions of rows in a single transaction — it locks the table and blocks the running API. Use a batch loop instead.

```python
# alembic/versions/e4f6a8c05d3e_backfill_discount_price.py
"""backfill discount_price column from price

Revision ID: e4f6a8c05d3e
Revises: d3e5f7b94c2d
Create Date: 2026-07-01
"""
from alembic import op

revision = "e4f6a8c05d3e"
down_revision = "d3e5f7b94c2d"

BATCH_SIZE = 500


def upgrade() -> None:
    bind = op.get_bind()
    total = 0

    while True:
        result = bind.execute(f"""
            UPDATE product
            SET discount_price = ROUND(price * 0.9, 2)
            WHERE discount_price IS NULL
            AND id IN (
                SELECT id FROM product
                WHERE discount_price IS NULL
                LIMIT {BATCH_SIZE}
            )
        """)
        total += result.rowcount
        if result.rowcount == 0:
            break

    print(f"[data-fix] Backfilled {total} rows in batches of {BATCH_SIZE}")


def downgrade() -> None:
    op.execute("UPDATE product SET discount_price = NULL")
```

**Why batch?**
- Single `UPDATE` on 500k rows holds a table lock for seconds — all reads/writes queue behind it
- Batching releases the lock between commits — app stays responsive
- Safe to re-run if it fails midway (idempotent `WHERE discount_price IS NULL`)

---

## Pattern 4 — Zero-Downtime (Expand-Contract)

For renaming columns or restructuring data while the API is live. Requires coordinated deploys across three phases.

```
Phase 1 → Migration: add new column, backfill existing rows
Phase 2 → App code: write to both old and new columns simultaneously
Phase 3 → Migration: make new column NOT NULL, drop old column
```

### Example: rename `price` → `unit_price`

```python
# Migration 1 — Expand: add new column and backfill
def upgrade() -> None:
    op.add_column("product", sa.Column("unit_price", sa.Numeric(10, 2), nullable=True))
    op.execute("UPDATE product SET unit_price = price")


# --- Deploy app code that writes to BOTH price AND unit_price ---
# --- Wait for all instances to roll out before running Migration 2 ---


# Migration 2 — Contract: lock in new column, remove old
def upgrade() -> None:
    # Validate backfill is complete
    bind = op.get_bind()
    nulls = bind.execute("SELECT COUNT(*) FROM product WHERE unit_price IS NULL").scalar()
    if nulls > 0:
        raise Exception(f"[data-fix] {nulls} rows still have NULL unit_price — backfill incomplete")

    op.alter_column("product", "unit_price", nullable=False)
    op.drop_column("product", "price")
```

---

## Pattern 5 — Standalone Script (One-Off Prod Fix)

When the fix only applies once, in one environment, and does not belong in the Alembic chain.

```python
# scripts/fix_orphaned_products.py
"""
One-off fix: set quantity=0 for products where quantity is NULL
Run: python scripts/fix_orphaned_products.py
"""
from app.database.db import session
from app.database.schema.product import Product


def run() -> None:
    db = session()
    try:
        orphans = db.query(Product).filter(Product.quantity == None).all()
        print(f"Found {len(orphans)} products with NULL quantity")

        if not orphans:
            print("Nothing to fix")
            return

        for p in orphans:
            p.quantity = 0

        db.commit()
        print(f"Fixed {len(orphans)} products")
    except Exception as e:
        db.rollback()
        print(f"Failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
```

**When to use standalone scripts:**
- Fix only needed in production (not dev/staging)
- Fix is exploratory — you're not sure of the scope yet
- Fix involves calling external APIs or services
- Fix is too risky to chain into the automated migration pipeline

---

## Rules Before Running Any Data Fix

### 1. Snapshot the database first
```bash
# RDS snapshot via AWS CLI
aws rds create-db-snapshot \
  --db-instance-identifier your-db \
  --db-snapshot-identifier pre-fix-snapshot-$(date +%Y%m%d)
```

### 2. Run on staging first
```bash
# Run migration on staging, confirm row counts
alembic upgrade head  # staging

# Check: how many rows affected?
# Does the app still work after?
# Did the migration complete in acceptable time?
```

### 3. Validate before and after
```sql
-- before: count rows that need fixing
SELECT COUNT(*) FROM product WHERE price <= 0;

-- after: confirm fix was applied
SELECT COUNT(*) FROM product WHERE price <= 0;  -- should be 0
```

### 4. Test rollback
```bash
alembic downgrade -1   # confirm downgrade doesn't crash
alembic upgrade head   # bring back up
```

---

## Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Single `UPDATE` on large table | Table lock — API goes down | Use batch loop |
| No snapshot before prod fix | Cannot recover if fix corrupts data | Always snapshot first |
| Mixing schema + data change in same revision | Cannot roll back schema without undoing data fix | Split into two revisions |
| `downgrade()` left as `pass` without comment | Future engineer doesn't know if it was intentional | Add comment: `# data loss — restore from snapshot` |
| Running fix on prod without staging test | Unknown runtime on real data volume | Always test on staging-scale data |
| Using `session.query(Model)` in migrations | ORM models evolve — migration breaks if model changes | Use raw SQL in migrations, not ORM models |

---

## This Project's Migration History

| Revision | Type | Description |
|---|---|---|
| `b379622f227c` | Schema | Initial — creates `product` table |
| `a1c3e5f82d4b` | Schema | Alters `price` from `FLOAT` → `NUMERIC(10,2)` |

> Next data migration should chain off `a1c3e5f82d4b` as `down_revision`.

---

## Running Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply one migration at a time
alembic upgrade +1

# Roll back one migration
alembic downgrade -1

# Check current state
alembic current

# View migration history
alembic history --verbose

# Run standalone script
python scripts/fix_orphaned_products.py
```

> **Reminder:** Migrations run in CI/CD before Lambda deployment — never inside the app startup. See `docs/Architecture.md` ADR-003.
