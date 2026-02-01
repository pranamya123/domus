"""
Calendar Agent - Manages schedule and time-aware recommendations
"""

import logging
from typing import Optional
from datetime import datetime

from .base import BaseAgent, AgentType, AgentStatus, AgentContext, AgentResponse
from app.llm import GeminiService, get_gemini_service, SYSTEM_PROMPTS
from app.services.calendar_service import CalendarService, get_calendar_service

logger = logging.getLogger(__name__)


# Keywords that indicate calendar-related queries
CALENDAR_KEYWORDS = [
    'calendar', 'schedule', 'meeting', 'appointment', 'event',
    'today', 'tomorrow', 'tonight', 'this evening', 'this morning',
    'workout', 'gym', 'exercise', 'yoga', 'run', 'training',
    'busy', 'free', 'available', 'when', 'what time',
    'plan', 'plans', 'scheduled'
]


class CalendarAgent(BaseAgent):
    """
    Calendar Agent - Schedule-aware assistant.

    Capabilities:
    - Retrieve upcoming events
    - Identify workout/exercise schedules
    - Provide time-aware recommendations
    - Coordinate with other agents for meal timing
    """

    def __init__(
        self,
        llm_service: Optional[GeminiService] = None,
        calendar_service: Optional[CalendarService] = None
    ):
        super().__init__(AgentType.CALENDAR)
        self.llm = llm_service or get_gemini_service()
        self.calendar = calendar_service or get_calendar_service()
        self._tools = self._define_tools()

    def _define_tools(self) -> list[dict]:
        """Define the tools/functions this agent can use."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_today_events",
                    "description": "Get all events scheduled for today",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_upcoming_workouts",
                    "description": "Get upcoming workout or exercise events",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hours_ahead": {
                                "type": "integer",
                                "description": "Hours to look ahead (default 24)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_next_event",
                    "description": "Get the next upcoming event",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]

    def can_handle(self, message: str) -> bool:
        """Check if message is calendar-related."""
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in CALENDAR_KEYWORDS)

    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Process a calendar-related request.

        Args:
            context: Agent context with message and state

        Returns:
            AgentResponse with schedule information
        """
        self.status = AgentStatus.PROCESSING

        try:
            # Fetch calendar data
            today_events = await self.calendar.get_today_events(context.user_id)
            upcoming_workouts = await self.calendar.get_upcoming_workouts(context.user_id)

            # Build context for response
            schedule_context = self._format_schedule(today_events, upcoming_workouts)

            # Check if this is a simple schedule query or needs LLM
            if self._is_simple_query(context.message):
                response_content = schedule_context
            else:
                # Use LLM for more complex queries
                system_prompt = SYSTEM_PROMPTS.get("calendar", self._get_default_prompt())
                full_prompt = f"{system_prompt}\n\n{schedule_context}\n\nUser question: {context.message}"

                response = await self.llm.generate(
                    prompt=full_prompt,
                    chat_history=context.chat_history
                )
                response_content = response.content

            self.status = AgentStatus.COMPLETED

            return AgentResponse(
                content=response_content,
                agent_type=self.agent_type,
                status=self.status,
                metadata={
                    "events_today": len(today_events),
                    "upcoming_workouts": len(upcoming_workouts),
                    "has_workout_today": any(
                        w.get("event_type") == "workout"
                        for w in today_events
                    )
                }
            )

        except Exception as e:
            logger.error(f"Calendar agent error: {e}")
            self.status = AgentStatus.ERROR
            return AgentResponse(
                content="I encountered an error accessing your calendar. Please try again.",
                agent_type=self.agent_type,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )

    def _format_schedule(
        self,
        today_events: list[dict],
        upcoming_workouts: list[dict]
    ) -> str:
        """Format schedule data for context."""
        lines = ["**Today's Schedule:**"]

        if not today_events:
            lines.append("No events scheduled for today.")
        else:
            for event in sorted(today_events, key=lambda e: e["start_time"]):
                start = datetime.fromisoformat(event["start_time"])
                time_str = start.strftime("%I:%M %p")
                event_type = event.get("event_type", "")
                type_icon = self._get_event_icon(event_type)

                lines.append(f"• {time_str} - {type_icon} {event['title']}")
                if event.get("location"):
                    lines.append(f"  📍 {event['location']}")

        if upcoming_workouts:
            lines.append("\n**Upcoming Workouts:**")
            for workout in upcoming_workouts:
                start = datetime.fromisoformat(workout["start_time"])
                lines.append(f"• {start.strftime('%I:%M %p')} - {workout['title']}")

        return "\n".join(lines)

    def _get_event_icon(self, event_type: str) -> str:
        """Get icon for event type."""
        icons = {
            "workout": "🏋️",
            "meeting": "📅",
            "meal": "🍽️",
        }
        return icons.get(event_type, "📌")

    def _is_simple_query(self, message: str) -> bool:
        """Check if this is a simple schedule query."""
        simple_patterns = [
            "what's on my calendar",
            "what do i have today",
            "show my schedule",
            "my events",
        ]
        message_lower = message.lower()
        return any(pattern in message_lower for pattern in simple_patterns)

    def _get_default_prompt(self) -> str:
        """Get default system prompt for calendar agent."""
        return """You are a calendar assistant. Help users understand their schedule
and provide time-aware recommendations. When users ask about meals around workouts,
suggest optimal timing for pre and post-workout nutrition."""

    async def get_workout_context(self, user_id: str) -> Optional[dict]:
        """
        Get workout context for cross-agent coordination.

        Returns workout timing info for meal planning.
        """
        workouts = await self.calendar.get_upcoming_workouts(user_id, hours_ahead=12)
        if not workouts:
            return None

        next_workout = workouts[0]
        start = datetime.fromisoformat(next_workout["start_time"])

        return {
            "has_workout": True,
            "workout_title": next_workout["title"],
            "workout_time": start.strftime("%I:%M %p"),
            "workout_datetime": next_workout["start_time"],
            "hours_until": (start - datetime.now()).total_seconds() / 3600,
            "suggested_meal_time": self._suggest_meal_time(start),
        }

    def _suggest_meal_time(self, workout_time: datetime) -> str:
        """Suggest optimal meal time relative to workout."""
        # Suggest eating 2-3 hours before workout
        from datetime import timedelta
        meal_time = workout_time - timedelta(hours=2)
        return meal_time.strftime("%I:%M %p")
