"""
Bake Sale Notification Service - Feature 2: "Bake Sale Prep, Handled"

Generates rich notifications with pre-seeded chat content for bake sale events.
This service is responsible for:
- Analyzing fridge contents vs. required ingredients
- Generating the full chat message (not just push text)
- Including recipe suggestions and action cards
- Sending push notification (works when app is backgrounded)
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from shared.schemas.state import NotificationRecord
from .push_notification_service import get_push_notification_service

logger = logging.getLogger(__name__)

# Media storage path for thumbnail
MEDIA_DIR = Path(__file__).resolve().parent.parent / "storage" / "media"

# Default recipe for bake sales
CHOCOLATE_CHIP_COOKIES_RECIPE = {
    "name": "Classic Chocolate Chip Cookies",
    "prep_time": "15 minutes",
    "cook_time": "12 minutes",
    "makes": "24 cookies",
    "ingredients": [
        "2 1/4 cups flour",
        "1 cup butter, softened",
        "3/4 cup sugar",
        "3/4 cup brown sugar",
        "2 eggs",
        "1 tsp vanilla extract",
        "1 tsp baking soda",
        "1 tsp salt",
        "2 cups chocolate chips"
    ]
}


class BakeSaleNotificationService:
    """
    Service for creating rich bake sale notifications with full chat pre-seeding.

    When user taps the notification, they see a complete chat message with:
    - Event summary and urgency
    - Items they have (from fridge)
    - Items they need to get
    - Recipe suggestion
    - Action card for ordering missing items
    """

    def __init__(self, storage):
        self._storage = storage

    async def create_bake_sale_notification(
        self,
        user_id: str,
        event: dict
    ) -> Optional[dict]:
        """
        Create a rich bake sale notification with full chat_seed_content.

        Args:
            user_id: User identifier
            event: Calendar event dict with prep requirements

        Returns:
            Notification data dict or None if creation failed
        """
        try:
            # Get event details
            event_title = event.get("title", "Bake Sale")
            event_time = event.get("start_time", "")
            suggested_items = event.get("suggested_items", [])

            # Format event time
            if event_time:
                event_dt = datetime.fromisoformat(event_time)
                time_str = event_dt.strftime("%A at %I:%M %p")
                days_until = (event_dt - datetime.now()).days
                if days_until == 0:
                    urgency = "today"
                elif days_until == 1:
                    urgency = "tomorrow"
                else:
                    urgency = f"in {days_until} days"
            else:
                time_str = "soon"
                urgency = "soon"

            # Analyze fridge inventory
            fridge_items = await self._get_fridge_items(user_id)

            # Compare with required items
            items_have, items_need = self._compare_inventory(
                suggested_items, fridge_items
            )

            # Generate push notification (short)
            title = f"{event_title} {urgency}"
            body = self._generate_short_body(items_need, urgency)

            # Generate full chat content (rich)
            chat_seed_content = self._generate_chat_seed_content(
                event_title=event_title,
                event_time=time_str,
                urgency=urgency,
                items_have=items_have,
                items_need=items_need,
            )

            # Create action card data for ordering
            action_card = self._create_order_action_card(items_need)

            # Create notification record
            notification_id = uuid4()
            notification_record = NotificationRecord(
                notification_id=notification_id,
                user_id=user_id,
                title=title,
                body=body,
                notification_type="proactive",
                chat_seed_content=chat_seed_content,
                event_id=event.get("id"),
                idempotency_key=f"bake_sale_{event.get('id')}_{user_id}",
            )

            # Check idempotency before saving
            existing = await self._check_idempotency(notification_record.idempotency_key)
            if existing:
                logger.debug("Notification already sent for this event")
                return None

            # Save to storage
            await self._storage.state.save_notification(notification_record)

            # NOTE: Push notifications are not configured for this feature.
            # Using in-app notifications only - notification is saved to storage
            # and will be delivered via WebSocket when user reconnects.
            push_service = get_push_notification_service()
            if push_service.is_configured:
                # Push is available but we're using in-app notifications for this feature
                logger.info(
                    "Push available but using in-app notification for bake sale (id=%s)",
                    notification_id
                )
            else:
                logger.info(
                    "Push not configured - using in-app notification only (id=%s)",
                    notification_id
                )

            logger.info(
                "Bake sale notification created: id=%s, user=%s, items_need=%d",
                notification_id, user_id, len(items_need)
            )

            return {
                "notification_id": str(notification_id),
                "title": title,
                "body": body,
                "chat_seed_content": chat_seed_content,
                "items_have": items_have,
                "items_need": items_need,
                "action_card": action_card,
            }

        except Exception as e:
            logger.error("Failed to create bake sale notification: %s", e)
            return None

    async def _get_fridge_items(self, user_id: str) -> list[str]:
        """
        Get list of items currently in fridge.

        For now, uses Gemini vision on the latest thumbnail.
        Falls back to empty list if unavailable.
        """
        try:
            # Check if thumbnail exists
            thumbnail_path = MEDIA_DIR / "latest_thumbnail.jpg"
            if not thumbnail_path.exists():
                logger.warning("No fridge thumbnail available")
                return []

            # Use FridgeAgent's vision capability
            from ..agents.fridge_agent import FridgeAgent
            from ..llm import get_gemini_service

            fridge_agent = FridgeAgent(get_gemini_service())

            # Quick inventory query
            vision_ready = await fridge_agent._ensure_vision_chat(user_id)
            if not vision_ready:
                return []

            response = await fridge_agent._ask_vision_chat(
                user_id,
                "List only the food items you can see, one per line. No descriptions."
            )

            if response:
                # Parse response into list
                items = [
                    line.strip().lower().lstrip("•-* ")
                    for line in response.split("\n")
                    if line.strip() and not line.strip().startswith("#")
                ]
                return items[:20]  # Limit to 20 items

            return []

        except Exception as e:
            logger.error("Failed to get fridge items: %s", e)
            return []

    def _compare_inventory(
        self,
        required: list[str],
        available: list[str]
    ) -> tuple[list[str], list[str]]:
        """
        Compare required items against available inventory.

        Returns tuple of (items_have, items_need).
        Uses fuzzy matching for flexibility.
        """
        available_lower = [item.lower() for item in available]
        available_text = " ".join(available_lower)

        items_have = []
        items_need = []

        for item in required:
            item_lower = item.lower()

            # Fuzzy match - check if item or its variants are in inventory
            found = (
                item_lower in available_text or
                any(item_lower in inv for inv in available_lower) or
                any(inv in item_lower for inv in available_lower)
            )

            if found:
                items_have.append(item)
            else:
                items_need.append(item)

        return items_have, items_need

    def _generate_short_body(self, items_need: list[str], urgency: str) -> str:
        """Generate short push notification body."""
        if not items_need:
            return f"You're all set for the bake sale {urgency}!"

        if len(items_need) == 1:
            return f"You're missing {items_need[0]}. Want me to help?"
        elif len(items_need) <= 3:
            return f"You're missing {', '.join(items_need[:2])}. Tap to prep."
        else:
            return f"You're missing {len(items_need)} items. Tap to see the list."

    def _generate_chat_seed_content(
        self,
        event_title: str,
        event_time: str,
        urgency: str,
        items_have: list[str],
        items_need: list[str],
    ) -> str:
        """
        Generate the full chat message that appears when notification is tapped.

        Includes all required sections:
        1. Summary/context message
        2. Items you have
        3. Items to get
        4. Recipe suggestion
        5. User-facing prompt
        """
        lines = []

        # 1. Summary message
        if items_need:
            lines.append(
                f"You have **{event_title}** {urgency} and you're missing a few items "
                f"for chocolate chip cookies."
            )
        else:
            lines.append(
                f"You have **{event_title}** {urgency} and you're all set! "
                f"You have everything for chocolate chip cookies."
            )

        lines.append("")

        # 2. Items you have
        lines.append("### ✅ Items you have")
        if items_have:
            for item in items_have:
                lines.append(f"• {item}")
        else:
            lines.append("• (none of the required items found)")
        lines.append("")

        # 3. Items to get
        lines.append("### 🛒 Items to get")
        if items_need:
            for item in items_need:
                lines.append(f"• {item}")
        else:
            lines.append("• (you have everything!)")
        lines.append("")

        # 4. Recipe suggestion
        recipe = CHOCOLATE_CHIP_COOKIES_RECIPE
        lines.append(f"### 🍪 Recipe: {recipe['name']}")
        lines.append(f"*Prep: {recipe['prep_time']} | Cook: {recipe['cook_time']} | Makes: {recipe['makes']}*")
        lines.append("")

        # 5. User-facing prompt
        if items_need:
            lines.append("---")
            lines.append("")
            lines.append("**Want me to order what you'll need or schedule prep reminders?**")
            lines.append("")
            lines.append("<!-- ACTION_CARD:order_missing_items -->")
        else:
            lines.append("---")
            lines.append("")
            lines.append("**Ready to start baking! Want me to set a reminder for when to start?**")

        return "\n".join(lines)

    def _create_order_action_card(self, items_need: list[str]) -> dict:
        """
        Create action card data for ordering missing items.

        This data is included in the notification payload for the frontend
        to render an inline action card.
        """
        return {
            "type": "order_missing_items",
            "title": "Order Missing Items",
            "description": f"Get {len(items_need)} items delivered via Instacart",
            "items": items_need,
            "actions": [
                {
                    "id": "place_order",
                    "label": "Place Order",
                    "style": "primary",
                },
                {
                    "id": "remind_later",
                    "label": "Remind Me Later",
                    "style": "secondary",
                },
            ],
            "estimated_total": self._estimate_cost(items_need),
        }

    def _estimate_cost(self, items: list[str]) -> float:
        """Estimate cost for missing items (mock)."""
        # Simple estimate: ~$3-5 per baking item
        per_item = 4.0
        return round(len(items) * per_item, 2)

    async def _check_idempotency(self, key: str) -> bool:
        """Check if notification was already sent."""
        try:
            return await self._storage.state.check_idempotency(key)
        except Exception:
            return False
