from alembic.environment import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class AppConfig(BaseSettings):
    db_id: str
    db_password: str
    db_host: str
    db_port: str
    db_name: str

    app_name: str = "FastAPI"
    app_env: str = "development"

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_app_config():
    return AppConfig() # type: ignore
