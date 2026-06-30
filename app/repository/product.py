from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.schema.product import Product
from app.models.product import ProductCreate, ProductUpdate


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, limit: int = 20, offset: int = 0) -> list[Product]:
        return self.db.query(Product).offset(offset).limit(limit).all()

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
        return product

    def delete(self, id: int) -> None:
        product = self.get_by_id(id)
        self.db.delete(product)
        self.db.commit()
