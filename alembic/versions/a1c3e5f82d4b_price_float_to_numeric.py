"""price float to numeric

Revision ID: a1c3e5f82d4b
Revises: b379622f227c
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1c3e5f82d4b"
down_revision: Union[str, None] = "b379622f227c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "product",
        "price",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=10, scale=2),
        existing_nullable=False,
        postgresql_using="price::numeric(10,2)",
    )


def downgrade() -> None:
    op.alter_column(
        "product",
        "price",
        existing_type=sa.Numeric(precision=10, scale=2),
        type_=sa.Float(),
        existing_nullable=False,
    )
