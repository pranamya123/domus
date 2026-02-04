"""
Calendar Service - Mock Google Calendar Integration

TODO: Replace with real Google Calendar API integration
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None  # workout, meeting, meal, prep_required, etc.
    requires_prep: bool = False  # True for events needing food preparation
    prep_type: Optional[str] = None  # baking, cooking, shopping, etc.
    suggested_items: Optional[list[str]] = None  # Suggested items to prepare


class CalendarService:
    """
    Mock Calendar Service for development.

    Provides realistic calendar data for testing meal planning
    and schedule-aware recommendations.
    """

    def __init__(self):
        self._mock_events: dict[str, list[CalendarEvent]] = {}
        logger.info("CalendarService initialized (mock mode)")

    def _get_mock_events(self, user_id: str) -> list[CalendarEvent]:
        """Generate mock events for today and tomorrow."""
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        return [
            # Today's events
            CalendarEvent(
                id="evt_001",
                title="Morning Standup",
                start_time=today.replace(hour=9, minute=0),
                end_time=today.replace(hour=9, minute=30),
                location="Zoom",
                event_type="meeting"
            ),
            CalendarEvent(
                id="evt_002",
                title="Lunch with Sarah",
                start_time=today.replace(hour=12, minute=30),
                end_time=today.replace(hour=13, minute=30),
                location="Cafe Milano",
                event_type="meal"
            ),
            CalendarEvent(
                id="evt_003",
                title="Gym - Leg Day",
                start_time=today.replace(hour=18, minute=0),
                end_time=today.replace(hour=19, minute=30),
                location="FitLife Gym",
                description="Leg workout + cardio",
                event_type="workout"
            ),
            # Tomorrow's events
            CalendarEvent(
                id="evt_004",
                title="Team Planning",
                start_time=(today + timedelta(days=1)).replace(hour=10, minute=0),
                end_time=(today + timedelta(days=1)).replace(hour=11, minute=0),
                location="Conference Room A",
                event_type="meeting"
            ),
            CalendarEvent(
                id="evt_005",
                title="Yoga Class",
                start_time=(today + timedelta(days=1)).replace(hour=7, minute=0),
                end_time=(today + timedelta(days=1)).replace(hour=8, minute=0),
                location="Zen Studio",
                event_type="workout"
            ),
            # Prep-required events (bake sale, dinner party, potluck)
            CalendarEvent(
                id="evt_006",
                title="School Bake Sale",
                start_time=(today + timedelta(days=1)).replace(hour=14, minute=0),
                end_time=(today + timedelta(days=1)).replace(hour=17, minute=0),
                location="Lincoln Elementary School",
                description="Bring baked goods for the school fundraiser",
                event_type="prep_required",
                requires_prep=True,
                prep_type="baking",
                suggested_items=["flour", "sugar", "butter", "eggs", "vanilla extract", "baking powder", "chocolate chips"]
            ),
            CalendarEvent(
                id="evt_007",
                title="Dinner Party at Home",
                start_time=(today + timedelta(days=2)).replace(hour=19, minute=0),
                end_time=(today + timedelta(days=2)).replace(hour=22, minute=0),
                location="Home",
                description="Hosting 6 guests for dinner",
                event_type="prep_required",
                requires_prep=True,
                prep_type="cooking",
                suggested_items=["chicken", "pasta", "garlic", "olive oil", "parmesan", "salad greens", "wine"]
            ),
            CalendarEvent(
                id="evt_008",
                title="Office Potluck",
                start_time=(today + timedelta(days=3)).replace(hour=12, minute=0),
                end_time=(today + timedelta(days=3)).replace(hour=14, minute=0),
                location="Office Kitchen",
                description="Monthly team potluck - bringing a main dish",
                event_type="prep_required",
                requires_prep=True,
                prep_type="cooking",
                suggested_items=["ground beef", "taco shells", "cheese", "lettuce", "tomatoes", "sour cream", "salsa"]
            ),
        ]

    async def get_events(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> list[dict]:
        """
        Get calendar events for a user within a date range.

        Args:
            user_id: User identifier
            start_date: Start of date range (defaults to now)
            end_date: End of date range (defaults to 24h from now)

        Returns:
            List of event dictionaries
        """
        start = start_date or datetime.now()
        end = end_date or (start + timedelta(hours=24))

        events = self._get_mock_events(user_id)

        # Filter events within range
        filtered = [
            e for e in events
            if start <= e.start_time <= end
        ]

        logger.info(
            "Calendar events fetched (user=%s, range=%s to %s, count=%d)",
            user_id, start.isoformat(), end.isoformat(), len(filtered)
        )

        return [self._event_to_dict(e) for e in filtered]

    async def get_today_events(self, user_id: str) -> list[dict]:
        """Get all events for today."""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return await self.get_events(user_id, start, end)

    async def get_upcoming_workouts(
        self,
        user_id: str,
        hours_ahead: int = 24
    ) -> list[dict]:
        """Get upcoming workout events."""
        events = await self.get_events(
            user_id,
            datetime.now(),
            datetime.now() + timedelta(hours=hours_ahead)
        )
        return [e for e in events if e.get("event_type") == "workout"]

    async def get_next_event(self, user_id: str) -> Optional[dict]:
        """Get the next upcoming event."""
        events = await self.get_events(user_id)
        if events:
            return min(events, key=lambda e: e["start_time"])
        return None

    async def get_prep_required_events(
        self,
        user_id: str,
        days_ahead: int = 7
    ) -> list[dict]:
        """
        Get upcoming events that require food preparation.

        These are events like bake sales, dinner parties, potlucks
        that need advance shopping and cooking.

        Args:
            user_id: User identifier
            days_ahead: How many days ahead to look (default 7)

        Returns:
            List of prep-required events with suggested items
        """
        start = datetime.now()
        end = start + timedelta(days=days_ahead)
        events = self._get_mock_events(user_id)

        # Filter to prep-required events within range
        prep_events = [
            e for e in events
            if e.requires_prep and start <= e.start_time <= end
        ]

        logger.info(
            "Prep-required events fetched (user=%s, days_ahead=%d, count=%d)",
            user_id, days_ahead, len(prep_events)
        )

        return [self._event_to_dict(e) for e in sorted(prep_events, key=lambda e: e.start_time)]

    async def get_event_by_keyword(
        self,
        user_id: str,
        keyword: str,
        days_ahead: int = 7
    ) -> Optional[dict]:
        """
        Find an event by keyword in the title.

        Args:
            user_id: User identifier
            keyword: Keyword to search for (case-insensitive)
            days_ahead: How many days ahead to look

        Returns:
            First matching event or None
        """
        start = datetime.now()
        end = start + timedelta(days=days_ahead)
        events = self._get_mock_events(user_id)

        keyword_lower = keyword.lower()
        for event in events:
            if keyword_lower in event.title.lower() and start <= event.start_time <= end:
                return self._event_to_dict(event)

        return None

    def _event_to_dict(self, event: CalendarEvent) -> dict:
        """Convert CalendarEvent to dictionary."""
        result = {
            "id": event.id,
            "title": event.title,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat(),
            "location": event.location,
            "description": event.description,
            "event_type": event.event_type,
            "requires_prep": event.requires_prep,
        }
        # Add prep-specific fields if applicable
        if event.requires_prep:
            result["prep_type"] = event.prep_type
            result["suggested_items"] = event.suggested_items or []
        return result


# Singleton instance
_calendar_service: Optional[CalendarService] = None


def get_calendar_service() -> CalendarService:
    """Get or create the singleton calendar service instance."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = CalendarService()
    return _calendar_service
