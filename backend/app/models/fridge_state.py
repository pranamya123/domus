"""
Fridge state and image models.

Rolling Buffer:
- Capacity: Last 3 validated images
- Priority: IoT Camera > Manual Scan
- Manual scans may override IoT only if explicitly flagged
"""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.household import Household


class ImageSource(str, Enum):
    """Source of fridge image."""
    IOT_CAMERA = "iot_camera"
    MANUAL_SCAN = "manual_scan"


class ImageStatus(str, Enum):
    """Validation status of fridge image."""
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class FridgeImage(Base):
    """Individual fridge image with metadata."""

    __tablename__ = "fridge_images"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    household_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("households.id", ondelete="CASCADE"),
        index=True
    )

    # Image data
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(50))

    # Source and priority
    source: Mapped[str] = mapped_column(String(20))
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher = more priority
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)

    # Validation
    status: Mapped[str] = mapped_column(
        String(20),
        default=ImageStatus.PENDING.value
    )
    validation_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps (UTC - server time is authoritative)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )  # 30 days from capture

    # Relationship to state (which buffer position)
    fridge_state_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("fridge_states.id", ondelete="SET NULL"),
        nullable=True
    )

    def __repr__(self) -> str:
        return f"<FridgeImage {self.id[:8]} ({self.source})>"


class FridgeState(Base):
    """
    Current fridge state with rolling image buffer.

    Scoped to household.
    """

    __tablename__ = "fridge_states"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    household_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("households.id", ondelete="CASCADE"),
        unique=True,
        index=True
    )

    # Current state (JSON serialized in production)
    last_analysis_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    degradation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Buffer tracking
    buffer_size: Mapped[int] = mapped_column(Integer, default=3)
    current_image_count: Mapped[int] = mapped_column(Integer, default=0)

    # Temporal observation history (JSON serialized rolling buffer)
    observation_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_observation_frames: Mapped[int] = mapped_column(Integer, default=10)

    # Timestamps (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    last_analysis_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    household: Mapped["Household"] = relationship(back_populates="fridge_states")
    images: Mapped[List["FridgeImage"]] = relationship(
        foreign_keys=[FridgeImage.fridge_state_id],
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FridgeState household={self.household_id[:8]}>"
