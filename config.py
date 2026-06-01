from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    project_name: str
    database_url: str
    supabase_url: str
    supabase_key: str
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    wati_api_endpoint: str | None = None
    wati_api_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
