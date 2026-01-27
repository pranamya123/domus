"""
IoT device endpoints for fridge camera integration.

IoT Camera Assumptions:
- Status: Hardware not installed; simulated via /api/ingest/iot
- Triggers: Door Open + Light On
- Debounce (Server-Side Authority): Ignore images within 15 minutes of last accepted
- Security: IoT ingestion endpoint requires device token (mocked)
"""

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.domus_orchestrator import orchestrator
from app.config import get_settings
from app.core.database import get_db
from app.core.debounce import should_accept_iot_image
from app.core.security import verify_device_token
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.fridge_state import FridgeImage, FridgeState, ImageSource, ImageStatus
from app.services.vision_service import vision_service

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


class IoTImageResponse(BaseModel):
    """Response for IoT image ingestion."""
    status: str
    message: str
    image_id: Optional[str] = None
    debounced: bool = False


class DeviceStatusResponse(BaseModel):
    """Device status response."""
    device_id: str
    device_type: str
    status: str
    last_seen: Optional[str] = None
    is_simulated: bool = True


class DeviceRegistrationRequest(BaseModel):
    """Request to register a new device."""
    household_id: str
    device_type: str = DeviceType.FRIDGE_CAMERA.value
    name: str = "Fridge Camera"


@router.post("/iot", response_model=IoTImageResponse)
async def ingest_iot_image(
    household_id: str,
    file: UploadFile = File(...),
    x_device_token: str = Header(..., alias="X-Device-Token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest image from IoT fridge camera.

    Requires device token authentication.
    Subject to server-side debouncing (15 minute minimum between images).
    """
    # Verify device token
    if not verify_device_token(x_device_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid device token"
        )

    # Check debounce - server time is authoritative
    should_accept = await should_accept_iot_image(household_id)

    if not should_accept:
        logger.info(f"IoT image debounced for household {household_id}")
        return IoTImageResponse(
            status="debounced",
            message="Image ignored - within 15-minute debounce window",
            debounced=True,
        )

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an image"
        )

    # Save image
    image_id = str(uuid4())
    file_extension = Path(file.filename or "image.jpg").suffix or ".jpg"
    file_path = settings.image_storage_path / household_id / f"iot_{image_id}{file_extension}"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save IoT image: {e}")
        raise HTTPException(status_code=500, detail="Failed to save image")

    # Validate image
    is_valid, validation = await vision_service.validate_fridge_image(str(file_path))

    if not is_valid:
        # Log warning but don't notify user (IoT rejection)
        logger.warning(f"IoT image validation failed for household {household_id}")
        file_path.unlink(missing_ok=True)

        return IoTImageResponse(
            status="rejected",
            message="Image validation failed - not a fridge image",
        )

    # Analyze image
    analysis = await vision_service.analyze_fridge_image(str(file_path), household_id)

    # Create image record
    fridge_image = FridgeImage(
        id=image_id,
        household_id=household_id,
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        mime_type=file.content_type or "image/jpeg",
        source=ImageSource.IOT_CAMERA.value,
        priority=20,  # IoT has higher priority than manual
        status=ImageStatus.VALIDATED.value,
        validation_score=validation.get("confidence", 0.9),
        validated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.image_retention_days),
    )
    db.add(fridge_image)

    # Update fridge state
    state_result = await db.execute(
        select(FridgeState).where(FridgeState.household_id == household_id)
    )
    fridge_state = state_result.scalar_one_or_none()

    if not fridge_state:
        fridge_state = FridgeState(
            id=str(uuid4()),
            household_id=household_id,
        )
        db.add(fridge_state)

    fridge_state.last_analysis_at = datetime.now(timezone.utc)
    fridge_state.confidence_score = analysis.get("confidence", 0.8)

    fridge_image.fridge_state_id = fridge_state.id

    # Update device last seen
    device_result = await db.execute(
        select(Device).where(
            Device.household_id == household_id,
            Device.device_type == DeviceType.FRIDGE_CAMERA.value
        )
    )
    device = device_result.scalar_one_or_none()

    if device:
        device.last_seen_at = datetime.now(timezone.utc)
        device.status = DeviceStatus.ONLINE.value

    await db.commit()

    # Process through orchestrator (background, no user response needed)
    await orchestrator.process({
        "action": "process_image",
        "image_analysis": analysis,
        "household_id": household_id,
        "source": "iot",
    })

    logger.info(f"IoT image processed for household {household_id}: {len(analysis.get('items', []))} items")

    return IoTImageResponse(
        status="success",
        message=f"Image processed - detected {len(analysis.get('items', []))} items",
        image_id=image_id,
    )


@router.post("/device/register", response_model=DeviceStatusResponse)
async def register_device(
    request: DeviceRegistrationRequest,
    x_device_token: str = Header(..., alias="X-Device-Token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new IoT device.

    Devices authenticate with a token.
    """
    if not verify_device_token(x_device_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid device token"
        )

    # Check if device already exists
    existing_result = await db.execute(
        select(Device).where(
            Device.household_id == request.household_id,
            Device.device_type == request.device_type
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.last_seen_at = datetime.now(timezone.utc)
        existing.status = DeviceStatus.ONLINE.value
        await db.commit()

        return DeviceStatusResponse(
            device_id=existing.id,
            device_type=existing.device_type,
            status=existing.status,
            last_seen=existing.last_seen_at.isoformat() if existing.last_seen_at else None,
            is_simulated=existing.is_simulated,
        )

    # Create new device
    device = Device(
        id=str(uuid4()),
        household_id=request.household_id,
        name=request.name,
        device_type=request.device_type,
        device_token=x_device_token,
        status=DeviceStatus.ONLINE.value,
        is_simulated=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(device)
    await db.commit()

    logger.info(f"Device registered: {device.id} for household {request.household_id}")

    return DeviceStatusResponse(
        device_id=device.id,
        device_type=device.device_type,
        status=device.status,
        last_seen=device.last_seen_at.isoformat() if device.last_seen_at else None,
        is_simulated=device.is_simulated,
    )


@router.get("/device/{household_id}/status", response_model=DeviceStatusResponse)
async def get_device_status(
    household_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get status of fridge camera device."""
    device_result = await db.execute(
        select(Device).where(
            Device.household_id == household_id,
            Device.device_type == DeviceType.FRIDGE_CAMERA.value
        )
    )
    device = device_result.scalar_one_or_none()

    if not device:
        return DeviceStatusResponse(
            device_id="none",
            device_type=DeviceType.FRIDGE_CAMERA.value,
            status=DeviceStatus.UNKNOWN.value,
            is_simulated=True,
        )

    # Check if device is offline (no activity in 30 minutes)
    if device.last_seen_at:
        offline_threshold = datetime.now(timezone.utc) - timedelta(minutes=30)
        if device.last_seen_at < offline_threshold:
            device.status = DeviceStatus.OFFLINE.value
            await db.commit()

    return DeviceStatusResponse(
        device_id=device.id,
        device_type=device.device_type,
        status=device.status,
        last_seen=device.last_seen_at.isoformat() if device.last_seen_at else None,
        is_simulated=device.is_simulated,
    )


@router.post("/simulate/door-open")
async def simulate_door_open(
    household_id: str,
    x_device_token: str = Header(..., alias="X-Device-Token"),
):
    """
    Simulate fridge door opening (for testing).

    In production, this would be triggered by actual hardware.
    """
    if not verify_device_token(x_device_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid device token"
        )

    logger.info(f"Simulated door open event for household {household_id}")

    return {
        "status": "simulated",
        "event": "door_open",
        "household_id": household_id,
        "message": "Door open event simulated. Upload an image to /api/ingest/iot to simulate camera capture."
    }
