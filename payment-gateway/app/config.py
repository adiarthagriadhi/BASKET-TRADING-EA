from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./gateway.db"
    admin_token: str = "change-me"
    environment: str = "sandbox"  # sandbox | production
    public_base_url: str = "http://localhost:8000"
    payment_expiry_minutes: int = 60
    webhook_timeout_seconds: float = 10.0
    webhook_max_attempts: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
