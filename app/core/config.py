from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """All configuration comes from environment variables / the .env file."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required: the app refuses to start without it. No default on purpose.
    database_url: str

    sql_echo: bool = False
    upload_dir: Path = BASE_DIR / "static" / "uploads"
    max_upload_size_mb: int = 10

    # Stand-in for the logged-in user until authentication exists.
    default_user_email: str = "demo@example.com"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
