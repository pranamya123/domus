"""
Grocery Notification Service for Domus

Feature: Context-Aware Suggestions (Judgment-Driven)

CORE PRINCIPLE: Deliver one non-obvious insight, not restate the trigger.
Domus should sound like it noticed something useful, not like it fired a notification.

BEHAVIOR: When user taps notification, lead with WHY this moment matters.
The location is implicit — the value is the situational judgment.

RESPONSE STRUCTURE:
1. Judgment-driven opening (temporal reasoning, pattern recognition)
2. Single item, confident tone
3. Soft, optional action question

HARD CONSTRAINTS:
- Do NOT restate the location as the main point
- Do NOT sound like a reminder system
- Do NOT list multiple items
- Do NOT ask more than one question
- Do NOT introduce the assistant

TONE: Thoughtful nudge, not system notification.
SUCCESS: "That's actually a thoughtful nudge." vs "A system noticed a thing."
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from ..storage.redis_store import RedisDomusStorage
from .location_service import DemoStore, GeofenceEntry
from .push_notification_service import get_push_notification_service

logger = logging.getLogger(__name__)


# =============================================================================
# Demo: Items that trigger notifications (with context for smart reasoning)
# =============================================================================
# In production, this would come from fridge inventory analysis.
# For demo, we include context to enable judgment-driven responses.

DEMO_LOW_ITEMS: dict[str, list[dict]] = {
    # Default demo user - milk is out
    "default": [
        {"item": "milk", "status": "out", "days_out": 3},
    ],
    # Can add more user-specific demo data
    "demo_user": [
        {"item": "milk", "status": "out", "days_out": 3},
        {"item": "eggs", "status": "low", "days_out": 0},
    ],
}


class GroceryNotificationService:
    """
    Generates contextual grocery store notifications.

    When user enters a grocery store geofence:
    1. Check if user has low/out items (demo: hardcoded)
    2. Generate notification with store name
    3. Send push notification
    4. Store for chat context
    """

    def __init__(self, storage: RedisDomusStorage):
        self._storage = storage
        self._push_service = get_push_notification_service()

        # Cooldown: 1 notification per store per day
        self._cooldown_hours = 24

    async def handle_geofence_entry(
        self,
        entry: GeofenceEntry,
        store: DemoStore
    ) -> Optional[dict]:
        """
        Handle a geofence entry event.

        Returns notification dict if sent, None otherwise.
        """
        user_id = entry.user_id
        logger.info(f"[GROCERY] handle_geofence_entry called for user={user_id}, store={store.name}")

        # Get low/out items for user (demo: hardcoded)
        low_items = self._get_low_items(user_id)
        logger.info(f"[GROCERY] low_items for {user_id}: {low_items}")
        if not low_items:
            logger.debug(f"No low items for user {user_id}")
            return None

        # Find first item that isn't on cooldown for this store
        # Cooldown is (user_id, store_id, item_name) - allows different items at same store
        priority_item = None
        for item in self._sort_items_by_priority(low_items):
            item_name = item["item"]
            cooldown_key = f"grocery_notif:{user_id}:{store.place_id}:{item_name}"

            if not await self._check_cooldown(cooldown_key):
                priority_item = item
                break
            else:
                logger.debug(f"Cooldown active for {item_name} at {store.name}")

        if not priority_item:
            logger.info(f"All items on cooldown for {user_id} at {store.name}")
            return None

        # Generate notification
        notification = await self._create_notification(
            user_id=user_id,
            store=store,
            item=priority_item,
        )

        # Set cooldown for this specific (store, item) combination
        item_name = priority_item["item"]
        cooldown_key = f"grocery_notif:{user_id}:{store.place_id}:{item_name}"
        await self._set_cooldown(cooldown_key)

        logger.info(
            f"Grocery notification sent: user={user_id}, "
            f"store={store.name}, item={item_name}"
        )

        return notification

    def _sort_items_by_priority(self, items: list[dict]) -> list[dict]:
        """Sort items by priority: 'out' items first, then 'low' items."""
        out_items = [i for i in items if i.get("status") == "out"]
        low_items = [i for i in items if i.get("status") == "low"]
        return out_items + low_items

    def _get_low_items(self, user_id: str) -> list[dict]:
        """
        Get low/out items for user.

        Demo: returns hardcoded items.
        Production: would query fridge inventory service.
        """
        # Check user-specific items first, fall back to default
        return DEMO_LOW_ITEMS.get(user_id, DEMO_LOW_ITEMS.get("default", []))

    async def _create_notification(
        self,
        user_id: str,
        store: DemoStore,
        item: dict
    ) -> dict:
        """
        Create and store the notification.

        Response follows the In-Store Intelligence structure:
        1. Contextual Acknowledgment (store + current presence)
        2. Relevant Reminder (1 item, no explanations)
        3. Gentle Action Question (low-commitment)
        """
        item_name = item["item"]
        item_status = item["status"]

        # Generate push notification content (short)
        title = f"Noticed you're at {store.name}"
        if item_status == "out":
            body = f"You're out of {item_name}. Want to pick some up?"
        else:
            body = f"Running low on {item_name}. Good time to grab some?"

        # Chat seed content - Judgment-driven suggestion
        # Leads with WHY this moment matters, not the trigger
        days_out = item.get("days_out", 0)
        chat_seed = self._generate_in_store_chat_seed(
            store_name=store.name,
            item_name=item_name,
            item_status=item_status,
            days_out=days_out,
        )

        # Create action card for in-store assist (not Instacart order)
        action_card = self._create_in_store_action_card(item_name)

        notification_id = str(uuid4())

        # Store notification
        from shared.schemas.state import NotificationRecord
        notification_record = NotificationRecord(
            notification_id=notification_id,
            user_id=user_id,
            title=title,
            body=body,
            sent_at=datetime.utcnow(),
            notification_type="proactive",
            chat_seed_content=chat_seed,
            idempotency_key=f"grocery_{user_id}_{store.place_id}_{datetime.utcnow().date()}",
        )

        await self._storage.state.save_notification(notification_record)
        logger.info(
            "Grocery notification saved to storage: id=%s, title=%s",
            notification_id, title
        )

        # Send push notification (if configured)
        # Note: For demo, push may not be configured - in-app notification still works
        try:
            if self._push_service.is_configured:
                await self._push_service.send_notification(
                    user_id=user_id,
                    title=title,
                    body=body,
                    notification_id=notification_id,
                )
                logger.info(f"Push notification sent for grocery alert: {user_id}")
            else:
                logger.info(f"Push not configured - using in-app notification only for {user_id}")
        except Exception as e:
            logger.warning(f"Push notification failed (in-app still works): {e}")

        return {
            "notification_id": notification_id,
            "title": title,
            "body": body,
            "chat_seed_content": chat_seed,
            "store": store.name,
            "item": item_name,
            "action_card": action_card,
        }

    def _generate_in_store_chat_seed(
        self,
        store_name: str,
        item_name: str,
        item_status: str,
        days_out: int = 0,
    ) -> str:
        """
        Generate a judgment-driven in-store suggestion.

        FORMAT: "[Temporal reasoning] — and you're at [store], which makes this a good moment to [action]."

        HARD CONSTRAINTS:
        - Lead with temporal/inventory insight, not location
        - Location comes second, as supporting context
        - End with why this moment matters
        - Single item only
        - One soft action question

        TONE: Thoughtful nudge, not system notification.
        """
        # Generate judgment-driven message
        # Format: [Insight] — and you're at [store], which makes this a good moment to grab it.
        if item_status == "out" and days_out >= 2:
            insight = f"You've been out of **{item_name}** for a few days"
        elif item_status == "out":
            insight = f"**{item_name.capitalize()}** ran out recently"
        else:
            insight = f"You're running low on **{item_name}**"

        # Combine insight + location + moment
        message = f"{insight} — and you're at {store_name}, which makes this a good moment to grab it."

        # Soft, optional action
        action = "Want me to add it to your list?"

        return f"{message}\n\n{action}"

    def _create_in_store_action_card(self, item_name: str) -> dict:
        """
        Create action card for in-store assist.

        NOT an Instacart order flow.
        This is a lightweight in-store helper.

        Actions:
        - Add to list
        - Mark as picked up
        - Ignore (dismiss)
        """
        return {
            "type": "in_store_assist",
            "title": item_name.capitalize(),
            "description": "Quick action",
            "item": item_name,
            "actions": [
                {
                    "id": "add_to_list",
                    "label": "Add to List",
                    "style": "secondary",
                },
                {
                    "id": "picked_up",
                    "label": "Picked Up",
                    "style": "primary",
                },
            ],
        }

    async def _check_cooldown(self, key: str) -> bool:
        """Check if cooldown is active for this key."""
        try:
            value = await self._storage.redis.get(key)
            return value is not None
        except Exception:
            return False

    async def _set_cooldown(self, key: str) -> None:
        """Set cooldown for this key."""
        try:
            await self._storage.redis.setex(
                key,
                timedelta(hours=self._cooldown_hours),
                "1"
            )
        except Exception as e:
            logger.error(f"Failed to set cooldown: {e}")


# Singleton instance
_grocery_notification_service: Optional[GroceryNotificationService] = None


def get_grocery_notification_service(
    storage: RedisDomusStorage
) -> GroceryNotificationService:
    """Get or create the singleton grocery notification service."""
    global _grocery_notification_service
    if _grocery_notification_service is None:
        _grocery_notification_service = GroceryNotificationService(storage)
    return _grocery_notification_service
