"""
Fridge Inventory Service

Iteration 1:
- Capture single Blink frame
- Extract inventory (Gemini stub)
- Store latest snapshot
- Retrieve latest snapshot
"""

import logging
from datetime import datetime
from typing import Optional

from shared.schemas.state import InventoryItem, InventorySnapshot
from shared.schemas.storage import DomusStorage

from .blink_service import BlinkService, get_blink_service
from app.llm import GeminiService, get_gemini_service

logger = logging.getLogger(__name__)


class FridgeInventoryService:
    """Minimal inventory service for Iteration 1."""

    def __init__(
        self,
        storage: DomusStorage,
        blink_service: Optional[BlinkService] = None,
        llm_service: Optional[GeminiService] = None,
    ):
        self._storage = storage
        self._blink_service = blink_service
        self._llm_service = llm_service

    def _get_blink(self) -> BlinkService:
        if self._blink_service is None:
            self._blink_service = get_blink_service()
        return self._blink_service

    def _get_llm(self) -> GeminiService:
        if self._llm_service is None:
            self._llm_service = get_gemini_service()
        return self._llm_service

    async def refresh(self, user_id: str, camera_name: str | None = None) -> dict:
        """
        Capture a Blink frame, extract inventory, and store the snapshot.
        """
        blink = self._get_blink()
        if not blink.is_connected(user_id):
            logger.warning("Fridge refresh blocked: Blink not connected (user_id=%s)", user_id)
            return {"success": False, "error": "Blink not connected"}
        logger.info("Fridge refresh started (user_id=%s, camera_name=%s)", user_id, camera_name)
        capture = await blink.capture_camera_frame(user_id, camera_name=camera_name)
        if not capture.get("success"):
            logger.warning("Fridge refresh capture failed (user_id=%s, error=%s)", user_id, capture.get("error"))
            return {"success": False, "error": capture.get("error", "Blink capture failed")}

        image_b64 = capture.get("image_bytes_b64")
        if not image_b64:
            logger.warning("Fridge refresh missing image bytes (user_id=%s)", user_id)
            return {"success": False, "error": "No image bytes returned from Blink"}

        llm = self._get_llm()
        raw_items = await llm.extract_fridge_inventory(image_b64)
        items = self._build_items(raw_items)

        snapshot = InventorySnapshot(
            user_id=user_id,
            items=items,
            captured_at=datetime.utcnow(),
            thumbnail_b64=image_b64,
            confidence=1.0 if items else 0.0,
        )
        await self._storage.state.save_inventory(snapshot)
        logger.info("Fridge refresh stored snapshot (user_id=%s, items=%s)", user_id, len(items))

        return {
            "success": True,
            "captured_at": snapshot.captured_at.isoformat() + "Z",
            "camera_name": capture.get("camera_name"),
            "inventory": self._snapshot_to_inventory_dict(snapshot),
        }

    async def get_latest(self, user_id: str) -> dict | None:
        """Get latest inventory snapshot for a user."""
        snapshot = await self._storage.state.get_latest_inventory(user_id)
        if not snapshot:
            return None
        return self._snapshot_to_inventory_dict(snapshot)

    def _build_items(self, raw_items: list[dict] | None) -> list[InventoryItem]:
        items: list[InventoryItem] = []
        for raw in raw_items or []:
            name = (raw.get("name") or "").strip()
            if not name:
                continue

            quantity = raw.get("quantity", 1)
            if isinstance(quantity, (int, float)):
                quantity = max(1, int(quantity))
            else:
                quantity = 1

            items.append(
                InventoryItem(
                    name=name,
                    category=raw.get("category") or "unknown",
                    quantity=quantity,
                    unit=raw.get("unit"),
                    confidence=float(raw.get("confidence", 1.0)),
                )
            )

        return items

    def _snapshot_to_inventory_dict(self, snapshot: InventorySnapshot) -> dict:
        items: list[dict] = []
        for item in snapshot.items:
            entry = {
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
            }
            items.append(entry)

        return {
            "items": items,
            "captured_at": snapshot.captured_at.isoformat() + "Z",
            "thumbnail_b64": snapshot.thumbnail_b64,
        }
