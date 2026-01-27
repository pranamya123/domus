"""
Calendar Service - Mocked Google Calendar integration.

Failure Handling:
- Calendar Failure: Skip calendar-driven intents

Enhanced for temporal reasoning and proactive intelligence:
- Meal event detection
- Ingredient extraction and matching
- Procurement urgency calculation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MealEvent:
    """Represents a meal-related calendar event."""
    event_id: str
    title: str
    date: datetime
    meal_type: str  # breakfast, lunch, dinner, brunch, other
    required_ingredients: List[str] = field(default_factory=list)
    guests: int = 1
    description: str = ""

    def days_away(self, from_time: Optional[datetime] = None) -> float:
        """Calculate days until this event."""
        if from_time is None:
            from_time = datetime.now(timezone.utc)
        return (self.date - from_time).total_seconds() / 86400


@dataclass
class MissingIngredients:
    """Result of checking inventory against event requirements."""
    event: MealEvent
    missing: List[str]
    available: List[str]
    procurement_urgency: str  # low, medium, high, urgent

    @property
    def has_missing(self) -> bool:
        return len(self.missing) > 0

    @property
    def missing_count(self) -> int:
        return len(self.missing)


class CalendarService:
    """
    Mocked Google Calendar service for meal planning integration.

    In production, this would integrate with Google Calendar API.
    """

    def __init__(self):
        self._mock_events: List[Dict[str, Any]] = []
        self._setup_mock_events()

    def _setup_mock_events(self):
        """Set up mock calendar events for testing."""
        now = datetime.now(timezone.utc)

        self._mock_events = [
            {
                "id": "event_1",
                "summary": "Dinner Party",
                "description": "Hosting dinner for 6 people",
                "start": (now + timedelta(days=2)).isoformat(),
                "end": (now + timedelta(days=2, hours=4)).isoformat(),
                "meal_type": "dinner",
                "guests": 6,
                "ingredients_needed": ["chicken", "rice", "vegetables", "wine"],
            },
            {
                "id": "event_2",
                "summary": "Family Brunch",
                "description": "Sunday brunch with family",
                "start": (now + timedelta(days=5)).isoformat(),
                "end": (now + timedelta(days=5, hours=2)).isoformat(),
                "meal_type": "brunch",
                "guests": 4,
                "ingredients_needed": ["eggs", "bacon", "bread", "orange juice", "butter"],
            },
            {
                "id": "event_3",
                "summary": "Quick Lunch",
                "description": "Working from home lunch",
                "start": (now + timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1, hours=1)).isoformat(),
                "meal_type": "lunch",
                "guests": 1,
                "ingredients_needed": ["bread", "cheese", "lettuce"],
            },
        ]

    async def get_upcoming_events(
        self,
        user_id: str,
        days_ahead: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming calendar events with meal-related metadata.

        Returns mocked events in Phase 1.
        """
        logger.info(f"Fetching calendar events for user {user_id}")

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_ahead)

        upcoming = []
        for event in self._mock_events:
            event_start = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
            if now <= event_start <= cutoff:
                upcoming.append(event)

        return upcoming

    async def get_meal_events(
        self,
        user_id: str,
        days_ahead: int = 7,
    ) -> List[Dict[str, Any]]:
        """Get events that involve meals."""
        events = await self.get_upcoming_events(user_id, days_ahead)
        return [e for e in events if e.get("meal_type")]

    async def check_ingredient_availability(
        self,
        event_id: str,
        available_ingredients: List[str],
    ) -> Dict[str, Any]:
        """
        Check if ingredients for an event are available.

        Returns missing ingredients list.
        """
        event = next((e for e in self._mock_events if e["id"] == event_id), None)

        if not event:
            return {"error": "Event not found"}

        needed = set(i.lower() for i in event.get("ingredients_needed", []))
        available = set(i.lower() for i in available_ingredients)

        missing = list(needed - available)
        has_all = len(missing) == 0

        return {
            "event_id": event_id,
            "event_name": event["summary"],
            "ingredients_needed": list(needed),
            "ingredients_available": list(needed & available),
            "ingredients_missing": missing,
            "has_all_ingredients": has_all,
        }

    async def add_meal_event(
        self,
        user_id: str,
        summary: str,
        start_time: datetime,
        duration_hours: int = 2,
        meal_type: str = "dinner",
        guests: int = 1,
        ingredients: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add a new meal event (mocked)."""
        event_id = f"event_{len(self._mock_events) + 1}"

        new_event = {
            "id": event_id,
            "summary": summary,
            "start": start_time.isoformat(),
            "end": (start_time + timedelta(hours=duration_hours)).isoformat(),
            "meal_type": meal_type,
            "guests": guests,
            "ingredients_needed": ingredients or [],
        }

        self._mock_events.append(new_event)
        logger.info(f"Created mock calendar event: {event_id}")

        return new_event

    async def get_upcoming_meal_events(
        self,
        user_id: str,
        days_ahead: int = 7
    ) -> List[MealEvent]:
        """
        Get upcoming meal events as MealEvent objects.

        Args:
            user_id: User identifier
            days_ahead: Number of days to look ahead

        Returns:
            List of MealEvent objects
        """
        events = await self.get_meal_events(user_id, days_ahead)
        meal_events = []

        for event in events:
            try:
                event_date = datetime.fromisoformat(
                    event["start"].replace("Z", "+00:00")
                )
                meal_events.append(MealEvent(
                    event_id=event["id"],
                    title=event["summary"],
                    date=event_date,
                    meal_type=event.get("meal_type", "other"),
                    required_ingredients=event.get("ingredients_needed", []),
                    guests=event.get("guests", 1),
                    description=event.get("description", "")
                ))
            except (ValueError, KeyError) as e:
                logger.warning(f"Error parsing event {event.get('id')}: {e}")
                continue

        return meal_events

    async def extract_ingredients_from_event(
        self,
        event: MealEvent
    ) -> List[str]:
        """
        Extract ingredient requirements from a meal event.

        In production, this could use NLP to extract ingredients from
        event descriptions/titles.

        Args:
            event: MealEvent to extract ingredients from

        Returns:
            List of ingredient names
        """
        # For now, return the explicit ingredients list
        ingredients = list(event.required_ingredients)

        # Simple keyword extraction from title/description (could use NLP)
        common_ingredients = {
            "breakfast": ["eggs", "bread", "butter", "milk"],
            "brunch": ["eggs", "bacon", "bread", "orange juice"],
            "lunch": ["bread", "cheese", "lettuce"],
            "dinner": ["vegetables", "protein"],
        }

        # Add common ingredients for meal type if list is empty
        if not ingredients:
            ingredients = common_ingredients.get(event.meal_type, [])

        return ingredients

    async def check_inventory_for_event(
        self,
        event: MealEvent,
        inventory: List[Dict[str, Any]]
    ) -> MissingIngredients:
        """
        Check if inventory has required ingredients for an event.

        Args:
            event: MealEvent to check
            inventory: Current inventory items

        Returns:
            MissingIngredients result with missing/available lists
        """
        # Get required ingredients
        required = await self.extract_ingredients_from_event(event)
        required_lower = {i.lower() for i in required}

        # Build set of available items
        available_items = set()
        for item in inventory:
            name = item.get("name", "").lower()
            if name:
                available_items.add(name)
                # Also add variations (e.g., "eggs" matches "egg")
                if name.endswith("s"):
                    available_items.add(name[:-1])
                else:
                    available_items.add(name + "s")

        # Find matches and missing
        available = [i for i in required if i.lower() in available_items]
        missing = [i for i in required if i.lower() not in available_items]

        # Calculate urgency based on days until event
        days = event.days_away()
        if days <= 0.5:
            urgency = "urgent"
        elif days <= 1:
            urgency = "high"
        elif days <= 3:
            urgency = "medium"
        else:
            urgency = "low"

        return MissingIngredients(
            event=event,
            missing=missing,
            available=available,
            procurement_urgency=urgency
        )

    async def get_events_with_missing_ingredients(
        self,
        user_id: str,
        inventory: List[Dict[str, Any]],
        days_ahead: int = 7
    ) -> List[MissingIngredients]:
        """
        Get all upcoming events that have missing ingredients.

        Args:
            user_id: User identifier
            inventory: Current inventory items
            days_ahead: Days to look ahead

        Returns:
            List of MissingIngredients for events with gaps
        """
        events = await self.get_upcoming_meal_events(user_id, days_ahead)
        results = []

        for event in events:
            missing = await self.check_inventory_for_event(event, inventory)
            if missing.has_missing:
                results.append(missing)

        # Sort by urgency (urgent first)
        urgency_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        results.sort(key=lambda x: urgency_order.get(x.procurement_urgency, 4))

        return results


# Global calendar service instance
calendar_service = CalendarService()
