"""
Event Evaluation Runner - Proactive Push Notifications

This is a BACKGROUND RUNNER, not an agent. It:
- Runs on a configurable scheduler interval (not user input)
- Queries existing agents/services for data
- Applies deterministic, code-based rules for notification decisions
- Uses LLM ONLY for ingredient inference (cached) and notification text

This module is completely separate from the chat orchestrator.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field
from uuid import uuid4

from app.services.calendar_service import CalendarService, get_calendar_service
from app.services.push_notification_service import PushNotificationService, get_push_notification_service
from app.llm import GeminiService, get_gemini_service
from app.llm.prompts import PUSH_NOTIFICATION_PROMPTS
from shared.schemas.state import NotificationRecord as StoredNotification

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class EventEvaluatorConfig:
    """Configuration for the Event Evaluation Runner."""
    # How often the runner checks for events (seconds)
    check_interval_seconds: int = 300  # 5 minutes

    # Lead time windows for different event types (hours before event)
    lead_time_hours: dict[str, int] = field(default_factory=lambda: {
        "bake_sale": 24,      # 24 hours before bake sale
        "potluck": 24,        # 24 hours before potluck
        "dinner_party": 12,   # 12 hours before dinner party
        "meal_prep": 6,       # 6 hours before meal prep events
        "default": 12,        # Default lead time
    })


# =============================================================================
# Cached Ingredient Lists (per event type)
# =============================================================================

# These are deterministic mappings. LLM is used ONLY to infer ingredients
# for NEW event types not in this cache.
CRITICAL_INGREDIENTS_CACHE: dict[str, list[str]] = {
    "bake_sale": ["flour", "sugar", "eggs", "butter", "baking powder", "vanilla"],
    "potluck": ["main dish ingredients"],  # Generic - will use LLM for specific event
    "dinner_party": ["protein", "vegetables", "wine", "dessert"],
    "workout": ["protein", "banana", "yogurt", "eggs"],
    "birthday_party": ["cake ingredients", "candles", "ice cream"],
    "breakfast_meeting": ["eggs", "bread", "coffee", "fruit", "juice"],
}


@dataclass
class LocalNotificationRecord:
    """Track sent notifications locally to ensure idempotency within session."""
    event_id: str
    sent_at: datetime
    missing_items: list[str]


class EventEvaluationRunner:
    """
    Background runner for proactive event-based notifications.

    Flow:
    1. Scheduler triggers evaluation at configured interval
    2. Query CalendarService for upcoming events within lead-time windows
    3. For each qualifying event:
       a. Load cached critical ingredients (or infer once via LLM)
       b. Get current fridge inventory (text-based, no new image analysis)
       c. Compare inventory vs required items IN CODE (deterministic)
    4. If critical items missing:
       a. Generate short push notification via LLM (dedicated prompt)
       b. Create notification in storage (with chat_seed_content)
       c. Emit WebSocket event for real-time UI update
       d. Send exactly one notification per event (idempotent)

    This runner does NOT:
    - Handle user chat messages
    - Route through the orchestrator
    - Use the chat synthesis prompt
    - Re-analyze fridge images
    """

    def __init__(
        self,
        calendar_service: Optional[CalendarService] = None,
        llm_service: Optional[GeminiService] = None,
        config: Optional[EventEvaluatorConfig] = None,
        storage=None,  # RedisDomusStorage - optional, set via set_storage()
        push_service: Optional[PushNotificationService] = None,
    ):
        self.calendar = calendar_service or get_calendar_service()
        self.llm = llm_service or get_gemini_service()
        self.config = config or EventEvaluatorConfig()
        self._storage = storage
        self._push_service = push_service or get_push_notification_service()

        # Track sent notifications locally for idempotency
        self._sent_notifications: dict[str, LocalNotificationRecord] = {}

        # Cache for LLM-inferred ingredients (populated on first encounter)
        self._ingredient_cache: dict[str, list[str]] = CRITICAL_INGREDIENTS_CACHE.copy()

        # Current fridge inventory (set externally or via callback)
        self._current_inventory: list[str] = []

        # Callbacks (websocket callback for real-time UI, push is handled by _push_service)
        self._notification_callback: Optional[Callable[[str, str, str], Awaitable[bool]]] = None
        self._websocket_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None

        # Runner state
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info("EventEvaluationRunner initialized (interval=%ds, push_configured=%s)",
                    self.config.check_interval_seconds, self._push_service.is_configured)

    def set_storage(self, storage) -> None:
        """Set the storage backend for persisting notifications."""
        self._storage = storage

    def set_notification_callback(self, callback: Callable[[str, str, str], Awaitable[bool]]) -> None:
        """
        Set the callback for sending push notifications (e.g., mobile push).

        Callback signature: async def callback(user_id: str, title: str, body: str) -> bool
        """
        self._notification_callback = callback

    def set_websocket_callback(self, callback: Callable[[str, dict], Awaitable[None]]) -> None:
        """
        Set the callback for emitting WebSocket events (for real-time UI updates).

        Callback signature: async def callback(user_id: str, notification_data: dict) -> None
        """
        self._websocket_callback = callback

    def update_inventory(self, inventory_items: list[str]) -> None:
        """
        Update the current fridge inventory.

        Called externally when fridge inventory changes (e.g., after vision analysis).
        This avoids re-running expensive multimodal inference.

        Args:
            inventory_items: List of item names currently in the fridge
        """
        self._current_inventory = [item.lower() for item in inventory_items]
        logger.debug("Inventory updated: %d items", len(self._current_inventory))

    async def start(self) -> None:
        """Start the background evaluation loop."""
        if self._running:
            logger.warning("EventEvaluationRunner already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("EventEvaluationRunner started")

    async def stop(self) -> None:
        """Stop the background evaluation loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("EventEvaluationRunner stopped")

    async def _run_loop(self) -> None:
        """Main evaluation loop - runs at configured interval."""
        while self._running:
            try:
                await self.evaluate_all_users()
            except Exception as e:
                logger.error("Event evaluation error: %s", e)

            await asyncio.sleep(self.config.check_interval_seconds)

    async def evaluate_all_users(self) -> None:
        """
        Evaluate events for all users.

        In production, this would iterate over active users.
        For now, uses a placeholder user_id.
        """
        # TODO: Get list of active users from session storage
        user_ids = ["default_user"]

        for user_id in user_ids:
            await self.evaluate_user_events(user_id)

    async def evaluate_user_events(self, user_id: str) -> list[dict]:
        """
        Evaluate upcoming events for a user and send notifications if needed.

        Returns list of notifications sent (for testing/logging).
        """
        notifications_sent = []

        # Step 1: Get upcoming events from CalendarService
        upcoming_events = await self._get_events_in_lead_window(user_id)

        if not upcoming_events:
            logger.debug("No qualifying events for user %s", user_id)
            return notifications_sent

        logger.info("Evaluating %d events for user %s", len(upcoming_events), user_id)

        for event in upcoming_events:
            event_id = event.get("id")

            # Step 2: Check idempotency - skip if already notified
            if self._already_notified(event_id):
                logger.debug("Already notified for event %s", event_id)
                continue

            # Step 3: Get critical ingredients for this event type
            event_type = self._classify_event_type(event)
            critical_items = await self._get_critical_ingredients(event_type, event)

            if not critical_items:
                continue

            # Step 4: Compare inventory vs required items (DETERMINISTIC - no LLM)
            missing_items = self._find_missing_items(critical_items)

            if not missing_items:
                logger.debug("All critical items present for event %s", event_id)
                continue

            # Step 5: Generate and send notification (LLM for text only)
            notification = await self._generate_and_send_notification(
                user_id, event, missing_items
            )

            if notification:
                notifications_sent.append(notification)
                self._record_notification(event_id, missing_items)

        return notifications_sent

    async def _get_events_in_lead_window(self, user_id: str) -> list[dict]:
        """
        Get events that are within their lead-time window.

        An event qualifies if: now < event_start < now + lead_time
        """
        now = datetime.now()
        max_lead_hours = max(self.config.lead_time_hours.values())

        # Get events in the next max_lead_hours
        events = await self.calendar.get_events(
            user_id,
            start_date=now,
            end_date=now + timedelta(hours=max_lead_hours)
        )

        qualifying_events = []
        for event in events:
            event_type = self._classify_event_type(event)
            lead_hours = self.config.lead_time_hours.get(
                event_type,
                self.config.lead_time_hours["default"]
            )

            event_start = datetime.fromisoformat(event["start_time"])
            time_until_event = (event_start - now).total_seconds() / 3600

            # Event is within its lead-time window
            if 0 < time_until_event <= lead_hours:
                qualifying_events.append(event)

        return qualifying_events

    def _classify_event_type(self, event: dict) -> str:
        """
        Classify event into a category for ingredient lookup.

        Uses deterministic keyword matching (no LLM).
        """
        title = event.get("title", "").lower()
        description = event.get("description", "").lower()
        text = f"{title} {description}"

        # Keyword-based classification
        if any(kw in text for kw in ["bake", "baking", "bake sale"]):
            return "bake_sale"
        if any(kw in text for kw in ["potluck", "bring a dish"]):
            return "potluck"
        if any(kw in text for kw in ["dinner party", "hosting dinner"]):
            return "dinner_party"
        if any(kw in text for kw in ["workout", "gym", "exercise"]):
            return "workout"
        if any(kw in text for kw in ["birthday", "bday"]):
            return "birthday_party"
        if any(kw in text for kw in ["breakfast meeting", "morning meeting"]):
            return "breakfast_meeting"

        return "default"

    async def _get_critical_ingredients(
        self,
        event_type: str,
        event: dict
    ) -> list[str]:
        """
        Get critical ingredients for an event type.

        Uses cached list if available. Falls back to LLM inference ONCE
        for new event types, then caches the result.
        """
        # Check cache first
        if event_type in self._ingredient_cache:
            return self._ingredient_cache[event_type]

        # LLM inference for unknown event types (one-time, then cached)
        logger.info("Inferring ingredients for new event type: %s", event_type)

        prompt = PUSH_NOTIFICATION_PROMPTS["ingredient_inference"].format(
            event_title=event.get("title", ""),
            event_description=event.get("description", "")
        )

        try:
            response = await self.llm.generate(prompt=prompt)
            # Parse comma-separated ingredients from response
            ingredients = [
                item.strip().lower()
                for item in response.content.split(",")
                if item.strip()
            ]

            # Cache for future use
            self._ingredient_cache[event_type] = ingredients
            logger.info("Cached ingredients for %s: %s", event_type, ingredients)

            return ingredients
        except Exception as e:
            logger.error("Failed to infer ingredients: %s", e)
            return []

    def _find_missing_items(self, required_items: list[str]) -> list[str]:
        """
        Find items that are required but not in inventory.

        This is DETERMINISTIC - no LLM involved.
        Uses fuzzy matching for common variations.
        """
        missing = []

        for required in required_items:
            required_lower = required.lower()

            # Check if any inventory item matches (partial match for flexibility)
            found = any(
                required_lower in inv_item or inv_item in required_lower
                for inv_item in self._current_inventory
            )

            if not found:
                missing.append(required)

        return missing

    async def _generate_and_send_notification(
        self,
        user_id: str,
        event: dict,
        missing_items: list[str]
    ) -> Optional[dict]:
        """
        Generate push notification text via LLM and send it.

        Uses a DEDICATED prompt (not the chat synthesis prompt).
        Creates a notification record with chat_seed_content for seamless
        transition to chat when user clicks the notification.
        """
        # Generate notification text using dedicated push prompt
        prompt = PUSH_NOTIFICATION_PROMPTS["push_notification"].format(
            event_title=event.get("title", ""),
            event_time=event.get("start_time", ""),
            missing_items=", ".join(missing_items)
        )

        try:
            response = await self.llm.generate(prompt=prompt)
            notification_text = response.content.strip()

            # Parse title and body (format: "Title: ... Body: ...")
            title, body = self._parse_notification_text(notification_text, event, missing_items)

            # Create chat_seed_content - EXACT text that will appear in chat
            # This is the SAME content as title + body for consistency
            chat_seed_content = f"{title}\n\n{body}"

            # Create notification record in storage
            notification_id = uuid4()
            if self._storage:
                notification_record = StoredNotification(
                    notification_id=notification_id,
                    user_id=user_id,
                    title=title,
                    body=body,
                    notification_type="proactive",
                    chat_seed_content=chat_seed_content,
                    event_id=event.get("id"),
                    idempotency_key=f"event_{event.get('id')}_prep_reminder",
                )
                await self._storage.state.save_notification(notification_record)
                logger.info("Notification saved to storage: %s", notification_id)

            # Emit WebSocket event for real-time UI update
            if self._websocket_callback:
                await self._websocket_callback(user_id, {
                    "notification_id": str(notification_id),
                    "title": title,
                    "body": body,
                    "notification_type": "proactive",
                    "event_id": event.get("id"),
                })

            # Send mobile push via push service (if configured)
            if self._push_service and self._push_service.is_configured:
                push_result = await self._push_service.send_notification(
                    user_id=user_id,
                    title=title,
                    body=body,
                    notification_id=str(notification_id),
                )
                if not push_result.success:
                    logger.warning("Push notification failed for event %s: %s",
                                   event.get("id"), push_result.error)
                else:
                    logger.info("Mobile push sent: %s", push_result.message_id)
            elif self._notification_callback:
                # Fallback to callback if push service not configured
                success = await self._notification_callback(user_id, title, body)
                if not success:
                    logger.warning("Push notification callback failed for event %s", event.get("id"))

            logger.info("Notification sent for event %s: %s", event.get("id"), title)
            return {
                "notification_id": str(notification_id),
                "event_id": event.get("id"),
                "title": title,
                "body": body,
                "chat_seed_content": chat_seed_content,
                "missing_items": missing_items
            }

        except Exception as e:
            logger.error("Failed to send notification: %s", e)
            return None

    def _parse_notification_text(
        self,
        llm_output: str,
        event: dict,
        missing_items: list[str]
    ) -> tuple[str, str]:
        """
        Parse LLM output into title and body.

        Falls back to deterministic text if parsing fails.
        """
        # Try to parse "Title: ... Body: ..." format
        if "Title:" in llm_output and "Body:" in llm_output:
            parts = llm_output.split("Body:")
            title = parts[0].replace("Title:", "").strip()
            body = parts[1].strip() if len(parts) > 1 else ""
            return title, body

        # Fallback to deterministic format
        title = f"Prep reminder: {event.get('title', 'Upcoming event')}"
        body = f"You may be missing: {', '.join(missing_items[:3])}"
        return title, body

    def _already_notified(self, event_id: str) -> bool:
        """Check if we've already sent a notification for this event."""
        return event_id in self._sent_notifications

    def _record_notification(self, event_id: str, missing_items: list[str]) -> None:
        """Record that a notification was sent (for idempotency)."""
        self._sent_notifications[event_id] = LocalNotificationRecord(
            event_id=event_id,
            sent_at=datetime.now(),
            missing_items=missing_items
        )

    def clear_old_notifications(self, max_age_hours: int = 48) -> None:
        """Clear notification records older than max_age_hours."""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        self._sent_notifications = {
            event_id: record
            for event_id, record in self._sent_notifications.items()
            if record.sent_at > cutoff
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_event_evaluator: Optional[EventEvaluationRunner] = None


def get_event_evaluator() -> EventEvaluationRunner:
    """Get or create the singleton EventEvaluationRunner instance."""
    global _event_evaluator
    if _event_evaluator is None:
        _event_evaluator = EventEvaluationRunner()
    return _event_evaluator
