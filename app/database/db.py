import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config.app_config import get_app_config

config = get_app_config()

IS_AWS = bool(os.getenv("AWS_EXECUTION_ENV") or os.getenv("LAMBDA_TASK_ROOT"))

db_url = f"postgresql://{config.db_id}:{config.db_password}@{config.db_host}:{config.db_port}/{config.db_name}"

# Lambda has no persistent process — NullPool avoids exhausting PostgreSQL connections
# under concurrent cold starts. Local dev uses the default pool for performance.
engine = create_engine(db_url, echo=False, poolclass=NullPool if IS_AWS else None)
session = sessionmaker(autoflush=False, autocommit=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = session()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
