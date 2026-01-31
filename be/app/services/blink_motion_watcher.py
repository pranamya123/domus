"""
Blink Motion Watcher

Polls Blink for fridge camera motion events, deduplicates, and triggers inventory refreshes.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from shared.schemas.state import FridgeMotionState
from shared.schemas.storage import DomusStorage

from .blink_service import get_blink_service
from .fridge_inventory_service import FridgeInventoryService

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 10
REFRESH_COOLDOWN_SECONDS = 60


class BlinkMotionWatcher:
    """Background task that triggers fridge scans on motion."""

    def __init__(
        self,
        storage: DomusStorage,
        poll_interval: int = POLL_INTERVAL_SECONDS,
        cooldown_seconds: int = REFRESH_COOLDOWN_SECONDS,
    ):
        self._storage = storage
        self._blink_service = get_blink_service()
        self._fridge_service = FridgeInventoryService(storage)
        self._poll_interval = poll_interval
        self._cooldown_seconds = cooldown_seconds
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the motion watcher loop."""
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._run_loop())
        logger.info("Blink motion watcher started (interval=%s)", self._poll_interval)

    async def stop(self) -> None:
        """Cancel the running watcher loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Blink motion watcher stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Blink motion watcher loop error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        user_ids = self._blink_service.get_connected_user_ids()
        if not user_ids:
            logger.debug("Blink motion watcher: no connected users")
            return

        for user_id in user_ids:
            await self._handle_user(user_id)

    async def _handle_user(self, user_id: str) -> None:
        events = await self._blink_service.get_recent_motion_events(user_id)
        if not events:
            return

        now = datetime.utcnow()
        for event in events:
            camera_id = event.get("camera_id") or event.get("camera_name") or "unknown"
            camera_name = event.get("camera_name")
            event_ts = self._parse_event_timestamp(event.get("timestamp"))

            state = await self._storage.state.get_motion_state(user_id, camera_id)
            if state and state.cooldown_until and now < state.cooldown_until:
                logger.debug(
                    "Motion event skipped (cooldown) user=%s camera=%s until=%s",
                    user_id,
                    camera_name,
                    state.cooldown_until,
                )
                continue

            if state and state.last_motion_at and event_ts and event_ts <= state.last_motion_at:
                logger.debug(
                    "Motion event skipped (already processed) user=%s camera=%s timestamp=%s",
                    user_id,
                    camera_name,
                    event_ts,
                )
                continue

            logger.info(
                "Motion detected for user=%s camera=%s timestamp=%s",
                user_id,
                camera_name,
                event.get("timestamp"),
            )

            refresh = await self._fridge_service.refresh(user_id, camera_name=camera_name)
            success = refresh.get("success", False)
            new_state = FridgeMotionState(
                user_id=user_id,
                camera_id=camera_id,
                camera_name=camera_name,
                last_motion_at=event_ts or now,
                cooldown_until=now + timedelta(
                    seconds=self._cooldown_seconds if success else 15
                ),
            )
            await self._storage.state.save_motion_state(new_state)

            if not success:
                logger.warning(
                    "Motion-triggered refresh failed (user=%s camera=%s error=%s)",
                    user_id,
                    camera_name,
                    refresh.get("error"),
                )
                continue

            logger.info(
                "Motion-triggered inventory saved (user=%s camera=%s)",
                user_id,
                camera_name,
            )

    def _parse_event_timestamp(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        try:
            value = raw.strip()
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
