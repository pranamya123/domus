"""
Event Bus Handlers - Subscribers for system-wide events.

Provides reactive behavior for:
- Inventory updates triggering proactive checks
- Hardware events triggering alerts
- Intent processing for analytics
"""

import logging
from typing import TYPE_CHECKING

from app.core.event_bus import Event, EventType, EventBus

if TYPE_CHECKING:
    from app.core.event_bus import EventBus

logger = logging.getLogger(__name__)


async def handle_inventory_updated(event: Event) -> None:
    """
    Trigger proactive checks when inventory changes.

    Called whenever the inventory is updated through image analysis
    or manual updates. Can trigger:
    - Calendar meal planning checks
    - Deal matching
    - Expiry predictions
    """
    logger.info(
        f"Inventory updated for household {event.household_id}: "
        f"{event.payload.get('total_items', 0)} items"
    )

    # Log temporal analysis results if available
    temporal = event.payload.get("temporal_analysis", {})
    if temporal:
        logger.debug(
            f"Temporal changes - Additions: {temporal.get('additions', 0)}, "
            f"Removals: {temporal.get('removals', 0)}, "
            f"Movements: {temporal.get('movements', 0)}"
        )


async def handle_hardware_disconnected(event: Event) -> None:
    """
    Log and potentially alert on hardware issues.

    Called when a hardware device (camera, sensor) disconnects.
    Logs the event for monitoring and could trigger user alerts.
    """
    device_type = event.payload.get("device_type", "unknown")
    last_seen = event.payload.get("last_seen")

    logger.warning(
        f"Hardware disconnected - Type: {device_type}, "
        f"Household: {event.household_id}, Last seen: {last_seen}"
    )


async def handle_intent_expiry_warning(event: Event) -> None:
    """
    Track expiry warnings for analytics.

    Called when items are approaching expiration.
    Useful for tracking food waste patterns.
    """
    count = event.payload.get("count", 0)
    items = event.payload.get("expiring_items", [])

    logger.info(
        f"Expiry warning for household {event.household_id}: "
        f"{count} items expiring soon"
    )

    # Log individual items for analytics
    for item in items[:5]:  # Log first 5
        logger.debug(
            f"  - {item.get('name')}: expires in {item.get('days_until_expiry', '?')} days"
        )


async def handle_intent_detected_expiry(event: Event) -> None:
    """
    Track expired items for food waste analytics.

    Called when items are detected as expired.
    """
    count = event.payload.get("count", 0)

    logger.warning(
        f"Expired items detected for household {event.household_id}: "
        f"{count} items expired"
    )


async def handle_intent_require_procurement(event: Event) -> None:
    """
    Track procurement needs for shopping list automation.

    Called when staple items are detected as missing.
    """
    missing = event.payload.get("missing_items", [])
    category = event.payload.get("category", "general")

    logger.info(
        f"Procurement needed for household {event.household_id}: "
        f"{', '.join(missing)} ({category})"
    )


async def handle_intent_item_added(event: Event) -> None:
    """Track items added to inventory."""
    item_name = event.payload.get("item_name", "unknown")
    location = event.payload.get("location", "unknown")

    logger.info(
        f"Item added for household {event.household_id}: "
        f"{item_name} at {location}"
    )


async def handle_intent_item_removed(event: Event) -> None:
    """Track items removed from inventory."""
    item_name = event.payload.get("item_name", "unknown")
    last_location = event.payload.get("last_location", "unknown")

    logger.info(
        f"Item removed for household {event.household_id}: "
        f"{item_name} from {last_location}"
    )


async def handle_intent_item_moved(event: Event) -> None:
    """Track items moved within fridge."""
    item_name = event.payload.get("item_name", "unknown")
    from_loc = event.payload.get("from_location", "unknown")
    to_loc = event.payload.get("to_location", "unknown")

    logger.debug(
        f"Item moved for household {event.household_id}: "
        f"{item_name} from {from_loc} to {to_loc}"
    )


async def handle_intent_consumption_likely(event: Event) -> None:
    """Track likely consumption events for usage patterns."""
    item_name = event.payload.get("item_name", "unknown")
    confidence = event.payload.get("consumption_confidence", 0)

    logger.info(
        f"Consumption likely for household {event.household_id}: "
        f"{item_name} ({confidence:.0%} confidence)"
    )


async def handle_intent_calendar_ingredient_missing(event: Event) -> None:
    """Track calendar-related procurement needs."""
    event_title = event.payload.get("event_title", "unknown event")
    missing = event.payload.get("missing_ingredients", [])
    urgency = event.payload.get("urgency", "medium")

    logger.info(
        f"Calendar ingredient alert for household {event.household_id}: "
        f"{event_title} missing {', '.join(missing)} (urgency: {urgency})"
    )


async def handle_notification_created(event: Event) -> None:
    """Track notifications for delivery analytics."""
    notification_type = event.payload.get("notification_type", "unknown")
    severity = event.payload.get("severity", "low")

    logger.debug(
        f"Notification created for household {event.household_id}: "
        f"type={notification_type}, severity={severity}"
    )


async def handle_system_error(event: Event) -> None:
    """Log and track system errors."""
    error = event.payload.get("error", "Unknown error")
    source = event.payload.get("source", "unknown")

    logger.error(
        f"System error from {source} for household {event.household_id}: {error}"
    )


def register_handlers(event_bus: EventBus) -> None:
    """
    Register all event handlers with the event bus.

    Called during application startup to set up event subscriptions.
    """
    logger.info("Registering event handlers...")

    # Inventory events
    event_bus.subscribe(EventType.INVENTORY_UPDATED, handle_inventory_updated)

    # Hardware events
    event_bus.subscribe(EventType.HARDWARE_DISCONNECTED, handle_hardware_disconnected)

    # Intent events - Expiry
    event_bus.subscribe(EventType.INTENT_EXPIRY_WARNING, handle_intent_expiry_warning)
    event_bus.subscribe(EventType.INTENT_DETECTED_EXPIRY, handle_intent_detected_expiry)

    # Intent events - Procurement
    event_bus.subscribe(EventType.INTENT_REQUIRE_PROCUREMENT, handle_intent_require_procurement)

    # Intent events - Temporal
    event_bus.subscribe(EventType.INTENT_ITEM_ADDED, handle_intent_item_added)
    event_bus.subscribe(EventType.INTENT_ITEM_REMOVED, handle_intent_item_removed)
    event_bus.subscribe(EventType.INTENT_ITEM_MOVED, handle_intent_item_moved)
    event_bus.subscribe(EventType.INTENT_CONSUMPTION_LIKELY, handle_intent_consumption_likely)

    # Intent events - Calendar
    event_bus.subscribe(EventType.INTENT_CALENDAR_INGREDIENT_MISSING, handle_intent_calendar_ingredient_missing)

    # Notification events
    event_bus.subscribe(EventType.NOTIFICATION_CREATED, handle_notification_created)

    # System events
    event_bus.subscribe(EventType.SYSTEM_ERROR, handle_system_error)

    logger.info(f"Registered {12} event handlers")
