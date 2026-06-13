from sqlalchemy.orm import  sessionmaker, Session
from sqlalchemy import create_engine
from app.config.app_config import get_app_config
from typing import Generator

config = get_app_config()

db_url = f"postgresql://{config.database_id}:{config.database_password}@{config.database_host}:{config.database_port}/{config.database_name}"
engine = create_engine(db_url, echo=False)
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
