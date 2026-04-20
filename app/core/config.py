"""
app/core/config.py
Configuración centralizada desde variables de entorno.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────
    APP_NAME: str = "Jardín y Vivero Los Naranjos"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # ── Base de datos ──────────────────────────────────
    DATABASE_URL: str

    # ── JWT / Auth ─────────────────────────────────────
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # ── 2FA ────────────────────────────────────────────
    TOTP_ISSUER: str = "Vivero Los Naranjos"

    # ── CORS ───────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:8000"

    @property
    def origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # ── Rate limiting ──────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 10

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — se lee solo una vez."""
    return Settings()


settings = get_settings()
