"""
Domus FastAPI Application Entry Point.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.database import init_db
from app.core.event_bus import event_bus
from app.core.event_handlers import register_handlers
from app.api.routes import chat, upload, iot, notifications, auth, health, alerts, blink, fridge

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if get_settings().debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()

    # Create required directories
    settings.image_storage_path.mkdir(parents=True, exist_ok=True)
    settings.notification_log_path.parent.mkdir(parents=True, exist_ok=True)
    settings.alexa_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Register event handlers
    register_handlers(event_bus)
    logger.info("Event handlers registered")

    # Start event bus
    await event_bus.start()
    logger.info("Event bus started")

    logger.info(f"Domus v0.1.0 started in {settings.app_env} mode")

    yield

    # Cleanup
    await event_bus.stop()
    logger.info("Domus shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Domus API",
    description="Hierarchical Multi-Agent Smart Home System",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://192.168.1.64:5173",  # Local network access
        "*"  # Allow all for development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(iot.router, prefix="/api/ingest", tags=["IoT"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(blink.router, prefix="/api/blink", tags=["Blink Camera"])
app.include_router(fridge.router, prefix="/api/fridge", tags=["Fridge"])

# Serve stored images statically
settings = get_settings()
settings.image_storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(settings.image_storage_path)), name="images")


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
