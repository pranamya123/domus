"""
Confidence Decay Service - Calculates effective confidence based on time since last seen.

Responsibilities:
- Calculate time-based confidence decay
- Category-specific decay rates
- Identify items needing verification
- Find stale items below threshold
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfidenceDecayService:
    """
    Calculates effective confidence based on time since last seen.

    Uses exponential decay with category-specific rates to model
    uncertainty about item presence over time.

    Decay Formula:
        effective_confidence = base_confidence * exp(-decay_rate * hours_since_seen)
    """

    # Decay rates by category (per hour)
    # Higher rates mean faster confidence decay (more perishable/volatile items)
    DECAY_RATES = {
        'dairy': 0.05,       # ~14 hours to halve
        'produce': 0.04,     # ~17 hours to halve
        'meat': 0.08,        # ~9 hours to halve
        'seafood': 0.10,     # ~7 hours to halve
        'condiments': 0.01,  # ~69 hours to halve
        'beverages': 0.02,   # ~35 hours to halve
        'frozen': 0.01,      # ~69 hours to halve
        'leftovers': 0.06,   # ~12 hours to halve
        'other': 0.02,       # ~35 hours to halve
        'default': 0.02,     # Default rate
    }

    # Confidence thresholds
    VERIFICATION_THRESHOLD = 0.6  # Below this, item needs verification
    STALE_THRESHOLD = 0.5         # Below this, item is considered stale
    MINIMUM_CONFIDENCE = 0.1      # Floor for decayed confidence

    def __init__(self):
        pass

    def calculate_effective_confidence(
        self,
        item: Dict[str, Any],
        current_time: Optional[datetime] = None
    ) -> float:
        """
        Calculate effective confidence for an item based on time decay.

        Args:
            item: Item dictionary with confidence, category, and last_seen_at
            current_time: Optional current time for calculation

        Returns:
            Effective confidence value between MINIMUM_CONFIDENCE and 1.0
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Get base confidence
        base_confidence = item.get("base_confidence") or item.get("confidence", 1.0)

        # Get last seen timestamp
        last_seen = self._parse_timestamp(
            item.get("last_seen_at") or item.get("last_verified_at")
        )

        if not last_seen:
            # If never seen, use first_detected_at or return base confidence
            last_seen = self._parse_timestamp(item.get("first_detected_at"))
            if not last_seen:
                return base_confidence

        # Calculate hours since seen
        hours_since_seen = (current_time - last_seen).total_seconds() / 3600

        if hours_since_seen <= 0:
            return base_confidence

        # Get category-specific decay rate
        category = item.get("category", "default").lower()
        decay_rate = item.get("decay_rate") or self.DECAY_RATES.get(
            category, self.DECAY_RATES["default"]
        )

        # Apply exponential decay
        decay_factor = self.get_decay_factor(hours_since_seen, category, decay_rate)
        effective_confidence = base_confidence * decay_factor

        # Apply floor
        return max(self.MINIMUM_CONFIDENCE, effective_confidence)

    def get_decay_factor(
        self,
        hours_unseen: float,
        category: str,
        custom_rate: Optional[float] = None
    ) -> float:
        """
        Calculate the decay factor for a given time period.

        Args:
            hours_unseen: Hours since item was last seen
            category: Item category for rate lookup
            custom_rate: Optional override for decay rate

        Returns:
            Decay factor between 0 and 1
        """
        if hours_unseen <= 0:
            return 1.0

        decay_rate = custom_rate or self.DECAY_RATES.get(
            category.lower(), self.DECAY_RATES["default"]
        )

        return math.exp(-decay_rate * hours_unseen)

    def get_stale_items(
        self,
        inventory: List[Dict[str, Any]],
        threshold: Optional[float] = None,
        current_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Find items with effective confidence below threshold.

        Args:
            inventory: List of inventory items
            threshold: Confidence threshold (default: STALE_THRESHOLD)
            current_time: Optional current time for calculation

        Returns:
            List of stale items with effective_confidence added
        """
        if threshold is None:
            threshold = self.STALE_THRESHOLD

        stale_items = []

        for item in inventory:
            effective_conf = self.calculate_effective_confidence(item, current_time)

            if effective_conf < threshold:
                item_with_conf = item.copy()
                item_with_conf["effective_confidence"] = effective_conf
                item_with_conf["hours_since_seen"] = self._calculate_hours_since_seen(
                    item, current_time
                )
                stale_items.append(item_with_conf)

        return stale_items

    def should_request_verification(
        self,
        item: Dict[str, Any],
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Determine if an item needs manual verification.

        Args:
            item: Item dictionary
            current_time: Optional current time for calculation

        Returns:
            True if item needs verification
        """
        # Check if already marked as needing verification
        if item.get("verification_needed"):
            return True

        effective_conf = self.calculate_effective_confidence(item, current_time)
        return effective_conf < self.VERIFICATION_THRESHOLD

    def get_items_needing_verification(
        self,
        inventory: List[Dict[str, Any]],
        current_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all items that need verification.

        Args:
            inventory: List of inventory items
            current_time: Optional current time for calculation

        Returns:
            List of items needing verification
        """
        needs_verification = []

        for item in inventory:
            if self.should_request_verification(item, current_time):
                item_copy = item.copy()
                item_copy["effective_confidence"] = self.calculate_effective_confidence(
                    item, current_time
                )
                needs_verification.append(item_copy)

        return needs_verification

    def apply_decay_to_inventory(
        self,
        inventory: List[Dict[str, Any]],
        current_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Apply confidence decay to all inventory items.

        Args:
            inventory: List of inventory items
            current_time: Optional current time for calculation

        Returns:
            Updated inventory with effective_confidence added
        """
        updated_inventory = []

        for item in inventory:
            item_copy = item.copy()
            item_copy["effective_confidence"] = self.calculate_effective_confidence(
                item, current_time
            )
            item_copy["verification_needed"] = self.should_request_verification(
                item, current_time
            )
            updated_inventory.append(item_copy)

        return updated_inventory

    def get_decay_rate_for_category(self, category: str) -> float:
        """Get the decay rate for a specific category."""
        return self.DECAY_RATES.get(category.lower(), self.DECAY_RATES["default"])

    def estimate_time_to_stale(
        self,
        item: Dict[str, Any],
        threshold: Optional[float] = None
    ) -> Optional[float]:
        """
        Estimate hours until an item becomes stale.

        Args:
            item: Item dictionary
            threshold: Confidence threshold (default: STALE_THRESHOLD)

        Returns:
            Hours until stale, or None if already stale or cannot calculate
        """
        if threshold is None:
            threshold = self.STALE_THRESHOLD

        base_confidence = item.get("base_confidence") or item.get("confidence", 1.0)

        if base_confidence <= threshold:
            return 0.0  # Already below threshold

        category = item.get("category", "default").lower()
        decay_rate = item.get("decay_rate") or self.DECAY_RATES.get(
            category, self.DECAY_RATES["default"]
        )

        if decay_rate <= 0:
            return None  # Cannot calculate with zero/negative rate

        # Solve for t: threshold = base_confidence * exp(-rate * t)
        # t = -ln(threshold / base_confidence) / rate
        try:
            ratio = threshold / base_confidence
            if ratio <= 0 or ratio >= 1:
                return None
            hours_to_stale = -math.log(ratio) / decay_rate
            return max(0.0, hours_to_stale)
        except (ValueError, ZeroDivisionError):
            return None

    def _parse_timestamp(
        self,
        timestamp: Optional[str | datetime]
    ) -> Optional[datetime]:
        """Parse a timestamp string or return datetime as-is."""
        if timestamp is None:
            return None

        if isinstance(timestamp, datetime):
            return timestamp

        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _calculate_hours_since_seen(
        self,
        item: Dict[str, Any],
        current_time: Optional[datetime] = None
    ) -> float:
        """Calculate hours since item was last seen."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        last_seen = self._parse_timestamp(
            item.get("last_seen_at") or item.get("last_verified_at") or
            item.get("first_detected_at")
        )

        if not last_seen:
            return 0.0

        return max(0.0, (current_time - last_seen).total_seconds() / 3600)


# Global service instance
confidence_decay_service = ConfidenceDecayService()
