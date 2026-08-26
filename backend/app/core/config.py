from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PEAK Smart Backend"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/food_expiry"
    storage_backend: str = "local"
    local_storage_path: str = "./data/uploads"
    max_image_size_bytes: int = 10 * 1024 * 1024
    vlm_provider: str = "mock"
    vlm_model: str | None = None
    vlm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VLM_API_KEY", "OPENAI_API_KEY"),
    )
    minimax_api_key: str | None = None
    minimax_video_base_url: str = "https://api.minimax.io"
    minimax_video_model: str = "MiniMax-H3"
    vlm_base_url: str | None = None
    expiring_soon_days: int = 3
    foodsafety_api_key: str | None = None
    foodsafety_recipe_count: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
