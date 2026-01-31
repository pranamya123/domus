"""
Base Agent Class for Domus
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of agents in Domus"""
    ORCHESTRATOR = "orchestrator"
    FRIDGE = "DFridge"
    CALENDAR = "DCalendar"
    ENERGY = "DEnergy"
    SECURITY = "DSecurity"
    SERVICES = "DServices"
    NOTIFICATION = "DNotification"


class AgentStatus(str, Enum):
    """Agent status states"""
    IDLE = "idle"
    ACTIVATING = "activating"
    ACTIVE = "active"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentResponse:
    """Structured response from an agent"""
    content: str
    agent_type: AgentType
    status: AgentStatus = AgentStatus.COMPLETED
    metadata: dict = field(default_factory=dict)
    tool_results: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    requires_approval: bool = False
    approval_data: Optional[dict] = None


@dataclass
class AgentContext:
    """Context passed to agents for processing"""
    user_id: str
    session_id: str
    message: str
    chat_history: list[dict] = field(default_factory=list)
    inventory: Optional[dict] = None
    calendar_events: Optional[list] = None
    energy_data: Optional[dict] = None
    security_status: Optional[dict] = None
    user_preferences: Optional[dict] = None


class BaseAgent(ABC):
    """
    Base class for all Domus agents.

    Each agent specializes in a specific domain (fridge, calendar, etc.)
    and uses the LLM service to generate intelligent responses.
    """

    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type
        self._status = AgentStatus.IDLE
        self._tools: list[dict] = []

    @property
    def status(self) -> AgentStatus:
        return self._status

    @status.setter
    def status(self, value: AgentStatus):
        self._status = value
        logger.info(f"Agent {self.agent_type} status: {value}")

    @abstractmethod
    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Process a user request and return a response.

        Args:
            context: The agent context with user message and state

        Returns:
            AgentResponse with the agent's response
        """
        pass

    @abstractmethod
    def can_handle(self, message: str) -> bool:
        """
        Determine if this agent can handle the given message.

        Args:
            message: The user's message

        Returns:
            True if this agent should handle the message
        """
        pass

    def get_tools(self) -> list[dict]:
        """Get the tools/functions this agent can use"""
        return self._tools

    async def activate(self) -> None:
        """Activate the agent"""
        self.status = AgentStatus.ACTIVATING
        # Perform any initialization
        self.status = AgentStatus.ACTIVE

    async def deactivate(self) -> None:
        """Deactivate the agent"""
        self.status = AgentStatus.IDLE
