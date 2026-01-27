"""
Blink Camera Integration Service.

Connects to Blink cameras to capture fridge images when motion is detected.
Supports Blink Outdoor, Indoor, and Mini cameras.
"""

import asyncio
import logging
import json
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import aiofiles
import aiohttp
import certifi
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.helpers.util import json_load

from app.config import get_settings
from app.services.vision_service import vision_service
from app.agents.domus_orchestrator import orchestrator

logger = logging.getLogger(__name__)
settings = get_settings()


class BlinkCameraService:
    """
    Manages Blink camera integration for fridge monitoring.

    Features:
    - Authenticate with Blink cloud
    - Monitor motion events
    - Capture snapshots on demand
    - Auto-process images through Gemini
    """

    def __init__(self):
        self.blink: Optional[Blink] = None
        self.auth: Optional[Auth] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        self._monitoring = False
        self._credentials_file = Path(settings.data_path) / "blink_credentials.json"
        self._last_motion_check: Dict[str, datetime] = {}
        self._household_id = "anonymous_household"  # Default, can be set per user

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context using certifi certificates."""
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        return ssl_context

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proper SSL."""
        if self._session is None or self._session.closed:
            ssl_context = self._create_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def initialize(self, email: str = None, password: str = None) -> Dict[str, Any]:
        """
        Initialize Blink connection.

        First time: requires email/password, will prompt for 2FA
        Subsequent: uses saved credentials
        """
        if self._initialized and self.blink:
            return {"status": "already_initialized", "cameras": self._get_camera_list()}

        # Get session with proper SSL context
        session = await self._get_session()
        self.blink = Blink(session=session)

        # Check for saved credentials
        if self._credentials_file.exists() and not email:
            try:
                self.auth = Auth(await json_load(self._credentials_file), session=session)
                self.blink.auth = self.auth
                await self.blink.start()
                self._initialized = True

                # Auto-start motion monitoring
                await self.start_motion_monitoring()

                logger.info("Blink initialized from saved credentials - auto-monitoring started")
                return {
                    "status": "success",
                    "message": "Connected to Blink. Auto-monitoring started.",
                    "cameras": self._get_camera_list()
                }
            except Exception as e:
                logger.warning(f"Failed to use saved credentials: {e}")
                # Continue to fresh login

        # Fresh login required
        if not email or not password:
            return {
                "status": "credentials_required",
                "message": "Please provide Blink email and password"
            }

        try:
            self.auth = Auth({"username": email, "password": password}, session=session)
            self.blink.auth = self.auth

            try:
                await self.blink.start()
            except BlinkTwoFARequiredError:
                # 2FA is required - Blink will send a code to user's email/phone
                logger.info("Blink 2FA required")
                return {
                    "status": "2fa_required",
                    "message": "Check your email/phone for Blink verification code"
                }

            # Save credentials for future use
            await self._save_credentials()
            self._initialized = True

            logger.info("Blink initialized successfully")
            return {
                "status": "success",
                "message": "Connected to Blink",
                "cameras": self._get_camera_list()
            }

        except BlinkTwoFARequiredError:
            # 2FA required (caught at outer level)
            logger.info("Blink 2FA required")
            return {
                "status": "2fa_required",
                "message": "Check your email/phone for Blink verification code"
            }
        except Exception as e:
            logger.error(f"Blink initialization failed: {e}")
            return {
                "status": "error",
                "message": str(e) if str(e) else "Login failed - please check your credentials"
            }

    async def verify_2fa(self, code: str) -> Dict[str, Any]:
        """Verify 2FA code from Blink."""
        if not self.auth:
            return {"status": "error", "message": "Not initialized. Call initialize first."}
        if not self.blink:
            return {"status": "error", "message": "Blink not initialized. Call initialize first."}

        try:
            # Use the new OAuth 2FA completion method
            success = await self.auth.complete_2fa_login(code)

            if not success:
                return {
                    "status": "error",
                    "message": "2FA verification failed. Please try again."
                }

            # Set up URLs (needed before setup_post_verify)
            self.blink.setup_urls()

            # Complete Blink setup after 2FA
            await self.blink.setup_post_verify()

            # Save credentials after successful 2FA
            await self._save_credentials()
            self._initialized = True

            # Auto-start motion monitoring
            await self.start_motion_monitoring()

            logger.info("Blink 2FA verified successfully - auto-monitoring started")
            return {
                "status": "success",
                "message": "2FA verified. Connected to Blink! Auto-monitoring started.",
                "cameras": self._get_camera_list()
            }
        except Exception as e:
            logger.error(f"2FA verification failed: {e}")
            return {
                "status": "error",
                "message": f"2FA verification failed: {e}"
            }

    async def _save_credentials(self):
        """Save Blink credentials for future use."""
        try:
            self._credentials_file.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self._credentials_file, "w") as f:
                await f.write(json.dumps(self.auth.login_attributes))
            logger.info("Blink credentials saved")
        except Exception as e:
            logger.warning(f"Failed to save credentials: {e}")

    def _get_camera_list(self) -> list:
        """Get list of available cameras."""
        if not self.blink or not self.blink.cameras:
            return []

        cameras = []
        for name, camera in self.blink.cameras.items():
            cameras.append({
                "name": name,
                "id": camera.camera_id,
                "type": camera.camera_type,
                "armed": camera.arm,
                "battery": camera.battery,
                "temperature": camera.temperature,
                "last_motion": camera.last_motion if hasattr(camera, 'last_motion') else None
            })
        return cameras

    async def capture_snapshot(self, camera_name: str = None) -> Dict[str, Any]:
        """
        Capture a snapshot from the specified camera (or first available).

        Returns the image path and triggers analysis.
        """
        if not self._initialized or not self.blink:
            return {"status": "error", "message": "Blink not initialized"}

        try:
            # Refresh to get latest state
            await self.blink.refresh()

            # Get camera
            if camera_name and camera_name in self.blink.cameras:
                camera = self.blink.cameras[camera_name]
            else:
                # Use first camera
                camera = list(self.blink.cameras.values())[0] if self.blink.cameras else None

            if not camera:
                return {"status": "error", "message": "No camera found"}

            # Request new snapshot
            await camera.snap_picture()
            await asyncio.sleep(2)  # Wait for snapshot to be ready
            await self.blink.refresh()

            # Save snapshot locally
            image_id = str(uuid4())
            image_dir = settings.image_storage_path / self._household_id
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / f"blink_{image_id}.jpg"

            await camera.image_to_file(str(image_path))

            logger.info(f"Snapshot captured: {image_path}")

            # Analyze with Gemini
            analysis_result = await self._analyze_image(str(image_path))

            return {
                "status": "success",
                "message": "Snapshot captured and analyzed",
                "image_id": image_id,
                "image_path": str(image_path),
                "camera": camera.name,
                "analysis": analysis_result
            }

        except Exception as e:
            logger.error(f"Snapshot capture failed: {e}")
            return {"status": "error", "message": str(e)}

    async def _analyze_image(self, image_path: str) -> Dict[str, Any]:
        """Analyze captured image with Gemini."""
        try:
            # Validate it's a fridge image
            is_valid, validation = await vision_service.validate_fridge_image(image_path)

            if not is_valid:
                logger.warning("Captured image doesn't appear to be a fridge")
                return {
                    "success": False,
                    "message": "Image doesn't appear to show fridge contents",
                    "validation": validation
                }

            # Analyze the image
            analysis = await vision_service.analyze_fridge_image(
                image_path,
                self._household_id
            )

            # Process through orchestrator to update fridge state
            await orchestrator.process({
                "action": "process_image",
                "image_analysis": analysis,
                "image_path": image_path,  # TODO: Remove - debugging only
                "household_id": self._household_id,
                "source": "blink_camera"
            })

            # Add image path to analysis result
            analysis["image_path"] = image_path  # TODO: Remove - debugging only
            return analysis

        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return {"success": False, "error": str(e)}

    async def start_motion_monitoring(self, camera_name: str = None, interval: int = 30):
        """
        Start monitoring for motion events.

        When motion is detected (door opens), capture and analyze.
        """
        if not self._initialized:
            logger.warning("Cannot start monitoring - Blink not initialized")
            return

        if self._monitoring:
            logger.info("Motion monitoring already running")
            return

        # Arm the system to enable motion detection
        try:
            for sync_name, sync_module in self.blink.sync.items():
                if not sync_module.arm:
                    logger.info(f"Arming sync module: {sync_name}")
                    await sync_module.async_arm(True)
            await self.blink.refresh()
            logger.info("Blink system armed for motion detection")
        except Exception as e:
            logger.warning(f"Failed to arm system: {e}")

        self._monitoring = True
        logger.info(f"Starting motion monitoring (interval: {interval}s)")

        asyncio.create_task(self._motion_monitor_loop(camera_name, interval))

    async def _motion_monitor_loop(self, camera_name: str, interval: int):
        """Background loop to check for motion events."""
        while self._monitoring:
            try:
                await self.blink.refresh()

                for name, camera in self.blink.cameras.items():
                    if camera_name and name != camera_name:
                        continue

                    # Log motion status for debugging
                    motion_status = getattr(camera, 'motion_detected', None)
                    logger.debug(f"Camera {name}: motion_detected={motion_status}, armed={camera.arm}")

                    # Check if motion was detected
                    if camera.motion_detected:
                        last_check = self._last_motion_check.get(name)
                        now = datetime.now(timezone.utc)

                        # Debounce: only process if no recent motion (15 min)
                        if not last_check or (now - last_check).seconds > 900:
                            logger.info(f"Motion detected on {name} - capturing snapshot")
                            self._last_motion_check[name] = now

                            # Capture and analyze
                            result = await self.capture_snapshot(name)

                            if result.get("status") == "success":
                                # Send notification about new scan
                                from app.services.notification_service import notification_service
                                await notification_service.create_notification(
                                    user_id=None,
                                    household_id=self._household_id,
                                    notification_type="fridge_scan",
                                    title="Fridge Scanned",
                                    message=f"Detected {len(result.get('analysis', {}).get('items', []))} items",
                                    severity="low"
                                )

            except Exception as e:
                logger.error(f"Motion monitoring error: {e}")

            await asyncio.sleep(interval)

    async def stop_motion_monitoring(self):
        """Stop motion monitoring."""
        self._monitoring = False
        logger.info("Motion monitoring stopped")

    async def get_status(self) -> Dict[str, Any]:
        """Get current Blink connection status."""
        return {
            "initialized": self._initialized,
            "monitoring": self._monitoring,
            "cameras": self._get_camera_list() if self._initialized else [],
            "credentials_saved": self._credentials_file.exists()
        }

    async def disconnect(self):
        """Disconnect from Blink."""
        self._monitoring = False
        self._initialized = False
        self.blink = None
        self.auth = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        logger.info("Blink disconnected")


# Global instance
blink_service = BlinkCameraService()
