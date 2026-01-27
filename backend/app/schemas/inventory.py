"""
Inventory-related schemas.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class InventoryItemCreate(BaseModel):
    """Schema for creating an inventory item."""
    name: str
    category: str = "other"
    quantity: int = 1
    unit: Optional[str] = None
    expiration_date: Optional[datetime] = None
    location_in_fridge: Optional[str] = None
    notes: Optional[str] = None


class InventoryItemResponse(BaseModel):
    """Schema for inventory item response."""
    id: str
    name: str
    category: str
    quantity: int
    unit: Optional[str] = None
    expiration_date: Optional[str] = None
    freshness_status: str
    confidence: float
    location_in_fridge: Optional[str] = None
    first_detected_at: str
    last_seen_at: str

    class Config:
        from_attributes = True


class InventoryListResponse(BaseModel):
    """Schema for inventory list response."""
    items: List[InventoryItemResponse]
    total_count: int
    last_updated: Optional[str] = None
    confidence: float = 0.0
