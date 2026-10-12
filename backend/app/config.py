from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    env: str = "dev"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expiry_days: int = 7
    db_path: str = "data/kanakku.db"
    upload_dir: str = "data/uploads"
    backup_dir: str = "data/backups"

    ollama_url: str = "http://localhost:11434"
    llm_text_model: str = "qwen2.5:7b"
    llm_vision_model: str = "qwen2.5vl:7b"
    embed_model: str = "nomic-embed-text"
    rerank_model: str = "BAAI/bge-reranker-base"
    llm_timeout_s: float = 180.0

    worker_enabled: bool = True
    frontend_dist: str = str(Path(__file__).resolve().parents[2] / "frontend" / "dist")

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        """Relative paths are relative to the repo root, whatever the working directory."""
        if self.db_path != ":memory:" and not Path(self.db_path).is_absolute():
            self.db_path = str(ROOT / self.db_path)
        self.upload_dir = str(ROOT / self.upload_dir)
        self.backup_dir = str(ROOT / self.backup_dir)
        return self

    @model_validator(mode="after")
    def _check_secret(self) -> "Settings":
        if self.is_prod and (self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32):
            raise ValueError("JWT_SECRET must be set to a random string (>= 32 chars) in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
