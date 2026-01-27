"""
Application configuration using Pydantic Settings.
All timestamps use UTC. Server time is authoritative.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Domus"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "sqlite+aiosqlite:///./domus.db"

    # Google OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/callback"

    # Gemini API
    gemini_api_key: Optional[str] = None

    # Redis (optional)
    redis_url: Optional[str] = None

    # IoT Device Token
    iot_device_token: str = "mock-iot-device-token"

    # Data Storage
    data_path: Path = Path("./storage/data")

    # Image Storage
    image_storage_path: Path = Path("./storage/images")
    image_retention_days: int = 30

    # Notification Settings
    notification_log_path: Path = Path("./logs/notifications.log")
    alexa_log_path: Path = Path("./logs/alexa.log")

    # Debounce Settings (in seconds)
    iot_image_debounce_seconds: int = 900  # 15 minutes
    expiry_notification_throttle_seconds: int = 86400  # 24 hours

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Rolling buffer settings
    max_image_buffer_size: int = 3

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def has_gemini_key(self) -> bool:
        return self.gemini_api_key is not None and len(self.gemini_api_key) > 0


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
