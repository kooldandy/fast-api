from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class AppConfig(BaseSettings):
    app_name: str = "FastAPI"
    app_env: str = "development"
    database_url: str
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_app_config():
    return AppConfig() # type: ignore
