from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.auth import get_current_user
from app.database.db import get_db
from app.models.product import ProductCreate, ProductResponse, ProductUpdate
from app.repository.product import ProductRepository
from app.utils.limiter import limiter

router = APIRouter(prefix="/api/v1/product", tags=["products"])


def get_product_repo(db: Session = Depends(get_db)) -> ProductRepository:
    return ProductRepository(db)


@router.get("", response_model=list[ProductResponse], dependencies=[Depends(get_current_user)])
@limiter.limit("60/minute")  # type: ignore[misc]
def get_all_products(
    request: Request,  # required by slowapi for rate-limit key extraction
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repo: ProductRepository = Depends(get_product_repo),
):
    return repo.get_all(limit=limit, offset=offset)


@router.get("/{id}", response_model=ProductResponse, dependencies=[Depends(get_current_user)])
@limiter.limit("60/minute")  # type: ignore[misc]
def get_product_by_id(
    request: Request,  # required by slowapi for rate-limit key extraction
    id: int,
    repo: ProductRepository = Depends(get_product_repo),
):
    return repo.get_by_id(id)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_current_user)])
@limiter.limit("20/minute")  # type: ignore[misc]
def add_product(
    request: Request,  # required by slowapi for rate-limit key extraction
    product: ProductCreate,
    repo: ProductRepository = Depends(get_product_repo),
):
    return repo.create(product)


@router.patch("/{id}", response_model=ProductResponse, dependencies=[Depends(get_current_user)])
@limiter.limit("20/minute")  # type: ignore[misc]
def update_product(
    request: Request,  # required by slowapi for rate-limit key extraction
    id: int,
    product: ProductUpdate,
    repo: ProductRepository = Depends(get_product_repo),
):
    return repo.update(id, product)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_current_user)])
@limiter.limit("10/minute")  # type: ignore[misc]
def delete_product(
    request: Request,  # required by slowapi for rate-limit key extraction
    id: int,
    repo: ProductRepository = Depends(get_product_repo),
):
    repo.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
