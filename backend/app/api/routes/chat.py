"""
Chat endpoints for conversational interface.

All conversation is owned by the Domus Orchestrator (L0).
Supports both authenticated and anonymous users.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.domus_orchestrator import orchestrator
from app.core.database import get_db
from app.core.security import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()

# Default anonymous household for users who aren't signed in
ANONYMOUS_USER_ID = "anonymous"
ANONYMOUS_HOUSEHOLD_ID = "anonymous_household"


class ChatMessage(BaseModel):
    """Chat message request."""
    message: str


class ChatResponse(BaseModel):
    """Chat response from Domus."""
    response: str
    status: str = "success"
    inventory_count: Optional[int] = None
    debug_state: Optional[dict] = None  # TODO: Remove this - debugging only


class ConversationMessage(BaseModel):
    """Single message in conversation history."""
    role: str
    content: str
    timestamp: str


class ConversationHistory(BaseModel):
    """Conversation history response."""
    messages: List[ConversationMessage]


@router.post("/message", response_model=ChatResponse)
async def send_message(
    chat: ChatMessage,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a chat message to Domus.

    Works for both authenticated and anonymous users.
    The Orchestrator owns all conversation output.
    """
    user_id = ANONYMOUS_USER_ID
    household_id = ANONYMOUS_HOUSEHOLD_ID

    # Check if user is authenticated
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)

        if token_data:
            from app.models.household import HouseholdMember

            user_id = token_data.user_id

            # Get user's household
            membership_result = await db.execute(
                select(HouseholdMember).where(HouseholdMember.user_id == user_id)
            )
            membership = membership_result.scalar_one_or_none()

            if membership:
                household_id = membership.household_id

    # Process through orchestrator
    result = await orchestrator.process({
        "action": "chat",
        "message": chat.message,
        "user_id": user_id,
        "household_id": household_id,
    })

    # Handle None result
    if result is None:
        result = {}

    # TODO: Remove this debug code later
    # Get current fridge state for debugging
    try:
        fridge_state = await orchestrator.process({
            "action": "get_inventory",
            "household_id": household_id,
        })
    except Exception:
        fridge_state = None

    return ChatResponse(
        response=result.get("response", "I'm sorry, I couldn't process that request."),
        status=result.get("status", "success"),
        inventory_count=result.get("inventory_count"),
        debug_state=fridge_state,  # TODO: Remove - debugging only
    )


@router.get("/history", response_model=ConversationHistory)
async def get_conversation_history(
    authorization: Optional[str] = Header(None),
    limit: int = 50,
):
    """Get conversation history for the current user."""
    user_id = ANONYMOUS_USER_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            user_id = token_data.user_id

    history = orchestrator._conversation_history.get(user_id, [])

    messages = [
        ConversationMessage(
            role=msg["role"],
            content=msg["content"],
            timestamp=msg["timestamp"],
        )
        for msg in history[-limit:]
    ]

    return ConversationHistory(messages=messages)


@router.delete("/history")
async def clear_conversation_history(
    authorization: Optional[str] = Header(None),
):
    """Clear conversation history for the current user."""
    user_id = ANONYMOUS_USER_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            user_id = token_data.user_id

    if user_id in orchestrator._conversation_history:
        orchestrator._conversation_history[user_id] = []

    return {"status": "cleared"}


# WebSocket for real-time chat
class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"WebSocket connected: {user_id}")

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"WebSocket disconnected: {user_id}")

    async def send_message(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)


manager = ConnectionManager()


@router.websocket("/ws/{token}")
async def websocket_chat(
    websocket: WebSocket,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for real-time chat.

    Token should be the JWT access token.
    """
    # Verify token
    token_data = verify_token(token)
    if not token_data:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = token_data.user_id

    # Get household
    from app.models.household import HouseholdMember

    membership_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.user_id == user_id)
    )
    membership = membership_result.scalar_one_or_none()

    if not membership:
        await websocket.close(code=4002, reason="No household")
        return

    await manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            # Process through orchestrator
            result = await orchestrator.process({
                "action": "chat",
                "message": message,
                "user_id": user_id,
                "household_id": membership.household_id,
            })

            # Send response
            await manager.send_message(user_id, {
                "type": "response",
                "response": result.get("response"),
                "status": result.get("status"),
            })

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(user_id)
