"""
Debounce/throttling utilities with server-side authority.

Server time is authoritative for all debounce logic.
Supports Redis or falls back to in-memory cache.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DebounceManager:
    """
    Manages debouncing for various operations.

    Uses in-memory cache (Phase 1). Redis-ready for Phase 2.
    Server time is authoritative.
    """

    def __init__(self):
        self._cache: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def should_accept(
        self,
        key: str,
        debounce_seconds: int,
    ) -> bool:
        """
        Check if an action should be accepted based on debounce rules.

        Args:
            key: Unique identifier for the action (e.g., "iot_image:{household_id}")
            debounce_seconds: Minimum seconds between accepted actions

        Returns:
            True if action should be accepted, False if within debounce window
        """
        now = datetime.now(timezone.utc)

        async with self._lock:
            last_accepted = self._cache.get(key)

            if last_accepted is None:
                self._cache[key] = now
                logger.debug(f"Debounce: First action for {key}, accepted")
                return True

            elapsed = (now - last_accepted).total_seconds()

            if elapsed >= debounce_seconds:
                self._cache[key] = now
                logger.debug(f"Debounce: {key} accepted after {elapsed:.1f}s")
                return True

            logger.debug(
                f"Debounce: {key} rejected, only {elapsed:.1f}s since last "
                f"(need {debounce_seconds}s)"
            )
            return False

    async def get_time_until_allowed(
        self,
        key: str,
        debounce_seconds: int,
    ) -> Optional[float]:
        """
        Get seconds until next action would be allowed.

        Returns None if action would be allowed now.
        """
        now = datetime.now(timezone.utc)

        async with self._lock:
            last_accepted = self._cache.get(key)

            if last_accepted is None:
                return None

            elapsed = (now - last_accepted).total_seconds()
            remaining = debounce_seconds - elapsed

            return remaining if remaining > 0 else None

    async def reset(self, key: str):
        """Reset debounce timer for a key."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]

    async def clear_all(self):
        """Clear all debounce timers."""
        async with self._lock:
            self._cache.clear()


# Global debounce manager instance
debounce_manager = DebounceManager()


# Convenience functions for specific debounce types
async def should_accept_iot_image(household_id: str) -> bool:
    """Check if IoT image should be accepted (15-minute debounce)."""
    key = f"iot_image:{household_id}"
    return await debounce_manager.should_accept(
        key,
        settings.iot_image_debounce_seconds
    )


async def should_send_expiry_notification(
    household_id: str,
    item_id: str
) -> bool:
    """Check if expiry notification should be sent (24-hour throttle per item)."""
    key = f"expiry_notification:{household_id}:{item_id}"
    return await debounce_manager.should_accept(
        key,
        settings.expiry_notification_throttle_seconds
    )
