"""
Blink Motion Watcher

Periodically syncs latest media from Blink camera cache.
Detects motion by comparing thumbnail hashes and downloads video when motion is detected.
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

from shared.schemas.storage import DomusStorage
from .blink_service import get_blink_service, CAMERA_NAME

logger = logging.getLogger(__name__)

# Poll interval range (seconds)
POLL_MIN_SECONDS = 60
POLL_MAX_SECONDS = 90


class BlinkMotionWatcher:
    """
    Background task that periodically syncs latest media from Blink.

    Behavior:
    - On connect: Downloads latest video + thumbnail (force_video=True in routes.py)
    - On poll: Refreshes thumbnail, if changed → downloads latest video
    - Always maintains latest_thumbnail.jpg and latest_clip.mp4 in storage/media/
    """

    def __init__(self, storage: DomusStorage):
        self._storage = storage
        self._blink_service = get_blink_service()
        self._task: Optional[asyncio.Task] = None
        # Track last motion detection time per user
        self._last_motion: dict[str, datetime] = {}

    async def start(self) -> None:
        """Start the watcher loop."""
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._run_loop())
        logger.info("Blink watcher started (poll_interval=%d-%ds)", POLL_MIN_SECONDS, POLL_MAX_SECONDS)

    async def stop(self) -> None:
        """Stop the watcher loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Blink watcher stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Blink watcher error: %s", exc)

            # Random sleep between polls
            sleep_time = random.randint(POLL_MIN_SECONDS, POLL_MAX_SECONDS)
            await asyncio.sleep(sleep_time)

    async def _poll_once(self) -> None:
        user_ids = self._blink_service.get_connected_user_ids()
        if not user_ids:
            logger.debug("Blink watcher: no connected users")
            return

        logger.debug("Blink watcher poll: users=%s", user_ids)

        for user_id in user_ids:
            # sync_latest_media handles:
            # - Refreshing thumbnail from Blink cache
            # - Detecting if thumbnail changed (hash comparison)
            # - Downloading video ONLY if thumbnail changed
            result = await self._blink_service.sync_latest_media(user_id, CAMERA_NAME)

            if not result.get("success"):
                logger.warning(
                    "Blink media sync failed (user=%s error=%s)",
                    user_id,
                    result.get("error"),
                )
                continue

            # Check if motion was detected (thumbnail changed)
            if result.get("thumbnail_changed"):
                self._last_motion[user_id] = datetime.utcnow()
                logger.info(
                    "🎬 MOTION DETECTED (user=%s) - thumbnail changed, video downloaded=%s",
                    user_id,
                    result.get("video_downloaded"),
                )

                # If video wasn't downloaded (Blink may still be uploading), retry after delay
                if not result.get("video_downloaded"):
                    logger.info("Video not ready, scheduling retry in 30s (user=%s)", user_id)
                    asyncio.create_task(self._retry_video_download(user_id, CAMERA_NAME))
            else:
                logger.debug(
                    "Blink poll complete (user=%s) - no motion detected",
                    user_id,
                )

    async def _retry_video_download(self, user_id: str, camera_name: str, max_retries: int = 3) -> None:
        """
        Retry downloading video after motion detection.

        Blink takes 30-60s to upload clips after motion, so we retry a few times.
        """
        for attempt in range(1, max_retries + 1):
            await asyncio.sleep(30)  # Wait 30s between retries

            logger.info("Retrying video download (user=%s attempt=%d/%d)", user_id, attempt, max_retries)

            result = await self._blink_service.sync_latest_media(
                user_id, camera_name, force_video=True
            )

            if result.get("video_downloaded"):
                logger.info(
                    "✅ Video download succeeded on retry (user=%s attempt=%d)",
                    user_id,
                    attempt,
                )
                return

            logger.warning(
                "Video download retry failed (user=%s attempt=%d/%d)",
                user_id,
                attempt,
                max_retries,
            )

        logger.error("Video download failed after %d retries (user=%s)", max_retries, user_id)
