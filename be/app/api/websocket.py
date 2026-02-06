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
from ..services.fridge_inventory_service import FridgeInventoryService
from ..services.blink_service import get_blink_service

logger = logging.getLogger(__name__)

# TODO: Change trigger to 2 days before the calendar event instead of 3 minutes after app open.
BAKE_SALE_NOTIFICATION_DELAY_SECONDS = 180  # 3 minutes after app open

# TODO: For demo only - triggers grocery store notification 7 minutes after app open.
# In production, this would be triggered by actual iOS geofence entry via POST /location/entered.
GROCERY_NOTIFICATION_DELAY_SECONDS = 30  # 30 seconds after app open (was 420 = 7 min)


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting."""

    def __init__(self, storage: RedisDomusStorage):
        self._storage = storage
        self._connections: dict[str, WebSocket] = {}  # user_id -> websocket
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}
        self._bake_sale_tasks: dict[str, asyncio.Task] = {}  # Track bake sale notification tasks
        self._bake_sale_notified: set[str] = set()  # Track users already notified (idempotency)
        self._grocery_tasks: dict[str, asyncio.Task] = {}  # Track grocery notification tasks
        self._grocery_notified: set[str] = set()  # Track users already notified (idempotency)

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

        # Send any pending unread notifications (for when user was backgrounded)
        await self._send_pending_notifications(user_id)

        # Schedule delayed bake sale notification check (3 minutes after connect)
        # TODO: Change trigger to 2 days before the calendar event instead of 3 minutes after app open.
        if user_id not in self._bake_sale_notified:
            self._bake_sale_tasks[user_id] = asyncio.create_task(
                self._delayed_bake_sale_check(user_id, session)
            )

        # Schedule delayed grocery store notification (30 seconds after connect for demo)
        # TODO: For demo only - simulates user entering a grocery store.
        # In production, this would be triggered by iOS geofence entry via POST /location/entered.
        if user_id not in self._grocery_notified:
            logger.info("Creating grocery notification task for user %s", user_id)
            self._grocery_tasks[user_id] = asyncio.create_task(
                self._delayed_grocery_check(user_id, session)
            )
            logger.info("Grocery notification task created for user %s", user_id)

    async def disconnect(self, user_id: str) -> None:
        """Clean up on disconnect."""
        # Cancel heartbeat
        if user_id in self._heartbeat_tasks:
            self._heartbeat_tasks[user_id].cancel()
            del self._heartbeat_tasks[user_id]

        # NOTE: Do NOT cancel bake sale task - it should still fire even if user backgrounds app
        # The notification will be delivered via push/local notification

        # Remove connection
        if user_id in self._connections:
            del self._connections[user_id]

        logger.info(f"WebSocket disconnected: user={user_id}")

    async def _send_pending_notifications(self, user_id: str) -> None:
        """
        Send any unread notifications to user on reconnect.

        This ensures notifications created while user was backgrounded
        are delivered when they return to the app.

        NOTE: Only sends ONE bake sale notification to avoid duplicates.
        """
        try:
            notifications = await self._storage.state.get_notifications(user_id, limit=10)
            unread = [n for n in notifications if n.read_at is None]

            if not unread:
                return

            # Filter: only send ONE bake sale notification (the most recent one)
            bake_sale_sent = False
            filtered_unread = []
            for n in unread:
                title_lower = n.title.lower() if n.title else ""
                is_bake_sale = "bake" in title_lower or "baking" in title_lower
                if is_bake_sale:
                    if not bake_sale_sent:
                        filtered_unread.append(n)
                        bake_sale_sent = True
                    # Skip additional bake sale notifications
                else:
                    filtered_unread.append(n)

            if not filtered_unread:
                return

            logger.info("Sending %d pending notifications to user %s", len(filtered_unread), user_id)

            for notification in filtered_unread:
                event = DomusEvent(
                    type=EventType.NOTIFICATION_CREATED,
                    payload={
                        "notification_id": str(notification.notification_id),
                        "title": notification.title,
                        "body": notification.body,
                        "notification_type": notification.notification_type,
                        "event_id": notification.event_id,
                    }
                )
                await self.send_event(user_id, event)

        except Exception as e:
            logger.error("Failed to send pending notifications: %s", e)

    async def _delayed_bake_sale_check(
        self,
        user_id: str,
        session: UserSession
    ) -> None:
        """
        Check for bake sale events after a delay and send notification if needed.

        This is the trigger for Feature 2: "Bake Sale Prep, Handled"
        Fires 3 minutes after app open (WebSocket connect).

        TODO: Change trigger to 2 days before the calendar event instead of 3 minutes after app open.
        """
        try:
            logger.info(
                "Bake sale timer started for user %s (delay=%ds)",
                user_id, BAKE_SALE_NOTIFICATION_DELAY_SECONDS
            )

            # Wait for configured delay
            await asyncio.sleep(BAKE_SALE_NOTIFICATION_DELAY_SECONDS)

            logger.info("Bake sale timer fired for user %s", user_id)

            # NOTE: Don't check if still connected - notification should be sent
            # even if app is backgrounded. Push/local notification will still work.

            # Check idempotency - only notify once per session
            if user_id in self._bake_sale_notified:
                logger.debug("User %s already notified about bake sale", user_id)
                return

            logger.info("Running bake sale check for user %s", user_id)

            # Import here to avoid circular imports
            from ..services.calendar_service import get_calendar_service
            from ..services.bake_sale_notification_service import BakeSaleNotificationService

            # Check for upcoming bake sale events
            calendar = get_calendar_service()
            prep_events = await calendar.get_prep_required_events(user_id, days_ahead=7)

            # Find bake sale type events
            bake_sale_event = None
            for event in prep_events:
                title_lower = event.get("title", "").lower()
                if "bake" in title_lower or event.get("prep_type") == "baking":
                    bake_sale_event = event
                    break

            if not bake_sale_event:
                logger.debug("No bake sale events found for user %s", user_id)
                return

            # Generate and send rich notification
            notification_service = BakeSaleNotificationService(self._storage)
            notification = await notification_service.create_bake_sale_notification(
                user_id=user_id,
                event=bake_sale_event
            )

            if notification:
                # Mark as notified (idempotency)
                self._bake_sale_notified.add(user_id)

                # Try to send WebSocket event for real-time UI update
                # If user is disconnected, notification is still saved to storage
                # and will be delivered when they reconnect via _send_pending_notifications
                if user_id in self._connections:
                    notification_event = DomusEvent(
                        type=EventType.NOTIFICATION_CREATED,
                        payload={
                            "notification_id": notification["notification_id"],
                            "title": notification["title"],
                            "body": notification["body"],
                            "notification_type": "proactive",
                            "event_id": bake_sale_event.get("id"),
                            "has_action_card": True,
                        }
                    )
                    await self.broadcast_to_user(user_id, notification_event)
                    logger.info(
                        "Bake sale in-app notification sent (realtime) for user %s",
                        user_id
                    )
                else:
                    logger.info(
                        "Bake sale notification saved for user %s (will deliver on reconnect)",
                        user_id
                    )

        except asyncio.CancelledError:
            logger.debug("Bake sale check cancelled for user %s", user_id)
        except Exception as e:
            logger.error("Bake sale check error for user %s: %s", user_id, e)

    async def _delayed_grocery_check(
        self,
        user_id: str,
        session: UserSession
    ) -> None:
        """
        Simulate grocery store geofence entry after a delay.

        TODO: For demo only - triggers 7 minutes after app open.
        In production, this would be triggered by actual iOS geofence entry
        via POST /location/entered when CLLocationManager detects didEnterRegion.
        """
        try:
            logger.info(
                "Grocery notification timer started for user %s (delay=%ds)",
                user_id, GROCERY_NOTIFICATION_DELAY_SECONDS
            )

            # Wait for configured delay
            await asyncio.sleep(GROCERY_NOTIFICATION_DELAY_SECONDS)

            logger.info("Grocery notification timer fired for user %s", user_id)

            # Check idempotency - only notify once per session
            if user_id in self._grocery_notified:
                logger.debug("User %s already notified about grocery", user_id)
                return

            # Import services
            from ..services.location_service import get_location_service, GeofenceEntry
            from ..services.grocery_notification_service import get_grocery_notification_service

            location_service = get_location_service()
            grocery_service = get_grocery_notification_service(self._storage)

            # Simulate entering the demo grocery store (Whole Foods)
            entry = GeofenceEntry(
                user_id=user_id,
                place_id="demo_grocery",
                timestamp=datetime.utcnow(),
            )

            store = location_service.validate_entry(entry)
            if not store:
                logger.debug("Demo grocery store not found")
                return

            # Generate notification
            notification = await grocery_service.handle_geofence_entry(entry, store)

            if notification:
                # Mark as notified (idempotency)
                self._grocery_notified.add(user_id)

                # Send WebSocket event for real-time UI update
                if user_id in self._connections:
                    notification_event = DomusEvent(
                        type=EventType.NOTIFICATION_CREATED,
                        payload={
                            "notification_id": notification["notification_id"],
                            "title": notification["title"],
                            "body": notification["body"],
                            "notification_type": "proactive",
                            "has_action_card": True,
                        }
                    )
                    await self.broadcast_to_user(user_id, notification_event)
                    logger.info(
                        "Grocery notification sent (realtime) for user %s: %s at %s",
                        user_id, notification["item"], notification["store"]
                    )
                else:
                    logger.info(
                        "Grocery notification saved for user %s (will deliver on reconnect)",
                        user_id
                    )

        except asyncio.CancelledError:
            logger.debug("Grocery check cancelled for user %s", user_id)
        except Exception as e:
            logger.error("Grocery check error for user %s: %s", user_id, e)

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

            # TODO: Re-enable Blink-based inventory refresh once Blink auth is fixed
            # For now, FridgeAgent reads thumbnail directly from storage/media/
            # and uses Gemini vision to analyze the image
            inventory = None
            is_inventory_query = self._is_inventory_query(content)
            logger.info(
                "Fridge query context (user_id=%s, is_inventory_query=%s) - using direct thumbnail read",
                user_id,
                is_inventory_query,
            )
            # Skip Blink service calls - FridgeAgent will handle thumbnail directly
            # service = FridgeInventoryService(self._storage)
            # blink_service = get_blink_service()
            # blink_service_connected = blink_service.is_connected(user_id)

            # Create status callback for multi-agent coordination
            async def status_callback(
                agent_type: AgentTypeEnum,
                status: AgentStatusEnum,
                message: str
            ) -> None:
                """Callback to emit agent status updates during coordination."""
                event_agent = self._map_agent_type(agent_type)
                # Map internal status to event schema status
                status_mapping = {
                    AgentStatusEnum.ACTIVATING: AgentStatus.ACTIVATING,
                    AgentStatusEnum.ACTIVE: AgentStatus.ACTIVATED,
                    AgentStatusEnum.PROCESSING: AgentStatus.PROCESSING,
                    AgentStatusEnum.COMPLETED: AgentStatus.COMPLETED,
                    AgentStatusEnum.ERROR: AgentStatus.ERROR,
                    AgentStatusEnum.IDLE: AgentStatus.DEACTIVATED,
                }
                event_status = status_mapping.get(status, AgentStatus.ACTIVATING)
                status_event = create_agent_status_event(
                    agent=event_agent,
                    status=event_status,
                    message=message
                )
                await self.broadcast_to_user(user_id, status_event)

            # Process message through orchestrator
            response, agent_type = await orchestrator.process_message(
                message=content,
                user_id=user_id,
                session_id=session.session_id,
                chat_history=chat_history,
                inventory=inventory,
                status_callback=status_callback
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
        """Map internal agent type to event schema agent type."""
        if agent_type is None:
            return AgentType.FRIDGE  # Default

        mapping = {
            AgentTypeEnum.ORCHESTRATOR: AgentType.ORCHESTRATOR,
            AgentTypeEnum.FRIDGE: AgentType.FRIDGE,
            AgentTypeEnum.CALENDAR: AgentType.CALENDAR,
            AgentTypeEnum.INSTACART: AgentType.INSTACART,
            AgentTypeEnum.SERVICES: AgentType.SERVICES,
            AgentTypeEnum.NOTIFICATION: AgentType.NOTIFICATION,
        }
        return mapping.get(agent_type, AgentType.FRIDGE)

    def _is_inventory_query(self, message: str) -> bool:
        """Check if a message is asking about fridge inventory."""
        msg = message.lower()
        keywords = [
            "fridge",
            "refrigerator",
            "firdge",
            "what's in my fridge",
            "whats in my fridge",
            "what do i have",
            "inventory",
            "scan my fridge",
            "scan my firdge",
        ]
        return any(k in msg for k in keywords)

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
