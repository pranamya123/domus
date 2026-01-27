"""
Device model - represents a physical or simulated IoT entity.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.household import Household


class DeviceType(str, Enum):
    """Types of IoT devices."""
    FRIDGE_CAMERA = "fridge_camera"
    PANTRY_SENSOR = "pantry_sensor"  # Future
    WASHER = "washer"  # Future


class DeviceStatus(str, Enum):
    """Device connection status."""
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class Device(Base):
    """IoT device model."""

    __tablename__ = "devices"

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

    # Device info
    name: Mapped[str] = mapped_column(String(255))
    device_type: Mapped[str] = mapped_column(String(50))
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Authentication
    device_token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default=DeviceStatus.UNKNOWN.value
    )
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)

    # Configuration (JSON in production)
    config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    household: Mapped["Household"] = relationship(back_populates="devices")

    def __repr__(self) -> str:
        return f"<Device {self.name} ({self.device_type})>"
