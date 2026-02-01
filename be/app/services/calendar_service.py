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
    event_type: Optional[str] = None  # workout, meeting, meal, etc.


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

    def _event_to_dict(self, event: CalendarEvent) -> dict:
        """Convert CalendarEvent to dictionary."""
        return {
            "id": event.id,
            "title": event.title,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat(),
            "location": event.location,
            "description": event.description,
            "event_type": event.event_type,
        }


# Singleton instance
_calendar_service: Optional[CalendarService] = None


def get_calendar_service() -> CalendarService:
    """Get or create the singleton calendar service instance."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = CalendarService()
    return _calendar_service
