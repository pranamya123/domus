"""
Temporal Comparison Service - Compares rolling buffer frames to detect item changes.

Responsibilities:
- Frame-to-frame comparison for change detection
- Item addition/removal/movement detection
- Consumption pattern analysis
- Stagnant item identification
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class ItemObservation:
    """A single observation of an item in a frame."""
    item_id: str
    name: str
    location: str
    confidence: float
    observed_at: datetime
    frame_id: str
    category: str = "other"
    quantity: int = 1


@dataclass
class ItemAddedEvent:
    """Event representing an item added to the fridge."""
    item_name: str
    location: str
    confidence: float
    detected_at: datetime
    category: str = "other"


@dataclass
class ItemRemovedEvent:
    """Event representing an item removed from the fridge."""
    item_name: str
    last_location: str
    last_confidence: float
    removed_at: datetime
    was_present_for_frames: int = 1


@dataclass
class ItemMovedEvent:
    """Event representing an item moved within the fridge."""
    item_name: str
    from_location: str
    to_location: str
    detected_at: datetime


@dataclass
class ConsumptionEvent:
    """Event indicating likely consumption of an item."""
    item_name: str
    category: str
    last_seen_at: datetime
    consumption_confidence: float
    reasoning: str


@dataclass
class StagnantItem:
    """Item that hasn't moved in a long time."""
    item_name: str
    location: str
    hours_stationary: float
    last_seen_at: datetime
    category: str


@dataclass
class TemporalChanges:
    """Aggregated changes detected between frames."""
    items_added: List[Dict[str, Any]] = field(default_factory=list)
    items_removed: List[Dict[str, Any]] = field(default_factory=list)
    items_moved: List[Dict[str, Any]] = field(default_factory=list)
    consumption_events: List[Dict[str, Any]] = field(default_factory=list)
    stagnant_items: List[Dict[str, Any]] = field(default_factory=list)
    analysis_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TemporalComparisonService:
    """
    Compares rolling buffer frames to detect item changes.

    Tracks item additions, removals, movements, and consumption patterns
    by analyzing sequential frames from the fridge camera.
    """

    # Minimum confidence threshold for considering an item "present"
    PRESENCE_THRESHOLD = 0.5

    # Location similarity threshold for considering same location
    LOCATION_MATCH_THRESHOLD = 0.8

    # Frames an item must be absent before considering it removed
    REMOVAL_FRAME_THRESHOLD = 2

    # Default hours before an item is considered stagnant
    DEFAULT_STAGNANT_HOURS = 72

    def __init__(self):
        self._observation_cache: Dict[str, List[ItemObservation]] = {}

    def compare_frames(
        self,
        current_items: List[Dict[str, Any]],
        previous_frames: List[Dict[str, Any]],
        frame_id: Optional[str] = None
    ) -> TemporalChanges:
        """
        Compare current frame items with previous frames to detect changes.

        Args:
            current_items: Items detected in the current frame
            previous_frames: List of previous frame observations
            frame_id: Optional identifier for the current frame

        Returns:
            TemporalChanges object with all detected changes
        """
        if not frame_id:
            frame_id = str(uuid4())

        changes = TemporalChanges()

        # Get the most recent previous frame for comparison
        if not previous_frames:
            # First frame - all items are "additions"
            for item in current_items:
                event = ItemAddedEvent(
                    item_name=item.get("name", "Unknown"),
                    location=item.get("location", "unknown"),
                    confidence=item.get("confidence", 0.8),
                    detected_at=datetime.now(timezone.utc),
                    category=item.get("category", "other")
                )
                changes.items_added.append(self._event_to_dict(event))
            return changes

        # Compare with previous frame(s)
        previous_items = previous_frames[-1].get("items", []) if previous_frames else []

        # Detect additions
        additions = self.detect_item_additions(current_items, previous_items)
        changes.items_added = [self._event_to_dict(e) for e in additions]

        # Detect removals
        removals = self.detect_item_removals(current_items, previous_items, previous_frames)
        changes.items_removed = [self._event_to_dict(e) for e in removals]

        # Detect movements
        movements = self.detect_item_movements(current_items, previous_items)
        changes.items_moved = [self._event_to_dict(e) for e in movements]

        # Detect consumption patterns for removed items
        for removal in removals:
            consumption = self.detect_consumption(removal, previous_frames)
            if consumption:
                changes.consumption_events.append(self._event_to_dict(consumption))

        return changes

    def detect_item_additions(
        self,
        current: List[Dict[str, Any]],
        previous: List[Dict[str, Any]]
    ) -> List[ItemAddedEvent]:
        """
        Detect items that appear in current frame but not in previous.

        Args:
            current: Current frame items
            previous: Previous frame items

        Returns:
            List of ItemAddedEvent for new items
        """
        additions = []
        previous_names = {item.get("name", "").lower() for item in previous}

        for item in current:
            name = item.get("name", "").lower()
            confidence = item.get("confidence", 0.8)

            # Only consider items with sufficient confidence
            if confidence < self.PRESENCE_THRESHOLD:
                continue

            if name and name not in previous_names:
                additions.append(ItemAddedEvent(
                    item_name=item.get("name", "Unknown"),
                    location=item.get("location", "unknown"),
                    confidence=confidence,
                    detected_at=datetime.now(timezone.utc),
                    category=item.get("category", "other")
                ))

        return additions

    def detect_item_removals(
        self,
        current: List[Dict[str, Any]],
        previous: List[Dict[str, Any]],
        all_frames: Optional[List[Dict[str, Any]]] = None
    ) -> List[ItemRemovedEvent]:
        """
        Detect items that were in previous frame but not in current.

        Uses frame history to avoid false positives from temporary occlusion.

        Args:
            current: Current frame items
            previous: Previous frame items
            all_frames: Full frame history for validation

        Returns:
            List of ItemRemovedEvent for removed items
        """
        removals = []
        current_names = {item.get("name", "").lower() for item in current}

        for item in previous:
            name = item.get("name", "").lower()
            confidence = item.get("confidence", 0.8)

            if confidence < self.PRESENCE_THRESHOLD:
                continue

            if name and name not in current_names:
                # Check if consistently absent across multiple frames
                frames_present = self._count_presence_in_history(name, all_frames or [])

                # Only report removal if item was stably present before
                if frames_present >= 1:
                    removals.append(ItemRemovedEvent(
                        item_name=item.get("name", "Unknown"),
                        last_location=item.get("location", "unknown"),
                        last_confidence=confidence,
                        removed_at=datetime.now(timezone.utc),
                        was_present_for_frames=frames_present
                    ))

        return removals

    def detect_item_movements(
        self,
        current: List[Dict[str, Any]],
        previous: List[Dict[str, Any]]
    ) -> List[ItemMovedEvent]:
        """
        Detect items that changed location between frames.

        Args:
            current: Current frame items
            previous: Previous frame items

        Returns:
            List of ItemMovedEvent for moved items
        """
        movements = []

        # Build lookup maps
        current_map = {item.get("name", "").lower(): item for item in current}
        previous_map = {item.get("name", "").lower(): item for item in previous}

        for name, curr_item in current_map.items():
            if name in previous_map:
                prev_item = previous_map[name]
                curr_location = curr_item.get("location", "unknown").lower()
                prev_location = prev_item.get("location", "unknown").lower()

                # Check if location changed
                if curr_location != prev_location and curr_location != "unknown" and prev_location != "unknown":
                    movements.append(ItemMovedEvent(
                        item_name=curr_item.get("name", "Unknown"),
                        from_location=prev_item.get("location", "unknown"),
                        to_location=curr_item.get("location", "unknown"),
                        detected_at=datetime.now(timezone.utc)
                    ))

        return movements

    def detect_consumption(
        self,
        removed_item: ItemRemovedEvent,
        observation_history: List[Dict[str, Any]]
    ) -> Optional[ConsumptionEvent]:
        """
        Analyze if a removed item was likely consumed vs. thrown away.

        Uses observation patterns to estimate consumption likelihood.

        Args:
            removed_item: The item that was removed
            observation_history: Historical frame observations

        Returns:
            ConsumptionEvent if consumption is likely, None otherwise
        """
        item_name_lower = removed_item.item_name.lower()

        # Count how many frames the item appeared in
        appearance_count = self._count_presence_in_history(item_name_lower, observation_history)

        if appearance_count < 2:
            return None

        # Heuristics for consumption likelihood
        # Items present for multiple frames that suddenly disappear are likely consumed
        consumption_confidence = min(0.95, 0.5 + (appearance_count * 0.1))

        # Higher confidence for food categories that are typically consumed
        consumable_categories = {"dairy", "produce", "meat", "seafood", "beverages", "leftovers"}

        # Try to find the category from history
        category = "unknown"
        for frame in observation_history:
            for item in frame.get("items", []):
                if item.get("name", "").lower() == item_name_lower:
                    category = item.get("category", "other")
                    break

        if category.lower() in consumable_categories:
            consumption_confidence += 0.1

        return ConsumptionEvent(
            item_name=removed_item.item_name,
            category=category,
            last_seen_at=removed_item.removed_at,
            consumption_confidence=min(1.0, consumption_confidence),
            reasoning=f"Item observed in {appearance_count} frames before removal"
        )

    def find_stagnant_items(
        self,
        inventory: List[Dict[str, Any]],
        threshold_hours: float = 72
    ) -> List[StagnantItem]:
        """
        Find items that haven't moved in a specified time period.

        Stagnant items may indicate forgotten food or items that should
        be checked for freshness.

        Args:
            inventory: Current inventory items with last_seen_at timestamps
            threshold_hours: Hours of inactivity before considering stagnant

        Returns:
            List of StagnantItem for items past the threshold
        """
        stagnant = []
        now = datetime.now(timezone.utc)

        for item in inventory:
            last_seen_str = item.get("last_seen_at") or item.get("first_detected_at")
            if not last_seen_str:
                continue

            try:
                if isinstance(last_seen_str, str):
                    last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                else:
                    last_seen = last_seen_str

                hours_since_seen = (now - last_seen).total_seconds() / 3600

                if hours_since_seen >= threshold_hours:
                    stagnant.append(StagnantItem(
                        item_name=item.get("name", "Unknown"),
                        location=item.get("location", "unknown"),
                        hours_stationary=hours_since_seen,
                        last_seen_at=last_seen,
                        category=item.get("category", "other")
                    ))
            except (ValueError, TypeError) as e:
                logger.debug(f"Error parsing timestamp for item {item.get('name')}: {e}")
                continue

        return stagnant

    def _count_presence_in_history(
        self,
        item_name: str,
        frames: List[Dict[str, Any]]
    ) -> int:
        """Count how many frames an item appeared in."""
        count = 0
        item_name_lower = item_name.lower()

        for frame in frames:
            items = frame.get("items", [])
            for item in items:
                if item.get("name", "").lower() == item_name_lower:
                    count += 1
                    break

        return count

    def _event_to_dict(self, event: Any) -> Dict[str, Any]:
        """Convert a dataclass event to dictionary."""
        if hasattr(event, '__dataclass_fields__'):
            result = {}
            for field_name in event.__dataclass_fields__:
                value = getattr(event, field_name)
                if isinstance(value, datetime):
                    value = value.isoformat()
                result[field_name] = value
            return result
        return {}


# Global service instance
temporal_comparison_service = TemporalComparisonService()
