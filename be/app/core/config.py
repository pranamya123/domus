"""
Domus Configuration

Application settings with environment variable support.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # App
    app_name: str = "Domus"
    debug: bool = True

    # Redis
    redis_url: str = "redis://localhost:6379"
    redis_password: Optional[str] = None

    # Auth (mock for Phase 1)
    jwt_secret: str = "domus-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Session
    session_ttl_seconds: int = 60 * 60 * 24  # 24 hours

    # WebSocket
    ws_heartbeat_interval: int = 30  # seconds

    # Gemini LLM
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    class Config:
        env_file = ".env"
        env_prefix = "DOMUS_"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
