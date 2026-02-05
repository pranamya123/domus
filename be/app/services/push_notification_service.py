"""
Push Notification Service - FCM/APNs for iOS Push Notifications

Demo-safe backend support for sending iOS push notifications via FCM.
- Uses FCM HTTP v1 API
- Sends notification body EXACTLY as stored
- Includes notification_id in payload for deep linking
- Supports hardcoded demo device token (from environment variable)

For production, you would:
1. Store device tokens per user in the database
2. Use proper service account authentication
3. Handle token refresh and invalidation
"""

import os
import logging
import httpx
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PushNotificationResult:
    """Result of sending a push notification."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class PushNotificationService:
    """
    FCM-based push notification service for iOS.

    For demo purposes, uses a hardcoded device token from environment.
    In production, tokens would be stored per-user in the database.
    """

    def __init__(self):
        # FCM configuration
        self.fcm_server_key = os.getenv("FCM_SERVER_KEY", "")
        self.fcm_project_id = os.getenv("FCM_PROJECT_ID", "domus-app")

        # Demo: Single hardcoded device token for testing
        # Set this from the iOS app console logs during registration
        self.demo_device_token = os.getenv("DEMO_DEVICE_TOKEN", "")

        # FCM endpoints
        self.fcm_send_url = f"https://fcm.googleapis.com/v1/projects/{self.fcm_project_id}/messages:send"
        self.fcm_legacy_url = "https://fcm.googleapis.com/fcm/send"

        # Track if service is configured
        self._is_configured = bool(self.fcm_server_key and self.demo_device_token)

        if self._is_configured:
            logger.info("PushNotificationService initialized with FCM")
        else:
            logger.warning(
                "PushNotificationService not fully configured. "
                "Set FCM_SERVER_KEY and DEMO_DEVICE_TOKEN environment variables."
            )

    @property
    def is_configured(self) -> bool:
        """Check if push notifications are properly configured."""
        return self._is_configured

    def set_demo_token(self, token: str) -> None:
        """
        Set the demo device token at runtime.

        Useful for setting the token from the iOS app logs without restart.
        """
        self.demo_device_token = token
        self._is_configured = bool(self.fcm_server_key and self.demo_device_token)
        logger.info("Demo device token updated")

    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        notification_id: Optional[str] = None,
        deep_link_url: Optional[str] = None,
    ) -> PushNotificationResult:
        """
        Send a push notification to a user's device.

        For demo, always uses the hardcoded demo device token.
        In production, would look up user's registered device tokens.

        Args:
            user_id: User ID (for logging, not used for token lookup in demo)
            title: Notification title
            body: Notification body (EXACT text to show)
            notification_id: ID for deep linking when notification is tapped
            deep_link_url: Optional deep link URL (defaults to domus://chat?notification_id=X)

        Returns:
            PushNotificationResult with success status and any error
        """
        if not self._is_configured:
            logger.warning("Push notifications not configured, skipping send")
            return PushNotificationResult(
                success=False,
                error="Push notifications not configured"
            )

        # Build deep link URL for notification tap
        if not deep_link_url and notification_id:
            deep_link_url = f"domus://chat?notification_id={notification_id}"

        # Build FCM message payload
        message = {
            "to": self.demo_device_token,
            "notification": {
                "title": title,
                "body": body,
                "sound": "default",
                "badge": 1,
            },
            "data": {
                "notification_id": notification_id or "",
                "deep_link": deep_link_url or "",
                "user_id": user_id,
            },
            # iOS specific configuration
            "apns": {
                "payload": {
                    "aps": {
                        "alert": {
                            "title": title,
                            "body": body,
                        },
                        "sound": "default",
                        "badge": 1,
                        "mutable-content": 1,
                    }
                },
                "fcm_options": {
                    "link": deep_link_url,
                }
            }
        }

        logger.info("Sending push notification to user %s: %s", user_id, title)
        logger.debug("FCM payload: %s", message)

        try:
            # Use legacy FCM API (simpler for demo, uses server key)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.fcm_legacy_url,
                    json=message,
                    headers={
                        "Authorization": f"key={self.fcm_server_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    result_data = response.json()
                    if result_data.get("success") == 1:
                        message_id = result_data.get("results", [{}])[0].get("message_id")
                        logger.info("Push notification sent successfully: %s", message_id)
                        return PushNotificationResult(
                            success=True,
                            message_id=message_id
                        )
                    else:
                        error = result_data.get("results", [{}])[0].get("error", "Unknown error")
                        logger.error("FCM returned error: %s", error)
                        return PushNotificationResult(
                            success=False,
                            error=error
                        )
                else:
                    logger.error("FCM request failed: %d %s", response.status_code, response.text)
                    return PushNotificationResult(
                        success=False,
                        error=f"HTTP {response.status_code}: {response.text}"
                    )

        except httpx.TimeoutException:
            logger.error("FCM request timed out")
            return PushNotificationResult(
                success=False,
                error="Request timed out"
            )
        except Exception as e:
            logger.error("Failed to send push notification: %s", e)
            return PushNotificationResult(
                success=False,
                error=str(e)
            )

    async def send_notification_with_payload(
        self,
        user_id: str,
        notification_record: dict,
    ) -> PushNotificationResult:
        """
        Send a push notification using a stored NotificationRecord.

        Convenience method that extracts title, body, and notification_id
        from the record and ensures EXACT text is sent.

        Args:
            user_id: User ID
            notification_record: Dict with title, body, notification_id

        Returns:
            PushNotificationResult
        """
        return await self.send_notification(
            user_id=user_id,
            title=notification_record.get("title", "domus"),
            body=notification_record.get("body", ""),
            notification_id=notification_record.get("notification_id"),
        )


# =============================================================================
# Singleton Instance
# =============================================================================

_push_service: Optional[PushNotificationService] = None


def get_push_notification_service() -> PushNotificationService:
    """Get or create the singleton PushNotificationService instance."""
    global _push_service
    if _push_service is None:
        _push_service = PushNotificationService()
    return _push_service
