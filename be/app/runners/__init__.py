"""
Domus Runners Module

Background runners for proactive, event-driven notifications.
These are NOT agents - they run on timers, not user input.
"""

from .event_evaluator import EventEvaluationRunner, get_event_evaluator

__all__ = [
    'EventEvaluationRunner',
    'get_event_evaluator',
]
