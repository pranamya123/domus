"""
Domus Backend - FastAPI Application

Main entry point for the Domus backend API.
"""

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from shared.schemas.events import (
    ScreenType,
    create_ui_screen_event,
)

from .core.config import settings
from .core.auth import decode_token
from .storage.memory_store import MemoryDomusStorage
from .api.routes import router, set_storage
from .api.websocket import WebSocketManager, ws_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global storage and websocket manager
storage: MemoryDomusStorage = None
websocket_manager: WebSocketManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global storage, websocket_manager

    # Startup
    logger.info("Starting Domus backend...")

    # Use in-memory storage for Phase 1 (no Redis required)
    storage = MemoryDomusStorage()
    await storage.connect()
    logger.info("Using in-memory storage (Phase 1)")

    # Set storage for routes
    set_storage(storage)

    # Initialize WebSocket manager
    websocket_manager = WebSocketManager(storage)

    logger.info("Domus backend started")

    yield

    # Shutdown
    logger.info("Shutting down Domus backend...")
    await storage.close()
    logger.info("Domus backend stopped")


# Create FastAPI app
app = FastAPI(
    title="Domus API",
    description="Smart home intelligence backend",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes
app.include_router(router, prefix="/api")


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time event streaming.

    Connect with: ws://host/ws?token=<jwt_token>
    """
    # Validate token
    token_data = decode_token(token)
    if not token_data:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Get session
    session = await storage.state.get_session(UUID(token_data.session_id))
    if not session:
        await websocket.close(code=4002, reason="Session not found")
        return

    # Connect
    await websocket_manager.connect(websocket, session)

    # Send initial screen event
    initial_screen = create_ui_screen_event(ScreenType.CHAT)
    await websocket_manager.send_event(session.user_id, initial_screen)

    try:
        # Message loop
        while True:
            message = await websocket.receive_text()
            await websocket_manager.handle_message(websocket, session, message)

    except WebSocketDisconnect:
        await websocket_manager.disconnect(session.user_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket_manager.disconnect(session.user_id)


# ============================================================================
# Root endpoint
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Domus API",
        "version": "1.0.0",
        "status": "running"
    }


# ============================================================================
# Run directly
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
