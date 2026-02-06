"""
Domus Configuration

Application settings with environment variable support.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DOMUS_",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_name: str = "Domus"
    debug: bool = True

    # Demo mode - bypasses authentication for all API calls
    # Set DOMUS_DEMO_MODE=true in environment or .env
    demo_mode: bool = True

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
    gemini_model: str = "gemini-3-flash-preview"
    gemini_vision_model: str = "gemini-3-flash-preview"  # Multimodal model for fridge analysis

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "https://sane-highhanded-regenia.ngrok-free.dev",

        "capacitor://localhost",
        "ionic://localhost",
    ]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
