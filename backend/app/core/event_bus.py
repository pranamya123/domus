"""
Typed Event Bus for agent communication.

Semantics:
- Asynchronous, in-process (Phase 1)
- Typed events only (no unstructured dicts)
- At-least-once delivery
- No direct agent-to-agent calls
- All coordination flows through the Orchestrator
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Typed event categories for the system."""

    # Fridge Events
    IMAGE_UPLOADED = "image.uploaded"
    IMAGE_VALIDATED = "image.validated"
    IMAGE_REJECTED = "image.rejected"
    INVENTORY_UPDATED = "inventory.updated"

    # Intent Events (L1 -> L0)
    INTENT_EXPIRY_WARNING = "intent.expiry_warning"
    INTENT_REQUIRE_PROCUREMENT = "intent.require_procurement"
    INTENT_DETECTED_EXPIRY = "intent.detected_expiry"
    INTENT_BULK_BUY_OPPORTUNITY = "intent.bulk_buy_opportunity"

    # Temporal Events
    INTENT_ITEM_ADDED = "intent.item_added"
    INTENT_ITEM_REMOVED = "intent.item_removed"
    INTENT_ITEM_MOVED = "intent.item_moved"
    INTENT_CONSUMPTION_LIKELY = "intent.consumption_likely"

    # Calendar Events
    INTENT_CALENDAR_INGREDIENT_MISSING = "intent.calendar_ingredient_missing"

    # Notification Events
    NOTIFICATION_CREATED = "notification.created"
    NOTIFICATION_DELIVERED = "notification.delivered"
    NOTIFICATION_FAILED = "notification.failed"

    # Hardware Events
    IOT_IMAGE_RECEIVED = "iot.image_received"
    HARDWARE_DISCONNECTED = "hardware.disconnected"

    # System Events
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    SYSTEM_ERROR = "system.error"


@dataclass
class Event:
    """Base event structure with required metadata."""

    event_type: EventType
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "system"
    household_id: Optional[str] = None
    user_id: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.event_type, EventType):
            raise TypeError(f"event_type must be EventType, got {type(self.event_type)}")
        if not isinstance(self.payload, dict):
            raise TypeError(f"payload must be dict, got {type(self.payload)}")


class EventBus:
    """
    Asynchronous event bus with typed events and at-least-once delivery.

    Subscribers are notified asynchronously. Failed deliveries are retried once.
    """

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._all_subscribers: List[Callable] = []
        self._running = False
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._processed_events: Set[str] = set()
        self._max_processed_cache = 10000

    async def start(self):
        """Start the event bus worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")

    async def stop(self):
        """Stop the event bus worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")

    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type.value}")

    def subscribe_all(self, handler: Callable):
        """Subscribe to all events (for logging/debugging)."""
        self._all_subscribers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    async def publish(self, event: Event):
        """Publish an event to the bus."""
        if not isinstance(event, Event):
            raise TypeError(f"Can only publish Event instances, got {type(event)}")

        await self._event_queue.put(event)
        logger.debug(f"Event published: {event.event_type.value} ({event.event_id})")

    async def _process_events(self):
        """Worker that processes events from the queue."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                await self._dispatch_event(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}")

    async def _dispatch_event(self, event: Event):
        """Dispatch event to all relevant subscribers."""
        # Deduplicate (at-least-once, but avoid double processing)
        if event.event_id in self._processed_events:
            logger.debug(f"Skipping duplicate event: {event.event_id}")
            return

        self._processed_events.add(event.event_id)

        # Trim cache if needed
        if len(self._processed_events) > self._max_processed_cache:
            # Remove oldest entries (simple approach)
            self._processed_events = set(list(self._processed_events)[-5000:])

        handlers = self._subscribers.get(event.event_type, []) + self._all_subscribers

        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Handler failed for {event.event_type.value}: {e}")
                # Retry once
                try:
                    result = handler(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as retry_error:
                    logger.error(f"Handler retry failed: {retry_error}")


# Global event bus instance
event_bus = EventBus()
