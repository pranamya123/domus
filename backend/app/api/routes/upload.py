"""
Image upload endpoints for manual fridge scanning.

Image Validation:
- Binary classifier: "Is this a fridge?"
- If valid: Add to buffer, trigger audit
- If invalid: Prompt user
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
from app.core.security import verify_token
from app.models.fridge_state import FridgeImage, FridgeState, ImageSource, ImageStatus
from app.models.household import HouseholdMember
from app.services.vision_service import vision_service

# Default anonymous household for users who aren't signed in
ANONYMOUS_USER_ID = "anonymous"
ANONYMOUS_HOUSEHOLD_ID = "anonymous_household"

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


class UploadResponse(BaseModel):
    """Response after image upload."""
    status: str
    message: str
    image_id: Optional[str] = None
    inventory_count: Optional[int] = None
    items_detected: Optional[list] = None
    validation_passed: bool = True


class ValidationResponse(BaseModel):
    """Image validation response."""
    is_valid: bool
    confidence: float
    reason: Optional[str] = None


@router.post("/image", response_model=UploadResponse)
async def upload_fridge_image(
    file: UploadFile = File(...),
    override_iot: bool = False,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a fridge image for analysis.

    Works for both authenticated and anonymous users.
    Manual scans may override IoT only if explicitly flagged.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an image"
        )

    user_id = ANONYMOUS_USER_ID
    household_id = ANONYMOUS_HOUSEHOLD_ID

    # Check if user is authenticated
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)

        if token_data:
            user_id = token_data.user_id

            # Get user's household
            membership_result = await db.execute(
                select(HouseholdMember).where(HouseholdMember.user_id == user_id)
            )
            membership = membership_result.scalar_one_or_none()

            if membership:
                household_id = membership.household_id

    # Save image to storage
    image_id = str(uuid4())
    file_extension = Path(file.filename or "image.jpg").suffix or ".jpg"
    file_path = settings.image_storage_path / household_id / f"{image_id}{file_extension}"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save image: {e}")
        raise HTTPException(status_code=500, detail="Failed to save image")

    # Validate image
    is_valid, validation = await vision_service.validate_fridge_image(str(file_path))

    if not is_valid:
        # Remove invalid image
        file_path.unlink(missing_ok=True)

        return UploadResponse(
            status="rejected",
            message="This doesn't appear to be a fridge image. Please upload a photo of the inside of your refrigerator.",
            validation_passed=False,
        )

    # Analyze image
    analysis = await vision_service.analyze_fridge_image(str(file_path), household_id)

    if not analysis.get("success"):
        return UploadResponse(
            status="error",
            message="Failed to analyze image. Please try again.",
            image_id=image_id,
            validation_passed=True,
        )

    # Create image record
    fridge_image = FridgeImage(
        id=image_id,
        household_id=household_id,
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        mime_type=file.content_type or "image/jpeg",
        source=ImageSource.MANUAL_SCAN.value,
        priority=10 if override_iot else 5,  # Manual has lower priority unless override
        is_override=override_iot,
        status=ImageStatus.VALIDATED.value,
        validation_score=validation.get("confidence", 0.9),
        validated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.image_retention_days),
    )
    db.add(fridge_image)

    # Get or create fridge state
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

    # Update fridge state
    fridge_state.last_analysis_at = datetime.now(timezone.utc)
    fridge_state.confidence_score = analysis.get("confidence", 0.8)
    fridge_state.is_degraded = analysis.get("degraded", False)

    # Link image to state
    fridge_image.fridge_state_id = fridge_state.id

    await db.commit()

    # Process through orchestrator
    result = await orchestrator.process({
        "action": "process_image",
        "image_analysis": analysis,
        "user_id": user_id,
        "household_id": household_id,
    })

    items = analysis.get("items", [])
    return UploadResponse(
        status="success",
        message=result.get("response", f"Detected {len(items)} items in your fridge."),
        image_id=image_id,
        inventory_count=len(items),
        items_detected=[item.get("name") for item in items],
        validation_passed=True,
    )


@router.post("/validate", response_model=ValidationResponse)
async def validate_image(
    file: UploadFile = File(...),
):
    """
    Validate an image without processing.

    Useful for client-side preview validation.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        return ValidationResponse(
            is_valid=False,
            confidence=0.0,
            reason="File must be an image"
        )

    # Save temporarily
    temp_path = Path("/tmp") / f"validate_{uuid4()}.jpg"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        is_valid, validation = await vision_service.validate_fridge_image(str(temp_path))

        return ValidationResponse(
            is_valid=is_valid,
            confidence=validation.get("confidence", 0.0),
            reason=validation.get("reason"),
        )
    finally:
        temp_path.unlink(missing_ok=True)


@router.get("/history")
async def get_upload_history(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    limit: int = 10,
):
    """Get recent image upload history for the user's household."""
    household_id = ANONYMOUS_HOUSEHOLD_ID

    # Check if user is authenticated
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)

        if token_data:
            # Get user's household
            membership_result = await db.execute(
                select(HouseholdMember).where(HouseholdMember.user_id == token_data.user_id)
            )
            membership = membership_result.scalar_one_or_none()

            if membership:
                household_id = membership.household_id

    # Get recent images
    images_result = await db.execute(
        select(FridgeImage)
        .where(FridgeImage.household_id == household_id)
        .order_by(FridgeImage.captured_at.desc())
        .limit(limit)
    )
    images = images_result.scalars().all()

    return {
        "images": [
            {
                "id": img.id,
                "source": img.source,
                "status": img.status,
                "captured_at": img.captured_at.isoformat(),
                "validation_score": img.validation_score,
            }
            for img in images
        ]
    }
