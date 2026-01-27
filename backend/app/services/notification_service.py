"""
Notification Service - Handles notification routing and delivery.

Architecture per spec:
- Emission: Agents emit NotificationIntents
- Routing (Orchestrator): Applies user preferences, throttling, determines channels
- Delivery (This Service): In-App Inbox, Push (simulated), Alexa (simulated), Email (mocked)

Failure Handling:
- Failed deliveries are retried once
- Persistent failure degrades to in-app inbox only
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import get_settings
from app.core.debounce import should_send_expiry_notification
from app.core.event_bus import Event, EventType, event_bus
from app.models.notification import (
    DeliveryStatus,
    NotificationChannel,
    NotificationSeverity,
    NotificationType,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class NotificationService:
    """
    Notification service for routing and delivering notifications.

    Supports multiple channels with fallback to in-app inbox.
    """

    def __init__(self):
        self._pending_notifications: List[Dict[str, Any]] = []
        self._delivered_notifications: List[Dict[str, Any]] = []

    async def create_notification(
        self,
        user_id: Optional[str],
        household_id: str,
        notification_type: str,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        severity: str = "medium",
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create and route a notification.

        Applies throttling for expiry notifications.
        """
        notification_id = str(uuid4())

        # Apply throttling for expiry notifications
        if notification_type == NotificationType.PERISHABLE_EXPIRY.value:
            if source_id:
                should_send = await should_send_expiry_notification(
                    household_id, source_id
                )
                if not should_send:
                    logger.info(f"Notification throttled: {notification_type} for {source_id}")
                    return {
                        "status": "throttled",
                        "notification_id": notification_id,
                        "reason": "Max 1 expiry alert per item per 24h"
                    }

        notification = {
            "id": notification_id,
            "user_id": user_id,
            "household_id": household_id,
            "notification_type": notification_type,
            "severity": severity,
            "title": title,
            "message": message,
            "context": context,
            "source_type": source_type,
            "source_id": source_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "delivery_status": DeliveryStatus.PENDING.value,
            "channels_attempted": [],
            "channels_delivered": [],
        }

        # Determine delivery channels based on severity
        channels = self._determine_channels(severity, notification_type)

        # Attempt delivery to each channel
        for channel in channels:
            success = await self._deliver_to_channel(notification, channel)
            notification["channels_attempted"].append(channel)

            if success:
                notification["channels_delivered"].append(channel)

        # Update delivery status
        if notification["channels_delivered"]:
            notification["delivery_status"] = DeliveryStatus.DELIVERED.value
            notification["delivered_at"] = datetime.now(timezone.utc).isoformat()
        else:
            # Fallback to in-app only
            await self._deliver_to_channel(notification, NotificationChannel.IN_APP.value)
            notification["channels_delivered"].append(NotificationChannel.IN_APP.value)
            notification["delivery_status"] = DeliveryStatus.DELIVERED.value

        self._delivered_notifications.append(notification)

        # Publish event
        await event_bus.publish(Event(
            event_type=EventType.NOTIFICATION_CREATED,
            payload=notification,
            source="notification_service",
            household_id=household_id,
            user_id=user_id,
        ))

        logger.info(
            f"Notification created: {notification_id} ({notification_type}) "
            f"delivered via {notification['channels_delivered']}"
        )

        return notification

    def _determine_channels(
        self,
        severity: str,
        notification_type: str
    ) -> List[str]:
        """
        Determine delivery channels based on severity and type.

        In production, this would also check user preferences.
        """
        # Always include in-app
        channels = [NotificationChannel.IN_APP.value]

        if severity in [NotificationSeverity.HIGH.value, NotificationSeverity.URGENT.value]:
            channels.append(NotificationChannel.PUSH.value)

        if notification_type == NotificationType.HARDWARE_DISCONNECTED.value:
            channels.append(NotificationChannel.PUSH.value)

        # Alexa for urgent items
        if severity == NotificationSeverity.URGENT.value:
            channels.append(NotificationChannel.ALEXA.value)

        return list(set(channels))  # Remove duplicates

    async def _deliver_to_channel(
        self,
        notification: Dict[str, Any],
        channel: str,
    ) -> bool:
        """
        Deliver notification to a specific channel.

        Returns True if delivery succeeded.
        """
        try:
            if channel == NotificationChannel.IN_APP.value:
                return await self._deliver_in_app(notification)
            elif channel == NotificationChannel.PUSH.value:
                return await self._deliver_push(notification)
            elif channel == NotificationChannel.ALEXA.value:
                return await self._deliver_alexa(notification)
            elif channel == NotificationChannel.EMAIL.value:
                return await self._deliver_email(notification)
            else:
                logger.warning(f"Unknown channel: {channel}")
                return False
        except Exception as e:
            logger.error(f"Delivery failed for {channel}: {e}")

            # Retry once
            try:
                if channel == NotificationChannel.IN_APP.value:
                    return await self._deliver_in_app(notification)
                return False
            except Exception as retry_error:
                logger.error(f"Retry failed for {channel}: {retry_error}")
                return False

    async def _deliver_in_app(self, notification: Dict[str, Any]) -> bool:
        """Deliver to in-app inbox (stored in DB in production)."""
        # In Phase 1, we just store in memory
        # WebSocket would push to connected clients
        logger.debug(f"In-app notification: {notification['title']}")
        return True

    async def _deliver_push(self, notification: Dict[str, Any]) -> bool:
        """Deliver push notification (simulated via log file)."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "push_notification",
            "notification_id": notification["id"],
            "title": notification["title"],
            "message": notification["message"],
            "severity": notification["severity"],
        }

        # Write to notification log
        log_path = settings.notification_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        logger.debug(f"Push notification logged: {notification['title']}")
        return True

    async def _deliver_alexa(self, notification: Dict[str, Any]) -> bool:
        """Deliver Alexa notification (simulated via log file)."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "alexa_announcement",
            "notification_id": notification["id"],
            "ssml": f"<speak>{notification['title']}. {notification['message']}</speak>",
        }

        # Write to Alexa log
        log_path = settings.alexa_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        logger.debug(f"Alexa notification logged: {notification['title']}")
        return True

    async def _deliver_email(self, notification: Dict[str, Any]) -> bool:
        """Deliver email notification (mocked)."""
        logger.debug(f"Email notification (mocked): {notification['title']}")
        return True

    async def get_user_notifications(
        self,
        user_id: str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get notifications for a user."""
        notifications = [
            n for n in self._delivered_notifications
            if n.get("user_id") == user_id
        ]

        if unread_only:
            notifications = [n for n in notifications if not n.get("is_read")]

        # Sort by created_at descending
        notifications.sort(key=lambda x: x["created_at"], reverse=True)

        return notifications[:limit]

    async def get_household_notifications(
        self,
        household_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get notifications for a household."""
        notifications = [
            n for n in self._delivered_notifications
            if n.get("household_id") == household_id
        ]

        notifications.sort(key=lambda x: x["created_at"], reverse=True)
        return notifications[:limit]

    async def mark_as_read(
        self,
        notification_id: str,
        user_id: str,
    ) -> bool:
        """Mark a notification as read."""
        for notification in self._delivered_notifications:
            if notification["id"] == notification_id and notification.get("user_id") == user_id:
                notification["is_read"] = True
                notification["read_at"] = datetime.now(timezone.utc).isoformat()
                return True
        return False

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        count = 0
        now = datetime.now(timezone.utc).isoformat()

        for notification in self._delivered_notifications:
            if notification.get("user_id") == user_id and not notification.get("is_read"):
                notification["is_read"] = True
                notification["read_at"] = now
                count += 1

        return count


# Global notification service instance
notification_service = NotificationService()
