"""
Blink Camera Service - blinkpy Integration

Handles authentication and camera operations with Blink cameras.
Uses blinkpy to avoid REST login "app update required" errors.
"""

import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

import aiohttp
import certifi
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth, BlinkTwoFARequiredError

import base64
from typing import Any
logger = logging.getLogger(__name__)


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
    """

    def __init__(self):
        self._sessions: dict[str, BlinkSession] = {}  # user_id -> session
        self._pending_auth: dict[str, BlinkSession] = {}  # user_id -> pending auth
        self._client_session: Optional[aiohttp.ClientSession] = None

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
        """
        Initiate Blink login. Returns account info and triggers 2FA if required.
        """
        try:
            session = await self._get_http_session()
            blink = Blink(session=session)
            auth = Auth({"username": email, "password": password}, session=session)
            blink.auth = auth

            try:
                await blink.start()
            except BlinkTwoFARequiredError:
                pending = BlinkSession(blink=blink, auth=auth, verified=False, email=email)
                self._pending_auth[user_id] = pending
                logger.info("Blink login requires 2FA for user %s", user_id)
                return {
                    "success": True,
                    "requires_2fa": True,
                    "message": "2FA code sent to your email/phone",
                }

            verified_session = BlinkSession(blink=blink, auth=auth, verified=True, email=email)
            self._sessions[user_id] = verified_session
            if user_id in self._pending_auth:
                del self._pending_auth[user_id]

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
        """
        Verify 2FA PIN code.
        """
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

    async def get_cameras(self, user_id: str) -> dict:
        """
        Get list of cameras for the user.
        """
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
                        "network_id": camera.network_id if hasattr(camera, "network_id") else None,
                        "status": camera.arm if hasattr(camera, "arm") else None,
                        "type": camera.camera_type if hasattr(camera, "camera_type") else None,
                    })

            return {"success": True, "cameras": cameras}

        except Exception as e:
            logger.error("Error fetching cameras for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    def disconnect(self, user_id: str) -> dict:
        """Disconnect Blink session for user."""
        if user_id in self._sessions:
            del self._sessions[user_id]
        if user_id in self._pending_auth:
            del self._pending_auth[user_id]
        logger.info("Blink disconnected for user %s", user_id)
        return {"success": True, "message": "Disconnected from Blink"}

    async def capture_camera_frame(self, user_id: str, camera_name: str | None = None) -> dict:
        """
        Capture a single still image from a Blink camera.

        Returns:
          {
            "success": True,
            "camera_id": "...",
            "camera_name": "...",
            "captured_at": "...",
            "image_bytes_b64": "..."
          }
        """
        session = self._sessions.get(user_id)
        if not session or not session.verified:
            return {"success": False, "error": "Not connected to Blink"}

        try:
            await session.blink.refresh()

            if not session.blink.cameras:
                return {"success": False, "error": "No cameras found"}

            # Choose camera
            cam = None
            if camera_name:
                cam = session.blink.cameras.get(camera_name)
                if cam is None:
                    return {"success": False, "error": f"Camera '{camera_name}' not found"}
            else:
                # Default: first camera in dict
                cam = next(iter(session.blink.cameras.values()))

            # Request a fresh snapshot if supported
            snap_fn = getattr(cam, "snap_picture", None)
            if callable(snap_fn):
                res = snap_fn()
                if hasattr(res, "__await__"):
                    await res

            # Refresh to load the new image
            await session.blink.refresh()

            # Try to extract image bytes (defensive across blinkpy versions)
            img_bytes: bytes | None = None

            # Some versions expose "image" or "image_data"
            for attr in ("image", "image_data", "thumbnail", "thumbnail_data"):
                val = getattr(cam, attr, None)
                if isinstance(val, (bytes, bytearray)) and len(val) > 0:
                    img_bytes = bytes(val)
                    break

            # Some versions have helpers
            if img_bytes is None:
                get_img = getattr(cam, "get_image", None)
                if callable(get_img):
                    res = get_img()
                    if hasattr(res, "__await__"):
                        res = await res
                    if isinstance(res, (bytes, bytearray)) and len(res) > 0:
                        img_bytes = bytes(res)

            if img_bytes is None:
                return {
                    "success": False,
                    "error": "Unable to fetch camera image bytes (blinkpy API mismatch). "
                             "Check camera object for image accessors."
                }

            return {
                "success": True,
                "camera_id": getattr(cam, "camera_id", None),
                "camera_name": getattr(cam, "name", camera_name) or camera_name or "default",
                "captured_at": datetime.utcnow().isoformat() + "Z",
                "image_bytes_b64": base64.b64encode(img_bytes).decode("utf-8"),
            }

        except Exception as e:
            logger.error("Error capturing camera frame for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}


    def get_connected_user_ids(self) -> list[str]:
        """Return all user IDs that currently have a verified Blink session."""
        return [
            user_id
            for user_id, session in self._sessions.items()
            if session.verified
        ]

    async def get_recent_motion_events(
        self, user_id: str, camera_name: str | None = None
    ) -> list[dict]:
        """
        Get recent motion events for the specified Blink user (and optional camera).

        Returns normalized event payloads. Defensive across blinkpy versions.
        """
        session = self._sessions.get(user_id)
        if not session or not session.verified:
            return []

        try:
            await session.blink.refresh()
        except Exception as e:
            logger.error("Failed to refresh Blink for motion events (user=%s): %s", user_id, e)
            return []

        cameras = []
        if camera_name:
            cam = session.blink.cameras.get(camera_name)
            if cam:
                cameras.append((camera_name, cam))
        else:
            cameras.extend(session.blink.cameras.items())

        events: list[dict] = []
        for name, cam in cameras:
            if not cam:
                continue

            timestamp = self._extract_motion_timestamp(cam)
            if not timestamp:
                continue

            camera_id = getattr(cam, "camera_id", None) or name
            events.append({
                "camera_id": camera_id,
                "camera_name": name,
                "timestamp": self._format_timestamp(timestamp),
                "type": "motion",
            })

        return events

    def _extract_motion_timestamp(self, camera: Any) -> Optional[datetime]:
        candidates = []
        motion_events = getattr(camera, "motion_events", None)
        if isinstance(motion_events, list) and motion_events:
            candidates.append(motion_events[0])

        attrs = [
            "last_motion",
            "last_motion_time",
            "last_event_time",
            "last_recording",
            "last_recording_time",
            "last_image_fetch",
        ]

        for attr in attrs:
            candidates.append(getattr(camera, attr, None))

        for raw in candidates:
            parsed = self._parse_motion_datetime(raw)
            if parsed:
                return parsed

        return None

    def _parse_motion_datetime(self, raw: Any) -> Optional[datetime]:
        if isinstance(raw, datetime):
            return raw

        if isinstance(raw, dict):
            for key in ("timestamp", "time", "date"):
                parsed = self._parse_motion_datetime(raw.get(key))
                if parsed:
                    return parsed
            return None

        if isinstance(raw, str):
            value = raw.strip()
            if not value:
                return None
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
        return None

    def _format_timestamp(self, timestamp: Optional[datetime]) -> str:
        ts = timestamp or datetime.utcnow()
        if ts.tzinfo:
            ts = ts.astimezone()
        return ts.replace(microsecond=0).isoformat() + "Z"



# Singleton instance
_blink_service: Optional[BlinkService] = None


def get_blink_service() -> BlinkService:
    """Get or create the singleton Blink service instance."""
    global _blink_service
    if _blink_service is None:
        _blink_service = BlinkService()
    return _blink_service
