"""
Base agent classes and intent definitions.

Agent Responsibility Boundaries:
- Level 0 (Orchestrator): User communication, external APIs, notification routing
- Level 1 (Domain Agents): Internal state management, intent emission ONLY
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Types of intents that L1 agents can emit."""

    # Fridge intents
    REQUIRE_PROCUREMENT = "require_procurement"
    DETECTED_EXPIRY = "detected_expiry"
    EXPIRY_WARNING = "expiry_warning"
    BULK_BUY_OPPORTUNITY = "bulk_buy_opportunity"
    INVENTORY_UPDATED = "inventory_updated"

    # Hardware intents
    HARDWARE_DISCONNECTED = "hardware_disconnected"
    HARDWARE_CONNECTED = "hardware_connected"

    # Analysis intents
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_FAILED = "analysis_failed"
    CONFIDENCE_DEGRADED = "confidence_degraded"

    # Temporal intents
    ITEM_ADDED = "item_added"
    ITEM_REMOVED = "item_removed"
    ITEM_MOVED = "item_moved"
    CONSUMPTION_LIKELY = "consumption_likely"

    # Calendar intents
    CALENDAR_EVENT_INGREDIENT_MISSING = "calendar_event_ingredient_missing"

    # State intents
    INVENTORY_IMBALANCE = "inventory_imbalance"


@dataclass
class AgentIntent:
    """
    Structured intent emitted by L1 agents.

    L1 agents can ONLY emit intents. They cannot:
    - Send notifications directly
    - Call external APIs
    - Generate user-visible responses
    """

    intent_type: IntentType
    payload: Dict[str, Any]
    intent_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_agent: str = ""
    household_id: Optional[str] = None
    confidence: float = 1.0
    reasoning: Optional[str] = None  # Agent's reasoning (for L0 review)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "intent_type": self.intent_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "source_agent": self.source_agent,
            "household_id": self.household_id,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class BaseAgent(ABC):
    """
    Base class for all agents.

    Provides common functionality and enforces boundaries.
    """

    def __init__(self, agent_id: str, agent_name: str, level: int):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.level = level
        self._is_running = False
        self._pending_intents: List[AgentIntent] = []
        logger.info(f"Agent initialized: {agent_name} (L{level})")

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def start(self):
        """Start the agent."""
        self._is_running = True
        logger.info(f"Agent started: {self.agent_name}")

    async def stop(self):
        """Stop the agent."""
        self._is_running = False
        logger.info(f"Agent stopped: {self.agent_name}")

    def emit_intent(self, intent: AgentIntent) -> None:
        """
        Emit an intent (L1 agents only).

        Intents are queued for the Orchestrator to process.
        """
        if self.level == 0:
            raise RuntimeError("L0 Orchestrator cannot emit intents")

        intent.source_agent = self.agent_name
        self._pending_intents.append(intent)
        logger.debug(f"Intent emitted: {intent.intent_type.value} from {self.agent_name}")

    def get_pending_intents(self) -> List[AgentIntent]:
        """Get and clear pending intents."""
        intents = self._pending_intents.copy()
        self._pending_intents.clear()
        return intents

    @abstractmethod
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input and return result.

        For L1 agents: Returns internal state updates, emits intents
        For L0 agents: Returns user-facing response
        """
        pass


class Level1Agent(BaseAgent):
    """
    Base class for Level 1 domain agents.

    Constraints enforced:
    - NO direct user notifications
    - NO direct external API calls
    - NO direct conversation output
    """

    def __init__(self, agent_id: str, agent_name: str):
        super().__init__(agent_id, agent_name, level=1)

    def _validate_no_user_output(self, result: Dict[str, Any]) -> None:
        """Ensure L1 agent isn't trying to output to user."""
        forbidden_keys = ["user_message", "notification", "response"]
        for key in forbidden_keys:
            if key in result:
                raise RuntimeError(
                    f"L1 agent {self.agent_name} attempted forbidden output: {key}"
                )


class Level0Agent(BaseAgent):
    """
    Base class for Level 0 orchestrator agent.

    Responsibilities:
    - Receives intents from L1 agents
    - Synthesizes with user context
    - Routes to external services
    - Owns all user conversation
    """

    def __init__(self, agent_id: str, agent_name: str):
        super().__init__(agent_id, agent_name, level=0)
        self._l1_agents: Dict[str, Level1Agent] = {}

    def register_l1_agent(self, agent: Level1Agent) -> None:
        """Register an L1 agent with the orchestrator."""
        self._l1_agents[agent.agent_id] = agent
        logger.info(f"L1 agent registered: {agent.agent_name}")

    def get_l1_agent(self, agent_id: str) -> Optional[Level1Agent]:
        """Get a registered L1 agent."""
        return self._l1_agents.get(agent_id)

    async def collect_intents(self) -> List[AgentIntent]:
        """Collect all pending intents from L1 agents."""
        all_intents = []
        for agent in self._l1_agents.values():
            intents = agent.get_pending_intents()
            all_intents.extend(intents)
        return all_intents
