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

    # --- Vector database (Qdrant) ---
    # QDRANT_URL set  -> talk to a Qdrant server (e.g. Docker).
    # QDRANT_URL empty -> embedded mode, data stored in QDRANT_PATH (no server needed).
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_path: Path = BASE_DIR / "qdrant_data"
    qdrant_collection: str = "grabpic_faces"

    # --- Face recognition (InsightFace, runs fully locally) ---
    face_model_name: str = "buffalo_l"          # SCRFD detector + ArcFace R50, 512-d
    face_model_root: str = "~/.insightface"     # where model files are downloaded
    face_use_gpu: bool = True                   # falls back to CPU automatically
    face_det_size: int = 960                    # detector input size (multiple of 32)
    face_min_det_score: float = 0.6             # ignore low-confidence detections
    face_min_size_px: int = 40                  # ignore tiny background faces
    face_match_threshold: float = 0.40          # cosine similarity needed to call it a match
    face_search_limit: int = 500                # max matching faces fetched per search
    show_match_scores: bool = True              # show similarity on the results page (dev aid)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()