from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    admin_password: str
    database_url: str = "sqlite:///./fridge.db"
    media_dir: str = "./media"
    food_safety_api_key: str = ""
    kang_backend_url: str = "https://antonym-tighten-backdrop.ngrok-free.dev"
    kang_fridge_device_id: str = "home-fridge-01"

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    @property
    def media_path(self) -> Path:
        path = (BACKEND_DIR / self.media_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
