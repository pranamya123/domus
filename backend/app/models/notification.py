"""
Notification models.

Schema per spec:
NotificationIntent(
  type,
  severity,
  context,
  timestamp,
  user_id,
  household_id
)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class NotificationType(str, Enum):
    """Types of notifications as per spec."""
    PERISHABLE_EXPIRY = "perishable_expiry"
    PROCUREMENT_REQUIRED = "procurement_required"
    PROCUREMENT_APPROVAL = "procurement_approval"
    CALENDAR_EVENT_INGREDIENT_MISSING = "calendar_event_ingredient_missing"
    HARDWARE_DISCONNECTED = "hardware_disconnected"
    BULK_BUY_OPPORTUNITY = "bulk_buy_opportunity"


class NotificationSeverity(str, Enum):
    """Notification severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, Enum):
    """Delivery channels."""
    IN_APP = "in_app"
    PUSH = "push"
    ALEXA = "alexa"
    EMAIL = "email"


class DeliveryStatus(str, Enum):
    """Delivery status."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class Notification(Base):
    """Notification record."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )
    household_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("households.id", ondelete="CASCADE"),
        index=True
    )

    # Notification content
    notification_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(
        String(20),
        default=NotificationSeverity.MEDIUM.value
    )
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Delivery
    channel: Mapped[str] = mapped_column(
        String(20),
        default=NotificationChannel.IN_APP.value
    )
    delivery_status: Mapped[str] = mapped_column(
        String(20),
        default=DeliveryStatus.PENDING.value
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Read status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Timestamps (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Reference to source (e.g., inventory item that triggered expiry alert)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification {self.notification_type} for user={self.user_id[:8]}>"


class NotificationPreference(Base):
    """User notification preferences."""

    __tablename__ = "notification_preferences"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # Preference settings
    notification_type: Mapped[str] = mapped_column(String(50))
    channel: Mapped[str] = mapped_column(String(20))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Schedule (e.g., quiet hours)
    quiet_start_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quiet_end_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notification_preferences")

    def __repr__(self) -> str:
        return f"<NotificationPreference {self.notification_type} via {self.channel}>"
