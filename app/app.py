import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config.app_config import get_app_config
from app.routing import product

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
config = get_app_config()

app = FastAPI(title=config.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#include all router
app.include_router(product.router)


@app.exception_handler(SQLAlchemyError)
def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error while handling %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Database error"},
    )


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}

# products = [
#     Product(id=1, name='Laptop', description='Gaming laptop', price=99.9, quantity=6),
#     Product(id=2, name='Laptop', description='working laptop', price=999.9, quantity=10),
# ]

# def init_db():
#     db = session()
#     count = db.query(db_model.Product).count
#     if count == 0:
#         for product in products:
#             db.add(db_model.Product(**product.model_dump()));
    
#         db.commit();


# init_db();
