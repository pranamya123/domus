"""
Inventory item model for fridge contents.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.household import Household


class ItemCategory(str, Enum):
    """Food item categories."""
    DAIRY = "dairy"
    PRODUCE = "produce"
    MEAT = "meat"
    SEAFOOD = "seafood"
    BEVERAGES = "beverages"
    CONDIMENTS = "condiments"
    LEFTOVERS = "leftovers"
    FROZEN = "frozen"
    OTHER = "other"


class FreshnessStatus(str, Enum):
    """Freshness status of an item."""
    FRESH = "fresh"
    EXPIRING_SOON = "expiring_soon"  # Within 3 days
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class InventoryItem(Base):
    """Individual item in the fridge inventory."""

    __tablename__ = "inventory_items"

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

    # Item identification
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(
        String(50),
        default=ItemCategory.OTHER.value
    )
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Quantity
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Expiration tracking
    expiration_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    predicted_expiration: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    freshness_status: Mapped[str] = mapped_column(
        String(20),
        default=FreshnessStatus.UNKNOWN.value
    )

    # Detection metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    detected_from_image_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True
    )
    location_in_fridge: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )  # e.g., "top shelf", "door", "drawer"

    # Confidence decay tracking
    base_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    decay_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    verification_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    observation_count: Mapped[int] = mapped_column(Integer, default=1)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_manually_added: Mapped[bool] = mapped_column(Boolean, default=False)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps (UTC)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    removed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    household: Mapped["Household"] = relationship(back_populates="inventory_items")

    def __repr__(self) -> str:
        return f"<InventoryItem {self.name} ({self.quantity})>"

    def update_freshness_status(self) -> None:
        """Update freshness status based on expiration date."""
        if not self.expiration_date:
            self.freshness_status = FreshnessStatus.UNKNOWN.value
            return

        now = datetime.now(timezone.utc)
        days_until_expiry = (self.expiration_date - now).days

        if days_until_expiry < 0:
            self.freshness_status = FreshnessStatus.EXPIRED.value
        elif days_until_expiry <= 3:
            self.freshness_status = FreshnessStatus.EXPIRING_SOON.value
        else:
            self.freshness_status = FreshnessStatus.FRESH.value
