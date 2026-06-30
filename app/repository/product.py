import json
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.schema.product import Product
from app.models.product import ProductCreate, ProductUpdate
from app.utils.redis_client import get_redis

CACHE_TTL = 60  # seconds


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, limit: int = 20, offset: int = 0) -> list[Any]:
        cache_key = f"products:limit={limit}:offset={offset}"
        redis = get_redis()

        cached = redis.get(cache_key)
        if cached:
            return self._deserialize(cached)

        products = self.db.query(Product).offset(offset).limit(limit).all()
        redis.setex(cache_key, CACHE_TTL, self._serialize(products))
        return products

    def get_by_id(self, id: int) -> Product:
        product = self.db.query(Product).filter(Product.id == id).first()
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return product

    def create(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        self._invalidate_cache()
        return product

    def update(self, id: int, data: ProductUpdate) -> Product:
        product = self.get_by_id(id)
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one product field is required",
            )

        for field, value in update_data.items():
            setattr(product, field, value)

        self.db.commit()
        self.db.refresh(product)
        self._invalidate_cache()
        return product

    def delete(self, id: int) -> None:
        product = self.get_by_id(id)
        self.db.delete(product)
        self.db.commit()
        self._invalidate_cache()

    # --- cache helpers ---

    def _serialize(self, products: list[Product]) -> str:
        return json.dumps([
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": str(p.price),   # Decimal → str for JSON
                "quantity": p.quantity,
            }
            for p in products
        ])

    def _deserialize(self, data: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = json.loads(data)
        for item in items:
            item["price"] = Decimal(item["price"])  # str → Decimal
        return items

    def _invalidate_cache(self) -> None:
        redis = get_redis()
        keys = redis.keys("products:*")
        if keys:
            redis.delete(*keys)
