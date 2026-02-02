"""
Blink Camera Service - blinkpy Integration

Handles authentication and camera operations with Blink cameras.
Uses blinkpy to avoid REST login "app update required" errors.
"""

import hashlib
import logging
import ssl
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

import aiohttp
import certifi
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth, BlinkTwoFARequiredError

logger = logging.getLogger(__name__)

# Hardcoded camera name
CAMERA_NAME = "Outdoor 4 - KLHX"


@dataclass
class BlinkSession:
    """Stores Blink authentication session data."""
    blink: Blink
    auth: Auth
    verified: bool = False
    email: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


class BlinkService:
    """
    Blink Camera API Service (via blinkpy).

    Handles:
    - Authentication (login + 2FA)
    - Camera listing
    - Fetching latest media (thumbnail + video) from Blink cloud
    """

    def __init__(self):
        self._sessions: dict[str, BlinkSession] = {}
        self._pending_auth: dict[str, BlinkSession] = {}
        self._client_session: Optional[aiohttp.ClientSession] = None
        self._media_dir = Path(__file__).resolve().parent.parent / "storage" / "media"
        # Track last thumbnail hash to detect changes
        self._last_thumbnail_hash: dict[str, str] = {}

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context using certifi certificates."""
        return ssl.create_default_context(cafile=certifi.where())

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create shared aiohttp session with proper SSL."""
        if self._client_session is None or self._client_session.closed:
            ssl_context = self._create_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._client_session = aiohttp.ClientSession(connector=connector)
        return self._client_session

    async def login(self, user_id: str, email: str, password: str) -> dict:
        """Login to Blink with email and password."""
        try:
            session = await self._get_http_session()
            blink = Blink(session=session)
            auth = Auth({"username": email, "password": password}, session=session)

            blink.auth = auth
            blink.auth.no_save = True

            try:
                await blink.start()
            except BlinkTwoFARequiredError:
                pending = BlinkSession(
                    blink=blink,
                    auth=blink.auth,
                    verified=False,
                    email=email,
                )
                self._pending_auth[user_id] = pending
                logger.info("Blink login requires 2FA for user %s", user_id)
                return {
                    "success": True,
                    "requires_2fa": True,
                    "message": "2FA code sent to your email/phone",
                }

            verified_session = BlinkSession(
                blink=blink,
                auth=blink.auth,
                verified=True,
                email=email,
            )
            self._sessions[user_id] = verified_session
            await self._ensure_camera_armed(blink, CAMERA_NAME)

            logger.info("Blink login successful for user %s (no 2FA)", user_id)
            return {
                "success": True,
                "requires_2fa": False,
                "message": "Login successful",
            }

        except Exception as e:
            logger.error("Blink login exception for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def verify_2fa(self, user_id: str, pin: str) -> dict:
        """Verify 2FA PIN code."""
        pending = self._pending_auth.get(user_id)
        if not pending:
            return {"success": False, "error": "No pending authentication. Please login again."}

        try:
            success = await pending.auth.complete_2fa_login(pin)
            if not success:
                return {"success": False, "error": "Invalid or expired PIN code"}

            pending.blink.setup_urls()
            await pending.blink.setup_post_verify()

            pending.verified = True
            self._sessions[user_id] = pending
            del self._pending_auth[user_id]
            await self._ensure_camera_armed(pending.blink, CAMERA_NAME)

            logger.info("Blink 2FA verified for user %s", user_id)
            return {"success": True, "message": "Blink camera connected successfully"}

        except Exception as e:
            logger.error("Blink 2FA verification error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    def is_connected(self, user_id: str) -> bool:
        """Check if user has a verified Blink session."""
        session = self._sessions.get(user_id)
        return session is not None and session.verified

    def get_session(self, user_id: str) -> Optional[BlinkSession]:
        """Get user's Blink session if connected."""
        return self._sessions.get(user_id)

    def get_connected_user_ids(self) -> list[str]:
        """Return all user IDs that currently have a verified Blink session."""
        return [uid for uid, s in self._sessions.items() if s.verified]

    async def get_cameras(self, user_id: str) -> dict:
        """Get list of cameras for the user."""
        session = self._sessions.get(user_id)
        if not session or not session.verified:
            return {"success": False, "error": "Not connected to Blink"}

        try:
            await session.blink.refresh()
            cameras = []
            if session.blink.cameras:
                for name, camera in session.blink.cameras.items():
                    cameras.append({
                        "id": camera.camera_id,
                        "name": name,
                        "network_id": getattr(camera, "network_id", None),
                        "status": getattr(camera, "arm", None),
                        "type": getattr(camera, "camera_type", None),
                    })
            return {"success": True, "cameras": cameras}

        except Exception as e:
            logger.error("Error fetching cameras for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    def disconnect(self, user_id: str) -> dict:
        """Disconnect Blink session for user."""
        self._sessions.pop(user_id, None)
        self._pending_auth.pop(user_id, None)
        self._last_thumbnail_hash.pop(user_id, None)
        logger.info("Blink disconnected for user %s", user_id)
        return {"success": True, "message": "Disconnected from Blink"}

    async def _ensure_camera_armed(self, blink: Any, camera_name: str) -> None:
        """Ensure camera is armed for motion detection."""
        try:
            cam = blink.cameras.get(camera_name) if getattr(blink, "cameras", None) else None
            if not cam:
                logger.info("Blink arm skipped (camera not found) camera=%s", camera_name)
                return
            arm_fn = getattr(cam, "async_arm", None)
            if callable(arm_fn):
                await arm_fn(True)
                logger.info("Camera armed for motion detection (camera=%s)", camera_name)
        except Exception as exc:
            logger.warning("Blink arm failed (camera=%s): %s", camera_name, exc)

    async def sync_latest_media(self, user_id: str, camera_name: str = CAMERA_NAME, force_video: bool = False) -> dict:
        """
        Fetch the latest thumbnail and video from Blink.

        1. Refresh to get latest thumbnail from cache
        2. If thumbnail changed (or force_video=True), download latest video from cloud
        3. Save both to storage/media/

        Args:
            user_id: User ID
            camera_name: Camera name
            force_video: If True, always download video (use on connect)

        Returns:
            dict with success status, paths, and whether thumbnail changed
        """
        session = self._sessions.get(user_id)
        if not session or not session.verified:
            return {"success": False, "error": "Not connected to Blink"}

        try:
            self._media_dir.mkdir(parents=True, exist_ok=True)
            thumbnail_path = self._media_dir / "latest_thumbnail.jpg"
            video_path = self._media_dir / "latest_clip.mp4"

            # Step 1: Refresh to get latest thumbnail
            logger.info("Refreshing Blink (user=%s camera=%s)", user_id, camera_name)
            await session.blink.refresh(force=True)

            cam = session.blink.cameras.get(camera_name)
            if cam is None:
                return {"success": False, "error": f"Camera '{camera_name}' not found"}

            # Step 2: Get and save thumbnail
            image_bytes = getattr(cam, "image_from_cache", None)
            thumbnail_changed = False

            if isinstance(image_bytes, (bytes, bytearray)) and len(image_bytes) > 0:
                # Check if thumbnail changed
                new_hash = hashlib.md5(image_bytes).hexdigest()
                old_hash = self._last_thumbnail_hash.get(user_id)

                if new_hash != old_hash:
                    thumbnail_changed = True
                    self._last_thumbnail_hash[user_id] = new_hash
                    logger.info("Thumbnail changed (user=%s old=%s new=%s)", user_id, old_hash, new_hash)

                thumbnail_path.write_bytes(image_bytes)
                logger.info("Saved thumbnail (%d bytes) to %s", len(image_bytes), thumbnail_path)
            else:
                logger.warning("No thumbnail in cache for camera=%s", camera_name)

            # Step 3: Download video if thumbnail changed or forced
            video_downloaded = False
            if force_video or thumbnail_changed:
                logger.info("Downloading latest video from cloud (user=%s force=%s changed=%s)",
                           user_id, force_video, thumbnail_changed)
                video_downloaded = await self._download_latest_video(session.blink, camera_name, video_path)

            return {
                "success": True,
                "thumbnail_path": str(thumbnail_path) if thumbnail_path.exists() else None,
                "video_path": str(video_path) if video_path.exists() else None,
                "thumbnail_changed": thumbnail_changed,
                "video_downloaded": video_downloaded,
                "camera_name": camera_name,
            }

        except Exception as e:
            logger.error("Error syncing media for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def _download_latest_video(self, blink: Blink, camera_name: str, video_path: Path) -> bool:
        """
        Download the latest video clip from Blink cloud.

        Returns True if video was downloaded successfully.
        """
        try:
            # Create temp directory for download
            temp_dir = self._media_dir / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Clean up any existing temp files first
            for f in temp_dir.glob("*.mp4"):
                try:
                    f.unlink()
                except Exception:
                    pass

            # Use download_videos to fetch from cloud
            download_fn = getattr(blink, "download_videos", None)
            if callable(download_fn):
                logger.info("Calling download_videos (camera=%s path=%s)", camera_name, temp_dir)
                result = download_fn(str(temp_dir), camera=camera_name, stop=1, delay=1)
                if hasattr(result, "__await__"):
                    await result

                # Find downloaded mp4 files
                mp4_files = sorted(temp_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)

                if mp4_files:
                    latest = mp4_files[0]
                    file_size = latest.stat().st_size

                    # Move to final location
                    if video_path.exists():
                        video_path.unlink()
                    latest.rename(video_path)
                    logger.info("✅ Saved video (%d bytes) to %s", file_size, video_path)

                    # Clean up other temp files
                    for f in temp_dir.glob("*.mp4"):
                        try:
                            f.unlink()
                        except Exception:
                            pass

                    return True
                else:
                    logger.warning("No video files downloaded from cloud (Blink may still be uploading)")

            # Fallback: try video_from_cache (usually won't have latest)
            cam = blink.cameras.get(camera_name)
            if cam:
                video_bytes = getattr(cam, "video_from_cache", None)
                if isinstance(video_bytes, (bytes, bytearray)) and len(video_bytes) > 0:
                    video_path.write_bytes(video_bytes)
                    logger.info("✅ Saved video from cache (%d bytes) to %s", len(video_bytes), video_path)
                    return True

            return False

        except Exception as e:
            logger.error("Error downloading video: %s", e)
            return False


# Singleton instance
_blink_service: Optional[BlinkService] = None


def get_blink_service() -> BlinkService:
    """Get or create the singleton Blink service instance."""
    global _blink_service
    if _blink_service is None:
        _blink_service = BlinkService()
    return _blink_service
