"""
Blink Camera Service - blinkpy Integration

Handles authentication and camera operations with Blink cameras.
Uses blinkpy to avoid REST login "app update required" errors.
"""

import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp
import certifi
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth, BlinkTwoFARequiredError

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


# Singleton instance
_blink_service: Optional[BlinkService] = None


def get_blink_service() -> BlinkService:
    """Get or create the singleton Blink service instance."""
    global _blink_service
    if _blink_service is None:
        _blink_service = BlinkService()
    return _blink_service
