"""
Domus Orchestrator - Routes messages to appropriate agents
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentType, AgentStatus, AgentContext, AgentResponse
from .fridge_agent import FridgeAgent
from app.llm import GeminiService, get_gemini_service, SYSTEM_PROMPTS

logger = logging.getLogger(__name__)


class DomusOrchestrator:
    """
    Main orchestrator for Domus smart home assistant.

    Responsibilities:
    - Route user messages to appropriate agents
    - Manage agent lifecycle
    - Maintain conversation context
    - Handle multi-agent workflows
    """

    def __init__(self, llm_service: Optional[GeminiService] = None):
        self.llm = llm_service or get_gemini_service()
        self._agents: dict[AgentType, BaseAgent] = {}
        self._active_agent: Optional[AgentType] = None

        # Initialize agents
        self._initialize_agents()

    def _initialize_agents(self):
        """Initialize all available agents"""
        self._agents[AgentType.FRIDGE] = FridgeAgent(self.llm)
        # Add more agents as they're implemented
        # self._agents[AgentType.CALENDAR] = CalendarAgent(self.llm)
        # self._agents[AgentType.ENERGY] = EnergyAgent(self.llm)
        # self._agents[AgentType.SECURITY] = SecurityAgent(self.llm)

        logger.info(f"Initialized {len(self._agents)} agents")

    def detect_agent(self, message: str) -> Optional[AgentType]:
        """
        Detect which agent should handle the message.

        Args:
            message: User's message

        Returns:
            AgentType if a specific agent should handle it, None for general chat
        """
        message_lower = message.lower()

        # Check each agent's ability to handle the message
        for agent_type, agent in self._agents.items():
            if agent.can_handle(message):
                return agent_type

        # Keyword-based fallback detection
        if any(word in message_lower for word in ['calendar', 'schedule', 'meeting', 'appointment', 'event', 'reminder']):
            return AgentType.CALENDAR

        if any(word in message_lower for word in ['energy', 'electricity', 'power', 'bill', 'thermostat', 'temperature']):
            return AgentType.ENERGY

        if any(word in message_lower for word in ['security', 'camera', 'lock', 'door', 'alarm', 'motion']):
            return AgentType.SECURITY

        return None

    async def process_message(
        self,
        message: str,
        user_id: str,
        session_id: str,
        chat_history: Optional[list[dict]] = None,
        inventory: Optional[dict] = None,
        **kwargs
    ) -> tuple[AgentResponse, Optional[AgentType]]:
        """
        Process a user message and return a response.

        Args:
            message: User's message
            user_id: User ID
            session_id: Session ID
            chat_history: Previous conversation messages
            inventory: Current fridge inventory
            **kwargs: Additional context data

        Returns:
            Tuple of (AgentResponse, detected AgentType)
        """
        # Detect which agent should handle this
        detected_agent = self.detect_agent(message)

        # Build context
        context = AgentContext(
            user_id=user_id,
            session_id=session_id,
            message=message,
            chat_history=chat_history or [],
            inventory=inventory,
            calendar_events=kwargs.get("calendar_events"),
            energy_data=kwargs.get("energy_data"),
            security_status=kwargs.get("security_status"),
            user_preferences=kwargs.get("user_preferences")
        )

        # If a specific agent is detected, use it
        if detected_agent and detected_agent in self._agents:
            agent = self._agents[detected_agent]
            self._active_agent = detected_agent

            logger.info(f"Routing to agent: {detected_agent}")
            response = await agent.process(context)
            return response, detected_agent

        # For general queries, use the orchestrator's LLM directly
        logger.info("Handling as general chat")
        response = await self._handle_general_chat(context)
        return response, None

    async def _handle_general_chat(self, context: AgentContext) -> AgentResponse:
        """Handle general chat that doesn't need a specific agent"""
        try:
            system_prompt = SYSTEM_PROMPTS.get("orchestrator", "")

            response = await self.llm.generate(
                prompt=context.message,
                system_prompt=system_prompt,
                chat_history=context.chat_history
            )

            return AgentResponse(
                content=response.content,
                agent_type=AgentType.ORCHESTRATOR,
                status=AgentStatus.COMPLETED,
                metadata={"model": "gemini"}
            )

        except Exception as e:
            logger.error(f"General chat error: {e}")
            return AgentResponse(
                content="Hello! I'm Domus, your smart home assistant. How can I help you today?",
                agent_type=AgentType.ORCHESTRATOR,
                status=AgentStatus.COMPLETED
            )

    def get_agent_status(self, agent_type: AgentType) -> AgentStatus:
        """Get the status of a specific agent"""
        if agent_type in self._agents:
            return self._agents[agent_type].status
        return AgentStatus.IDLE

    def get_active_agent(self) -> Optional[AgentType]:
        """Get the currently active agent"""
        return self._active_agent

    async def activate_agent(self, agent_type: AgentType) -> bool:
        """Activate a specific agent"""
        if agent_type in self._agents:
            await self._agents[agent_type].activate()
            self._active_agent = agent_type
            return True
        return False

    async def deactivate_agent(self, agent_type: AgentType) -> bool:
        """Deactivate a specific agent"""
        if agent_type in self._agents:
            await self._agents[agent_type].deactivate()
            if self._active_agent == agent_type:
                self._active_agent = None
            return True
        return False


# Singleton instance
_orchestrator: Optional[DomusOrchestrator] = None


def get_orchestrator() -> DomusOrchestrator:
    """Get or create the singleton orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DomusOrchestrator()
    return _orchestrator
