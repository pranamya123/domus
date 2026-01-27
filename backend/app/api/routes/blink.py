"""
Blink Camera API endpoints.

Handles:
- Blink account authentication
- 2FA verification
- Camera listing
- Manual snapshot capture
- Motion monitoring control
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.services.blink_service import blink_service

logger = logging.getLogger(__name__)

router = APIRouter()


class BlinkLoginRequest(BaseModel):
    """Blink login credentials."""
    email: str
    password: str


class Blink2FARequest(BaseModel):
    """Blink 2FA verification code."""
    code: str


class CaptureRequest(BaseModel):
    """Snapshot capture request."""
    camera_name: Optional[str] = None


class MonitoringRequest(BaseModel):
    """Motion monitoring configuration."""
    camera_name: Optional[str] = None
    interval: int = 30  # seconds between checks


@router.get("/status")
async def get_blink_status():
    """
    Get Blink connection status.

    Returns whether Blink is connected, list of cameras, etc.
    """
    status = await blink_service.get_status()
    return status


@router.post("/login")
async def login_to_blink(request: BlinkLoginRequest):
    """
    Login to Blink account.

    First step of authentication. May return '2fa_required' status
    if two-factor authentication is enabled.
    """
    result = await blink_service.initialize(
        email=request.email,
        password=request.password
    )

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/verify-2fa")
async def verify_2fa(request: Blink2FARequest):
    """
    Verify 2FA code sent to email/phone.

    Call this after login returns '2fa_required' status.
    """
    result = await blink_service.verify_2fa(request.code)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/reconnect")
async def reconnect_blink():
    """
    Reconnect using saved credentials.

    Use this to reconnect after server restart.
    """
    result = await blink_service.initialize()
    return result


@router.get("/cameras")
async def list_cameras():
    """
    List all available Blink cameras.

    Returns camera name, ID, battery level, temperature, etc.
    """
    status = await blink_service.get_status()

    if not status["initialized"]:
        raise HTTPException(
            status_code=400,
            detail="Blink not connected. Please login first."
        )

    return {"cameras": status["cameras"]}


@router.post("/capture")
async def capture_snapshot(request: CaptureRequest = None):
    """
    Manually capture a snapshot from the camera.

    Triggers image capture, sends to Gemini for analysis,
    and updates fridge inventory.
    """
    camera_name = request.camera_name if request else None
    result = await blink_service.capture_snapshot(camera_name)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/monitoring/start")
async def start_monitoring(request: MonitoringRequest = None):
    """
    Start automatic motion monitoring.

    When motion is detected (fridge door opens), automatically
    captures and analyzes the image.
    """
    status = await blink_service.get_status()

    if not status["initialized"]:
        raise HTTPException(
            status_code=400,
            detail="Blink not connected. Please login first."
        )

    camera_name = request.camera_name if request else None
    interval = request.interval if request else 30

    await blink_service.start_motion_monitoring(camera_name, interval)

    return {
        "status": "success",
        "message": f"Motion monitoring started (checking every {interval}s)"
    }


@router.post("/monitoring/stop")
async def stop_monitoring():
    """Stop automatic motion monitoring."""
    await blink_service.stop_motion_monitoring()

    return {
        "status": "success",
        "message": "Motion monitoring stopped"
    }


@router.post("/disconnect")
async def disconnect_blink():
    """
    Disconnect from Blink.

    Stops monitoring and clears session (credentials are still saved).
    """
    await blink_service.disconnect()

    return {
        "status": "success",
        "message": "Disconnected from Blink"
    }
