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
    meta_whatsapp_token: str | None = None
    meta_whatsapp_phone_number_id: str | None = None
    waba_id: str | None = None
    rate_limit_enabled: bool = True
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800


@lru_cache
def get_settings() -> Settings:
    return Settings()
