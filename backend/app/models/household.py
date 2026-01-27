"""
Household model - logical container for shared devices.

Ownership Rules:
- Fridge state is scoped to a household
- A user may belong to multiple households (future-ready)
- Phase 1 assumes single-user household but doesn't hardcode this
"""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.device import Device
    from app.models.fridge_state import FridgeState
    from app.models.inventory import InventoryItem
    from app.models.notification import Notification


class MemberRole(str, Enum):
    """Household member roles."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Household(Base):
    """Household model - container for shared devices."""

    __tablename__ = "households"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    members: Mapped[List["HouseholdMember"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan"
    )
    devices: Mapped[List["Device"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan"
    )
    fridge_states: Mapped[List["FridgeState"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan"
    )
    inventory_items: Mapped[List["InventoryItem"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Household {self.name}>"


class HouseholdMember(Base):
    """Association table for users and households with roles."""

    __tablename__ = "household_members"

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
    role: Mapped[str] = mapped_column(
        String(20),
        default=MemberRole.MEMBER.value
    )

    # Timestamps (UTC)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="household_memberships")
    household: Mapped["Household"] = relationship(back_populates="members")

    def __repr__(self) -> str:
        return f"<HouseholdMember user={self.user_id} household={self.household_id}>"
