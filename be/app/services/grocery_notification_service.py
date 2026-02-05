"""
Grocery Notification Service for Domus

Generates location-based grocery notifications when user enters a store
and has items marked as "out" or "low".

Demo-focused: deterministic logic, no ML, no Places API.
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
# Demo: Items that trigger notifications
# =============================================================================
# In production, this would come from fridge inventory analysis.
# For demo, we use a simple lookup per user.

DEMO_LOW_ITEMS: dict[str, list[dict]] = {
    # Default demo user - milk is out
    "default": [
        {"item": "milk", "status": "out"},
    ],
    # Can add more user-specific demo data
    "demo_user": [
        {"item": "milk", "status": "out"},
        {"item": "eggs", "status": "low"},
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

        # Get low/out items for user (demo: hardcoded)
        low_items = self._get_low_items(user_id)
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
        """Create and store the notification."""
        item_name = item["item"]
        item_status = item["status"]

        # Generate notification content
        if item_status == "out":
            title = f"Noticed you're at {store.name}"
            body = f"You're out of {item_name}. Want to pick some up?"
        else:
            title = f"Noticed you're at {store.name}"
            body = f"You're running low on {item_name}. Good time to restock?"

        # Chat seed content for when user taps notification
        chat_seed = (
            f"You're at {store.name} and {item_name} is marked as "
            f"{'out of stock' if item_status == 'out' else 'running low'}. "
            f"I can help you find it or add it to your shopping list."
        )

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
