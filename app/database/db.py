from sqlalchemy.orm import  sessionmaker, Session
from sqlalchemy import create_engine
from app.config.app_config import get_app_config
from typing import Generator

config = get_app_config()

engine = create_engine(config.database_url)
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
