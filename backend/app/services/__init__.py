"""
Services layer for Domus.

LLM Usage & Arbitration:
- LLM calls are owned by services, not agents directly
- Level 1 agents may request reasoning via a service interface
- The Orchestrator may override agent conclusions or request re-analysis
"""

from app.services.vision_service import VisionService, vision_service
from app.services.calendar_service import CalendarService, calendar_service
from app.services.instacart_service import InstacartService, instacart_service
from app.services.notification_service import NotificationService, notification_service

__all__ = [
    "VisionService",
    "vision_service",
    "CalendarService",
    "calendar_service",
    "InstacartService",
    "instacart_service",
    "NotificationService",
    "notification_service",
]
