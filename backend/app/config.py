"""Application settings. Secrets come from environment variables only (spec 8.15)."""
import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR / 'storage' / 'app.db'}"
    jwt_secret: str = ""                    # REQUIRED in production; see .env.example
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    reset_token_minutes: int = 30
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    storage_dir: str = str(BASE_DIR / "storage")
    max_upload_mb: int = 10
    max_dataset_mb: int = 300
    # first administrator, created on startup if no admin exists
    admin_email: str = ""
    admin_password: str = ""
    # SMTP is optional; without it reset links are written to the server log
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@fakenews.local"
    frontend_url: str = "http://localhost:5173"
    # demo convenience ONLY: return the reset token in the API response
    expose_reset_token: bool = False


settings = Settings()

if not settings.jwt_secret:
    # Never hard-code a secret: fall back to a random per-process one and warn.
    settings.jwt_secret = secrets.token_urlsafe(48)
    logging.getLogger("app").warning(
        "JWT_SECRET not set - using a random secret; all tokens are invalidated on restart.")

Path(settings.storage_dir, "models").mkdir(parents=True, exist_ok=True)
Path(settings.storage_dir, "avatars").mkdir(parents=True, exist_ok=True)
