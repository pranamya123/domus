"""
Fridge state API endpoints.

Provides access to current fridge inventory and latest capture.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.agents.domus_orchestrator import orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

ANONYMOUS_HOUSEHOLD_ID = "anonymous_household"


@router.get("/state")
async def get_fridge_state(
    authorization: Optional[str] = Header(None),
):
    """
    Get current fridge state including inventory and latest image.

    Returns:
    - inventory: List of items in the fridge
    - item_count: Total number of items
    - latest_image_url: URL to the most recent capture
    - last_analysis: Timestamp of last analysis
    - confidence: Overall confidence score
    """
    household_id = ANONYMOUS_HOUSEHOLD_ID

    # Get fridge state from orchestrator
    result = await orchestrator.process({
        "action": "get_inventory",
        "household_id": household_id,
    })

    return {
        "status": "success",
        "inventory": result.get("inventory", []),
        "item_count": result.get("item_count", 0),
        "latest_image_url": result.get("latest_image_url"),
        "last_updated": result.get("last_updated"),
        "confidence": result.get("confidence", 0),
    }


@router.get("/latest-image")
async def get_latest_image(
    authorization: Optional[str] = Header(None),
):
    """
    Get just the latest fridge image URL.

    Quick endpoint for checking the most recent capture.
    """
    household_id = ANONYMOUS_HOUSEHOLD_ID

    result = await orchestrator.process({
        "action": "get_inventory",
        "household_id": household_id,
    })

    return {
        "latest_image_url": result.get("latest_image_url"),
        "last_updated": result.get("last_updated"),
        "item_count": result.get("item_count", 0),
    }
