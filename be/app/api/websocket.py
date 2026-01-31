"""
WebSocket Handler

Real-time event delivery to frontend clients.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from shared.schemas.events import (
    DomusEvent,
    EventType,
    AgentType,
    AgentStatus,
    ScreenType,
    create_ui_screen_event,
    create_agent_status_event,
    create_heartbeat_event,
)
from shared.schemas.state import UserSession

from ..core.config import settings
from ..storage.redis_store import RedisDomusStorage
from ..agents import get_orchestrator
from ..agents.base import AgentType as AgentTypeEnum, AgentStatus as AgentStatusEnum

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting."""

    def __init__(self, storage: RedisDomusStorage):
        self._storage = storage
        self._connections: dict[str, WebSocket] = {}  # user_id -> websocket
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}

    async def connect(
        self,
        websocket: WebSocket,
        session: UserSession
    ) -> None:
        """
        Accept WebSocket connection and start event streaming.
        """
        await websocket.accept()
        user_id = session.user_id

        # Store connection
        self._connections[user_id] = websocket
        logger.info(f"WebSocket connected: user={user_id}")

        # Start heartbeat task
        self._heartbeat_tasks[user_id] = asyncio.create_task(
            self._heartbeat_loop(user_id)
        )

        # Start event subscription task
        asyncio.create_task(self._event_subscription_loop(user_id, websocket))

    async def disconnect(self, user_id: str) -> None:
        """Clean up on disconnect."""
        # Cancel heartbeat
        if user_id in self._heartbeat_tasks:
            self._heartbeat_tasks[user_id].cancel()
            del self._heartbeat_tasks[user_id]

        # Remove connection
        if user_id in self._connections:
            del self._connections[user_id]

        logger.info(f"WebSocket disconnected: user={user_id}")

    async def send_event(self, user_id: str, event: DomusEvent) -> bool:
        """
        Send event to specific user.

        Returns True if sent successfully.
        """
        websocket = self._connections.get(user_id)
        if not websocket:
            return False

        try:
            # Serialize with proper JSON encoding
            event_json = event.model_dump_json()
            await websocket.send_text(event_json)
            return True
        except Exception as e:
            logger.error(f"Error sending event to {user_id}: {e}")
            await self.disconnect(user_id)
            return False

    async def broadcast_to_user(self, user_id: str, event: DomusEvent) -> None:
        """
        Send event to user via WebSocket only (to avoid duplicates).

        Note: Redis persistence disabled to prevent duplicate delivery
        via both direct send and pub/sub subscription.
        """
        # Send directly to connected WebSocket
        await self.send_event(user_id, event)

    async def handle_message(
        self,
        websocket: WebSocket,
        session: UserSession,
        message: str
    ) -> None:
        """
        Handle incoming WebSocket message from client.

        Phase 1: Simple chat messages that trigger agent activation flow.
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                await self._handle_chat_message(session, data.get("content", ""))
            elif msg_type == "ping":
                # Client ping, respond with pong
                await self.send_event(
                    session.user_id,
                    DomusEvent(type=EventType.HEARTBEAT, payload={"pong": True})
                )
            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message: {message[:100]}")

    async def _handle_chat_message(self, session: UserSession, content: str) -> None:
        """
        Handle chat message from user.

        Phase 2 flow with real LLM:
        1. User sends message
        2. Detect which agent should handle it
        3. Emit agent.status(activating) with agent name
        4. Process through orchestrator + LLM
        5. Emit agent.status(activated)
        6. Emit chat response
        """
        user_id = session.user_id

        # Get orchestrator
        orchestrator = get_orchestrator()

        # Detect which agent should handle this
        detected_agent = orchestrator.detect_agent(content)
        agent_name = detected_agent.value if detected_agent else "Domus"

        # Map our AgentType to the event schema AgentType
        event_agent = self._map_agent_type(detected_agent)

        # 1. Emit activating status
        activating_event = create_agent_status_event(
            agent=event_agent,
            status=AgentStatus.ACTIVATING,
            message=f"Activating {agent_name} agent..."
        )
        await self.broadcast_to_user(user_id, activating_event)

        # 2. Process through orchestrator (real LLM call)
        try:
            # Get chat history from state (if available)
            chat_history = []
            blink_connected = False
            try:
                state = await self._storage.state.get_domus_state(session.session_id)
                if state and state.chat_history:
                    chat_history = state.chat_history
                # Check if Blink is connected from latest state (or fallback to session)
                if state and state.session and state.session.capabilities:
                    blink_connected = state.session.capabilities.blink_connected
                else:
                    blink_connected = session.capabilities.blink_connected if session.capabilities else False
            except Exception:
                pass  # Continue without history if unavailable

            # Get inventory (only if Blink connected)
            inventory = self._get_mock_inventory(blink_connected)

            # Process message through orchestrator
            response, agent_type = await orchestrator.process_message(
                message=content,
                user_id=user_id,
                session_id=session.session_id,
                chat_history=chat_history,
                inventory=inventory
            )

            # 3. Emit activated status
            activated_event = create_agent_status_event(
                agent=event_agent,
                status=AgentStatus.ACTIVATED,
                message=f"{agent_name} agent ready"
            )
            await self.broadcast_to_user(user_id, activated_event)

            # 4. Send LLM response
            response_event = DomusEvent(
                type=EventType.CHAT_ASSISTANT_MESSAGE,
                payload={
                    "content": response.content,
                    "sender": "domus",
                    "agent": agent_name,
                    "metadata": response.metadata
                }
            )
            await self.broadcast_to_user(user_id, response_event)

        except Exception as e:
            logger.error(f"Error processing message: {e}")

            # Send error response
            error_event = create_agent_status_event(
                agent=event_agent,
                status=AgentStatus.ERROR,
                message="Error processing request"
            )
            await self.broadcast_to_user(user_id, error_event)

            response_event = DomusEvent(
                type=EventType.CHAT_ASSISTANT_MESSAGE,
                payload={
                    "content": "I apologize, but I encountered an error processing your request. Please try again.",
                    "sender": "domus",
                    "error": True
                }
            )
            await self.broadcast_to_user(user_id, response_event)

    def _map_agent_type(self, agent_type: Optional[AgentTypeEnum]) -> AgentType:
        """Map internal agent type to event schema agent type"""
        if agent_type is None:
            return AgentType.FRIDGE  # Default

        mapping = {
            AgentTypeEnum.FRIDGE: AgentType.FRIDGE,
            AgentTypeEnum.CALENDAR: AgentType.CALENDAR,
            AgentTypeEnum.SERVICES: AgentType.SERVICES,
            AgentTypeEnum.NOTIFICATION: AgentType.NOTIFICATION,
        }
        return mapping.get(agent_type, AgentType.FRIDGE)

    def _get_mock_inventory(self, blink_connected: bool = False) -> dict | None:
        """Get inventory data - returns None if Blink not connected"""
        if not blink_connected:
            return None  # No inventory without Blink connection

        # Mock inventory for when Blink IS connected (for testing)
        return {
            "items": [
                {"name": "Apples", "quantity": 4, "unit": "pieces", "estimated_expiry": "5 days"},
                {"name": "Spinach", "quantity": 1, "unit": "bag", "estimated_expiry": "2 days"},
                {"name": "Carrots", "quantity": 1, "unit": "bunch", "estimated_expiry": "1 week"},
                {"name": "Bell peppers", "quantity": 2, "unit": "pieces", "estimated_expiry": "4 days"},
                {"name": "Milk", "quantity": 1, "unit": "gallon", "estimated_expiry": "5 days"},
                {"name": "Greek yogurt", "quantity": 2, "unit": "cups", "estimated_expiry": "1 week"},
                {"name": "Cheddar cheese", "quantity": 1, "unit": "block", "estimated_expiry": "2 weeks"},
                {"name": "Chicken breast", "quantity": 2, "unit": "lbs", "estimated_expiry": "3 days"},
                {"name": "Eggs", "quantity": 8, "unit": "pieces", "estimated_expiry": "2 weeks"},
                {"name": "Leftover pasta", "quantity": 1, "unit": "container", "estimated_expiry": "today"},
                {"name": "Orange juice", "quantity": 0.5, "unit": "gallon", "estimated_expiry": "1 week"},
            ]
        }

    async def _heartbeat_loop(self, user_id: str) -> None:
        """Send periodic heartbeat to keep connection alive."""
        while True:
            try:
                await asyncio.sleep(settings.ws_heartbeat_interval)
                heartbeat = create_heartbeat_event()
                await self.send_event(user_id, heartbeat)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error for {user_id}: {e}")
                break

    async def _event_subscription_loop(
        self,
        user_id: str,
        websocket: WebSocket
    ) -> None:
        """
        Subscribe to Redis pub/sub for events from other services.

        This ensures events published by backend services (not through
        this WebSocket connection) are still delivered to the client.
        """
        try:
            async for event in self._storage.events.subscribe(user_id):
                # Don't send duplicates - check if websocket still active
                if user_id not in self._connections:
                    break
                await websocket.send_text(event.model_dump_json())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Event subscription error for {user_id}: {e}")


# Global manager instance (initialized in main.py)
ws_manager: Optional[WebSocketManager] = None
