"""
Agent system for Domus.

Hierarchy:
- Level 0: Domus Orchestrator - owns user communication, external APIs
- Level 1: Domain agents (DomusFridge) - emit intents only
"""

from app.agents.base import BaseAgent, AgentIntent, IntentType
from app.agents.domus_orchestrator import DomusOrchestrator
from app.agents.domus_fridge import DomusFridge

__all__ = [
    "BaseAgent",
    "AgentIntent",
    "IntentType",
    "DomusOrchestrator",
    "DomusFridge",
]
