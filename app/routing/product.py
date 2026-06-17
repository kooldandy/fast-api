from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session 
from app.auth.auth import get_current_user
from app.database.db import get_db
from app.database.schema.product import Product as ProductSchema
from app.models.product import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/api/v1/product", tags=["products"])


def get_product_or_404(id: int, db: Session) -> ProductSchema:
    product = db.query(ProductSchema).filter(ProductSchema.id == id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get("", response_model=list[ProductResponse], dependencies=[Depends(get_current_user)])
def get_all_product(db: Session = Depends(get_db)):
    return db.query(ProductSchema).all()


@router.get("/{id}", response_model=ProductResponse)
def get_product_by_id(id: int, db: Session = Depends(get_db)):
    return get_product_or_404(id, db)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def add_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = ProductSchema(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.patch("/{id}", response_model=ProductResponse)
def update_product(id: int, product: ProductUpdate, db: Session = Depends(get_db)):
    db_product = get_product_or_404(id, db)
    update_data = product.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one product field is required",
        )

    for field, value in update_data.items():
        setattr(db_product, field, value)

    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(id: int, db: Session = Depends(get_db)):
    db_product = get_product_or_404(id, db)
    db.delete(db_product)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
