"""Application settings via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    environment: str = "development"
    database_url: str


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so the .env file and environment are only read once per process,
    and so FastAPI dependency injection can reuse the same instance via
    Depends(get_settings) without re-parsing on every request.
    """
    return Settings()  # type: ignore[call-arg]