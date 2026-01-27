"""
DomusFridge - Level 1 Domain Agent for Fridge Management.

Role: Specialized domain expert for refrigerator state and food safety.

Capabilities:
- Ingests image data
- Maintains internal fridge state (Inventory, Expiry)
- Emits structured intents (e.g., REQUIRE_PROCUREMENT, DETECTED_EXPIRY)

Constraints:
- NO direct user notifications
- NO direct external API calls
- NO direct conversation output
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.agents.base import AgentIntent, IntentType, Level1Agent
from app.models.inventory import FreshnessStatus, ItemCategory
from app.services.temporal_comparison_service import temporal_comparison_service, TemporalChanges
from app.services.confidence_decay_service import confidence_decay_service

logger = logging.getLogger(__name__)


class DomusFridge(Level1Agent):
    """
    Level 1 Fridge Agent.

    Manages fridge state and emits intents for the orchestrator.
    """

    def __init__(self, household_id: str):
        super().__init__(
            agent_id=f"fridge_{household_id}",
            agent_name="DomusFridge"
        )
        self.household_id = household_id
        self._current_inventory: List[Dict[str, Any]] = []
        self._last_analysis: Optional[Dict[str, Any]] = None
        self._confidence_score: float = 0.0
        self._latest_image_path: Optional[str] = None  # TODO: Remove - debugging only

        # Temporal analysis rolling buffer
        self._observation_history: List[Dict[str, Any]] = []
        self._max_observation_frames: int = 10

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process fridge-related operations.

        Context can contain:
        - action: "analyze_image", "check_expiry", "update_inventory"
        - image_analysis: Vision service results
        - manual_update: Manual inventory changes
        """
        action = context.get("action")

        if action == "analyze_image":
            return await self._process_image_analysis(context)
        elif action == "check_expiry":
            return await self._check_expiry()
        elif action == "update_inventory":
            return await self._update_inventory(context)
        elif action == "get_state":
            return self._get_current_state()
        else:
            logger.warning(f"Unknown action: {action}")
            return {"status": "error", "message": f"Unknown action: {action}"}

    async def _process_image_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process vision analysis results and update inventory.

        Emits intents based on findings.
        """
        analysis = context.get("image_analysis", {})

        # TODO: Remove - debugging only
        if context.get("image_path"):
            self._latest_image_path = context.get("image_path")

        if not analysis:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.ANALYSIS_FAILED,
                payload={"reason": "No analysis data provided"},
                household_id=self.household_id,
                confidence=0.0,
            ))
            return {"status": "error", "message": "No analysis data"}

        # Extract detected items from analysis
        detected_items = analysis.get("items", [])
        self._confidence_score = analysis.get("confidence", 0.8)

        # Check for degraded confidence
        if self._confidence_score < 0.5:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.CONFIDENCE_DEGRADED,
                payload={
                    "confidence": self._confidence_score,
                    "reason": "Low vision model confidence"
                },
                household_id=self.household_id,
                confidence=self._confidence_score,
            ))

        # Update internal inventory
        previous_items = {item["name"]: item for item in self._current_inventory}
        new_inventory = []
        items_added = []
        items_removed = []

        for item_data in detected_items:
            item = self._normalize_item(item_data)
            new_inventory.append(item)

            if item["name"] not in previous_items:
                items_added.append(item)

        # Check for removed items
        current_names = {item["name"] for item in new_inventory}
        for name, item in previous_items.items():
            if name not in current_names:
                items_removed.append(item)

        # Run temporal analysis BEFORE updating inventory
        temporal_changes = await self._run_temporal_analysis(new_inventory)

        # Store current frame in observation history
        self._store_observation(new_inventory)

        self._current_inventory = new_inventory
        self._last_analysis = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "item_count": len(new_inventory),
            "confidence": self._confidence_score,
            "temporal_changes": {
                "items_added": len(temporal_changes.items_added),
                "items_removed": len(temporal_changes.items_removed),
                "items_moved": len(temporal_changes.items_moved),
                "consumption_events": len(temporal_changes.consumption_events),
            }
        }

        # Emit inventory updated intent
        self.emit_intent(AgentIntent(
            intent_type=IntentType.INVENTORY_UPDATED,
            payload={
                "total_items": len(new_inventory),
                "items_added": len(items_added),
                "items_removed": len(items_removed),
                "items": [i["name"] for i in new_inventory],
                "temporal_analysis": {
                    "additions": len(temporal_changes.items_added),
                    "removals": len(temporal_changes.items_removed),
                    "movements": len(temporal_changes.items_moved),
                }
            },
            household_id=self.household_id,
            confidence=self._confidence_score,
            reasoning=f"Detected {len(new_inventory)} items with {self._confidence_score:.0%} confidence"
        ))

        # Check for expiry issues
        await self._check_expiry()

        # Check for procurement needs
        await self._check_procurement_needs()

        return {
            "status": "success",
            "inventory_count": len(new_inventory),
            "items_added": items_added,
            "items_removed": items_removed,
            "confidence": self._confidence_score,
        }

    def _normalize_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize item data to standard format."""
        name = item_data.get("name", "Unknown Item")
        category = item_data.get("category", ItemCategory.OTHER.value)

        # Estimate expiration if not provided
        expiration = item_data.get("expiration_date")
        if not expiration:
            expiration = self._estimate_expiration(category)

        return {
            "name": name,
            "category": category,
            "quantity": item_data.get("quantity", 1),
            "expiration_date": expiration,
            "confidence": item_data.get("confidence", 0.8),
            "location": item_data.get("location", "unknown"),
        }

    def _estimate_expiration(self, category: str) -> str:
        """Estimate expiration date based on category."""
        now = datetime.now(timezone.utc)
        days_map = {
            ItemCategory.DAIRY.value: 7,
            ItemCategory.PRODUCE.value: 5,
            ItemCategory.MEAT.value: 3,
            ItemCategory.SEAFOOD.value: 2,
            ItemCategory.BEVERAGES.value: 30,
            ItemCategory.CONDIMENTS.value: 90,
            ItemCategory.LEFTOVERS.value: 3,
            ItemCategory.FROZEN.value: 180,
            ItemCategory.OTHER.value: 14,
        }
        days = days_map.get(category, 14)
        return (now + timedelta(days=days)).isoformat()

    async def _check_expiry(self) -> Dict[str, Any]:
        """
        Check inventory for expiring/expired items.

        Emits appropriate intents.
        """
        now = datetime.now(timezone.utc)
        expiring_soon = []
        expired = []

        for item in self._current_inventory:
            exp_date_str = item.get("expiration_date")
            if not exp_date_str:
                continue

            try:
                exp_date = datetime.fromisoformat(exp_date_str.replace("Z", "+00:00"))
                days_until = (exp_date - now).days

                if days_until < 0:
                    expired.append({**item, "days_expired": abs(days_until)})
                elif days_until <= 3:
                    expiring_soon.append({**item, "days_until_expiry": days_until})
            except (ValueError, TypeError):
                continue

        # Emit intents for expired items
        if expired:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.DETECTED_EXPIRY,
                payload={
                    "expired_items": expired,
                    "count": len(expired),
                },
                household_id=self.household_id,
                confidence=0.9,
                reasoning=f"Found {len(expired)} expired items that should be discarded"
            ))

        # Emit intents for items expiring soon
        if expiring_soon:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.EXPIRY_WARNING,
                payload={
                    "expiring_items": expiring_soon,
                    "count": len(expiring_soon),
                },
                household_id=self.household_id,
                confidence=0.85,
                reasoning=f"Found {len(expiring_soon)} items expiring within 3 days"
            ))

        return {
            "expired": expired,
            "expiring_soon": expiring_soon,
        }

    async def _check_procurement_needs(self) -> None:
        """
        Analyze inventory for procurement needs.

        Emits REQUIRE_PROCUREMENT intent if staples are low.
        """
        # Define staple items that should trigger procurement
        staples = {"milk", "eggs", "bread", "butter", "cheese"}
        current_items = {item["name"].lower() for item in self._current_inventory}

        missing_staples = staples - current_items

        if missing_staples:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.REQUIRE_PROCUREMENT,
                payload={
                    "missing_items": list(missing_staples),
                    "category": "staples",
                },
                household_id=self.household_id,
                confidence=0.7,
                reasoning=f"Common staples missing: {', '.join(missing_staples)}"
            ))

    def _get_current_state(self) -> Dict[str, Any]:
        """Get current fridge state for orchestrator."""
        state = {
            "status": "success",
            "inventory": self._current_inventory,
            "item_count": len(self._current_inventory),
            "last_analysis": self._last_analysis,
            "confidence": self._confidence_score,
        }
        # TODO: Remove - debugging only
        if self._latest_image_path:
            # Convert file path to URL path
            import os
            filename = os.path.basename(self._latest_image_path)
            parent = os.path.basename(os.path.dirname(self._latest_image_path))
            state["latest_image_url"] = f"/images/{parent}/{filename}"
        return state

    async def handle_hardware_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle hardware-related events."""
        if event_type == "disconnected":
            self.emit_intent(AgentIntent(
                intent_type=IntentType.HARDWARE_DISCONNECTED,
                payload={
                    "device_type": "fridge_camera",
                    "last_seen": data.get("last_seen"),
                },
                household_id=self.household_id,
                confidence=1.0,
                reasoning="Fridge camera connection lost"
            ))
        elif event_type == "connected":
            self.emit_intent(AgentIntent(
                intent_type=IntentType.HARDWARE_CONNECTED,
                payload={
                    "device_type": "fridge_camera",
                },
                household_id=self.household_id,
                confidence=1.0,
            ))

    def _store_observation(self, frame_items: List[Dict[str, Any]]) -> None:
        """
        Add a frame observation to the rolling buffer.

        Maintains a maximum of max_observation_frames entries.
        """
        observation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items": frame_items,
            "item_count": len(frame_items),
        }

        self._observation_history.append(observation)

        # Trim to max size
        if len(self._observation_history) > self._max_observation_frames:
            self._observation_history = self._observation_history[-self._max_observation_frames:]

        logger.debug(f"Stored observation frame. Buffer size: {len(self._observation_history)}")

    async def _run_temporal_analysis(
        self,
        current_items: List[Dict[str, Any]]
    ) -> TemporalChanges:
        """
        Run temporal comparison analysis on current frame.

        Compares with observation history to detect changes.
        """
        changes = temporal_comparison_service.compare_frames(
            current_items=current_items,
            previous_frames=self._observation_history
        )

        # Emit intents for detected changes
        await self._emit_temporal_intents(changes)

        return changes

    async def _emit_temporal_intents(self, changes: TemporalChanges) -> None:
        """Emit intents based on temporal analysis results."""

        # Emit ITEM_ADDED intents
        for item in changes.items_added:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.ITEM_ADDED,
                payload={
                    "item_name": item.get("item_name"),
                    "location": item.get("location"),
                    "category": item.get("category"),
                    "confidence": item.get("confidence"),
                },
                household_id=self.household_id,
                confidence=item.get("confidence", 0.8),
                reasoning=f"New item detected: {item.get('item_name')} at {item.get('location')}"
            ))

        # Emit ITEM_REMOVED intents
        for item in changes.items_removed:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.ITEM_REMOVED,
                payload={
                    "item_name": item.get("item_name"),
                    "last_location": item.get("last_location"),
                    "was_present_for_frames": item.get("was_present_for_frames"),
                },
                household_id=self.household_id,
                confidence=item.get("last_confidence", 0.8),
                reasoning=f"Item removed: {item.get('item_name')} from {item.get('last_location')}"
            ))

        # Emit ITEM_MOVED intents
        for item in changes.items_moved:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.ITEM_MOVED,
                payload={
                    "item_name": item.get("item_name"),
                    "from_location": item.get("from_location"),
                    "to_location": item.get("to_location"),
                },
                household_id=self.household_id,
                confidence=0.85,
                reasoning=f"Item moved: {item.get('item_name')} from {item.get('from_location')} to {item.get('to_location')}"
            ))

        # Emit CONSUMPTION_LIKELY intents
        for event in changes.consumption_events:
            self.emit_intent(AgentIntent(
                intent_type=IntentType.CONSUMPTION_LIKELY,
                payload={
                    "item_name": event.get("item_name"),
                    "category": event.get("category"),
                    "consumption_confidence": event.get("consumption_confidence"),
                },
                household_id=self.household_id,
                confidence=event.get("consumption_confidence", 0.7),
                reasoning=event.get("reasoning", "Item likely consumed")
            ))

    def get_observation_history(self) -> List[Dict[str, Any]]:
        """Get the current observation history buffer."""
        return self._observation_history.copy()

    async def _apply_confidence_decay(self) -> None:
        """
        Update effective confidence for all items based on time.

        Emits CONFIDENCE_DEGRADED intents for items below threshold.
        """
        stale_items = confidence_decay_service.get_stale_items(self._current_inventory)

        for item in stale_items:
            effective_conf = item.get("effective_confidence", 0.5)
            hours_since_seen = item.get("hours_since_seen", 0)

            self.emit_intent(AgentIntent(
                intent_type=IntentType.CONFIDENCE_DEGRADED,
                payload={
                    "item": {
                        "name": item.get("name"),
                        "category": item.get("category"),
                        "location": item.get("location"),
                    },
                    "effective_confidence": effective_conf,
                    "hours_since_seen": hours_since_seen,
                    "verification_needed": True,
                },
                household_id=self.household_id,
                confidence=effective_conf,
                reasoning=f"Item '{item.get('name')}' not seen for {hours_since_seen:.1f} hours, confidence degraded to {effective_conf:.0%}"
            ))

    def get_inventory_with_decay(self) -> List[Dict[str, Any]]:
        """
        Get current inventory with confidence decay applied.

        Returns inventory items with effective_confidence and verification_needed fields.
        """
        return confidence_decay_service.apply_decay_to_inventory(self._current_inventory)

    async def check_and_apply_decay(self) -> Dict[str, Any]:
        """
        Check for decayed items and emit appropriate intents.

        Called periodically to maintain inventory accuracy.
        """
        await self._apply_confidence_decay()

        items_needing_verification = confidence_decay_service.get_items_needing_verification(
            self._current_inventory
        )

        return {
            "stale_count": len(confidence_decay_service.get_stale_items(self._current_inventory)),
            "verification_needed_count": len(items_needing_verification),
            "items_needing_verification": [
                item.get("name") for item in items_needing_verification
            ]
        }
