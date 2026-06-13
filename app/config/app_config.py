from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class AppConfig(BaseSettings):
    database_id: str
    database_password: str
    database_host: str
    database_port: str
    database_name: str

    app_name: str = "FastAPI"
    app_env: str = "development"

    cors_origins: list[str]

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_app_config():
    return AppConfig() # type: ignore
