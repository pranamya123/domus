"""
Domus Orchestrator - Routes messages to appropriate agents

Coordinates multi-agent workflows for complex queries that span
multiple domains (e.g., meal planning with workout schedule).
"""

import logging
from enum import Enum
from typing import Optional, Callable, Awaitable

from .base import BaseAgent, AgentType, AgentStatus, AgentContext, AgentResponse
from .fridge_agent import FridgeAgent
from .calendar_agent import CalendarAgent
from .instacart_agent import InstacartAgent
from app.llm import GeminiService, get_gemini_service, SYSTEM_PROMPTS

logger = logging.getLogger(__name__)


# =============================================================================
# Intent Detection & Agent Bundles
# =============================================================================

class Intent(str, Enum):
    """User intent categories that map to agent bundles."""
    NUTRITION_WITH_ACTIVITY = "nutrition_with_activity"  # meal + workout/schedule
    MEAL_PLANNING = "meal_planning"                      # meal + schedule
    SHOPPING_FOR_MEAL = "shopping_for_meal"              # meal + shopping
    FRIDGE_ONLY = "fridge_only"                          # just fridge
    CALENDAR_ONLY = "calendar_only"                      # just calendar
    SHOPPING_ONLY = "shopping_only"                      # just shopping
    GENERAL = "general"                                  # no specific intent


# Intent → Agent Bundle mapping (deterministic)
INTENT_AGENT_BUNDLES: dict[Intent, list[AgentType]] = {
    Intent.NUTRITION_WITH_ACTIVITY: [AgentType.FRIDGE, AgentType.CALENDAR, AgentType.INSTACART],
    Intent.MEAL_PLANNING: [AgentType.FRIDGE, AgentType.CALENDAR],
    Intent.SHOPPING_FOR_MEAL: [AgentType.FRIDGE, AgentType.INSTACART],
    Intent.FRIDGE_ONLY: [AgentType.FRIDGE],
    Intent.CALENDAR_ONLY: [AgentType.CALENDAR],
    Intent.SHOPPING_ONLY: [AgentType.INSTACART],
    Intent.GENERAL: [],
}


# Intent detection rules (keyword patterns)
INTENT_PATTERNS: dict[Intent, list[tuple[str, ...]]] = {
    Intent.NUTRITION_WITH_ACTIVITY: [
        ('workout', 'eat'), ('gym', 'eat'), ('exercise', 'meal'),
        ('training', 'food'), ('workout', 'meal'), ('workout', 'dinner'),
        ('gym', 'food'), ('exercise', 'eat'),
    ],
    Intent.MEAL_PLANNING: [
        ('tonight', 'eat'), ('tonight', 'dinner'), ('today', 'cook'),
        ('tomorrow', 'meal'), ('week', 'meal'), ('plan', 'meal'),
    ],
    Intent.SHOPPING_FOR_MEAL: [
        ('need', 'cook'), ('buy', 'dinner'), ('shop', 'meal'),
        ('missing', 'recipe'), ('groceries', 'meal'),
    ],
}


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
        """Initialize all available agents."""
        self._agents[AgentType.FRIDGE] = FridgeAgent(self.llm)
        self._agents[AgentType.CALENDAR] = CalendarAgent(self.llm)
        self._agents[AgentType.INSTACART] = InstacartAgent(self.llm)
        # TODO: Add more agents as needed
        # self._agents[AgentType.ENERGY] = EnergyAgent(self.llm)
        # self._agents[AgentType.SECURITY] = SecurityAgent(self.llm)

        logger.info(f"Initialized {len(self._agents)} agents: {list(self._agents.keys())}")

    def detect_intent(self, message: str) -> Intent:
        """
        Detect user intent from message.

        Maps to an agent bundle for execution.
        """
        message_lower = message.lower()

        # Check multi-agent intents first (most specific)
        for intent, patterns in INTENT_PATTERNS.items():
            for keywords in patterns:
                if all(kw in message_lower for kw in keywords):
                    logger.info("Detected intent: %s (keywords: %s)", intent, keywords)
                    return intent

        # Ensure workout + nutrition requests trigger fridge even without explicit fridge mention.
        workout_keywords = ['workout', 'gym', 'exercise', 'training']
        nutrition_keywords = ['meal', 'eat', 'food', 'snack', 'protein', 'carb', 'calorie', 'macro', 'nutrition']
        if any(kw in message_lower for kw in workout_keywords) and any(kw in message_lower for kw in nutrition_keywords):
            return Intent.NUTRITION_WITH_ACTIVITY

        # Fall back to single-agent detection
        if any(kw in message_lower for kw in ['fridge', 'food', 'eat', 'cook', 'meal', 'ingredient']):
            return Intent.FRIDGE_ONLY
        if any(kw in message_lower for kw in ['calendar', 'schedule', 'workout', 'gym', 'tonight', 'today']):
            return Intent.CALENDAR_ONLY
        if any(kw in message_lower for kw in ['buy', 'shop', 'cart', 'order', 'instacart']):
            return Intent.SHOPPING_ONLY

        return Intent.GENERAL

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
        if any(word in message_lower for word in ['calendar', 'schedule', 'meeting', 'appointment', 'event', 'reminder', 'tonight', 'today']):
            return AgentType.CALENDAR

        if any(word in message_lower for word in ['buy', 'shop', 'cart', 'instacart', 'order', 'delivery']):
            return AgentType.INSTACART

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
        status_callback: Optional[Callable[[AgentType, AgentStatus, str], Awaitable[None]]] = None,
        **kwargs
    ) -> tuple[AgentResponse, Optional[AgentType]]:
        """
        Process a user message and return a response.

        Uses intent detection to determine which agent bundle to execute.

        Args:
            message: User's message
            user_id: User ID
            session_id: Session ID
            chat_history: Previous conversation messages
            inventory: Current fridge inventory
            status_callback: Optional async callback for agent status updates
                             Signature: (agent_type, status, message) -> None
            **kwargs: Additional context data

        Returns:
            Tuple of (AgentResponse, detected AgentType)
        """
        self._status_callback = status_callback
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

        # Step 1: Detect intent
        intent = self.detect_intent(message)
        agent_bundle = INTENT_AGENT_BUNDLES.get(intent, [])

        logger.info("Intent: %s → Agents: %s", intent, [a.value for a in agent_bundle])

        # Step 2: Execute agent bundle
        if len(agent_bundle) > 1:
            # Multi-agent coordination
            response = await self._execute_agent_bundle(context, intent, agent_bundle)
            return response, AgentType.ORCHESTRATOR

        elif len(agent_bundle) == 1:
            # Single agent - emit status before and after processing
            agent_type = agent_bundle[0]
            if agent_type in self._agents:
                agent = self._agents[agent_type]
                self._active_agent = agent_type

                # Emit status before fetching response
                await self._emit_status(
                    agent_type,
                    AgentStatus.PROCESSING,
                    f"Consulting {agent_type.value}..."
                )

                response = await agent.process(context)

                # Emit completion status
                await self._emit_status(
                    agent_type,
                    AgentStatus.COMPLETED,
                    f"{agent_type.value} complete"
                )

                return response, agent_type

        # Step 3: Fallback to general chat - emit status before fetching response
        logger.info("No specific agent bundle, handling as general chat")

        await self._emit_status(
            AgentType.ORCHESTRATOR,
            AgentStatus.PROCESSING,
            "Thinking..."
        )

        response = await self._handle_general_chat(context)

        await self._emit_status(
            AgentType.ORCHESTRATOR,
            AgentStatus.COMPLETED,
            "Response ready"
        )

        return response, None

    async def _emit_status(
        self,
        agent_type: AgentType,
        status: AgentStatus,
        message: str
    ) -> None:
        """Emit agent status update via callback if available."""
        if self._status_callback:
            try:
                await self._status_callback(agent_type, status, message)
            except Exception as e:
                logger.warning("Status callback error: %s", e)

    async def _execute_agent_bundle(
        self,
        context: AgentContext,
        intent: Intent,
        agent_bundle: list[AgentType]
    ) -> AgentResponse:
        """
        Execute a bundle of agents and synthesize results.

        Each agent in the bundle is queried, then LLM decides
        which results are relevant for the final response.
        """
        results: dict[str, any] = {"intent": intent.value}

        # Emit orchestrator coordinating status
        await self._emit_status(
            AgentType.ORCHESTRATOR,
            AgentStatus.PROCESSING,
            f"Coordinating {len(agent_bundle)} agents..."
        )

        try:
            # Execute each agent in the bundle
            for agent_type in agent_bundle:
                agent = self._agents.get(agent_type)
                if not agent:
                    continue

                # Emit agent activation status
                agent_name = agent_type.value
                await self._emit_status(
                    agent_type,
                    AgentStatus.ACTIVATING,
                    f"Consulting {agent_name}..."
                )

                logger.info("Executing agent: %s", agent_type.value)

                if agent_type == AgentType.FRIDGE:
                    response = await agent.process(context)
                    results["fridge"] = {
                        "content": response.content,
                        "available": True
                    }
                    await self._emit_status(
                        agent_type,
                        AgentStatus.COMPLETED,
                        "Analyzed fridge contents"
                    )

                elif agent_type == AgentType.CALENDAR:
                    workout_ctx = await agent.get_workout_context(context.user_id)
                    events = await agent.calendar.get_today_events(context.user_id)
                    results["calendar"] = {
                        "workout": workout_ctx,
                        "events": events,
                        "available": True
                    }
                    workout_msg = "Found workout scheduled" if workout_ctx and workout_ctx.get("has_workout") else "No workout found"
                    await self._emit_status(
                        agent_type,
                        AgentStatus.COMPLETED,
                        workout_msg
                    )

                elif agent_type == AgentType.INSTACART:
                    # Get fridge items for cross-reference
                    fridge_items = self._extract_items_from_response(
                        results.get("fridge", {}).get("content", "")
                    )
                    # Determine activity type from calendar
                    activity = "workout" if results.get("calendar", {}).get("workout") else None

                    suggestions = await agent.instacart.suggest_missing_items(
                        context.user_id,
                        fridge_items,
                        activity_type=activity
                    )
                    cart = await agent.instacart.get_cart(context.user_id)

                    # Auto-add recommended items if workout scheduled
                    cart_additions = []
                    if activity == "workout" and suggestions:
                        for item in suggestions[:1]:  # Add top suggestion
                            if "protein" in item.get("name", "").lower():
                                add_result = await agent.instacart.add_to_cart(
                                    context.user_id,
                                    item["product_key"]
                                )
                                if add_result.get("success"):
                                    cart_additions.append(item["name"])

                    results["instacart"] = {
                        "suggestions": suggestions,
                        "cart": cart,
                        "auto_added": cart_additions,
                        "available": True
                    }
                    cart_msg = f"Added {', '.join(cart_additions)} to cart" if cart_additions else "Checked shopping suggestions"
                    await self._emit_status(
                        agent_type,
                        AgentStatus.COMPLETED,
                        cart_msg
                    )

            # Emit synthesizing status
            await self._emit_status(
                AgentType.ORCHESTRATOR,
                AgentStatus.PROCESSING,
                "Synthesizing response..."
            )

            # Synthesize final response (LLM decides relevance)
            response_content = await self._synthesize_with_relevance(context, results)

            return AgentResponse(
                content=response_content,
                agent_type=AgentType.ORCHESTRATOR,
                status=AgentStatus.COMPLETED,
                metadata={
                    "intent": intent.value,
                    "agents_executed": [a.value for a in agent_bundle],
                    "multi_agent": True
                }
            )

        except Exception as e:
            logger.error("Agent bundle execution error: %s", e)
            return AgentResponse(
                content="I encountered an error processing your request. Please try again.",
                agent_type=AgentType.ORCHESTRATOR,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )

    async def _synthesize_with_relevance(
        self,
        context: AgentContext,
        results: dict
    ) -> str:
        """
        Synthesize response with LLM deciding relevance of each source.

        The LLM is given all agent results but instructed to only use
        sources that are relevant to the user's question.
        """
        # Format each data source
        fridge_data = self._format_fridge_data(results.get("fridge", {}))
        calendar_data = self._format_calendar_data(results.get("calendar", {}))
        instacart_data = self._format_instacart_data(results.get("instacart", {}))

        synthesis_prompt = f"""You are given data from multiple sources. Answer the user's question using ONLY the sources that are relevant.

**User Question:** {context.message}

---
**SOURCE 1: Fridge Contents** (from camera vision analysis)
{fridge_data}

---
**SOURCE 2: Calendar/Schedule**
{calendar_data}

---
**SOURCE 3: Shopping/Instacart**
{instacart_data}

---

**Instructions:**
- Only mention a source if it directly helps answer the question
- If a source isn't relevant, don't mention it at all
- It's OK to ignore any source entirely if it doesn't add value
- Be specific: use actual item names, times, and prices when relevant
- Keep the response concise and actionable
- If items were auto-added to cart, mention it naturally at the end
"""

        response = await self.llm.generate(
            prompt=synthesis_prompt,
            system_prompt="You are Domus, a helpful smart home assistant. Give concise, actionable advice."
        )

        return response.content

    def _format_fridge_data(self, fridge: dict) -> str:
        """Format fridge data for synthesis prompt."""
        if not fridge.get("available"):
            return "Not available"

        # Pass fridge agent output unchanged into synthesis (required for context-aware meals).
        return fridge.get("content", "")

    def _format_calendar_data(self, calendar: dict) -> str:
        """Format calendar data for synthesis prompt."""
        if not calendar.get("available"):
            return "Not available"

        lines = []

        # Workout info
        workout = calendar.get("workout")
        if workout and workout.get("has_workout"):
            lines.append(f"🏋️ Upcoming workout: {workout.get('workout_title', 'Workout')}")
            lines.append(f"   Time: {workout.get('workout_time', 'Unknown')}")
            lines.append(f"   Suggested pre-workout meal: {workout.get('suggested_meal_time', 'Unknown')}")
        else:
            lines.append("No workout scheduled in the next 12 hours")

        # Other events
        events = calendar.get("events", [])
        if events:
            lines.append(f"\nOther events today: {len(events)} scheduled")

        return "\n".join(lines) if lines else "No calendar data"

    def _format_instacart_data(self, instacart: dict) -> str:
        """Format instacart data for synthesis prompt."""
        if not instacart.get("available"):
            return "Not available"

        lines = []

        # Suggestions
        suggestions = instacart.get("suggestions", [])
        if suggestions:
            lines.append("Missing items you might need:")
            for item in suggestions[:3]:
                lines.append(f"  • {item.get('name', 'Unknown')} - ${item.get('price', 0):.2f}")

        # Auto-added items
        auto_added = instacart.get("auto_added", [])
        if auto_added:
            lines.append(f"\n✅ Auto-added to cart: {', '.join(auto_added)}")

        # Cart summary
        cart = instacart.get("cart", {})
        if cart.get("item_count", 0) > 0:
            lines.append(f"\nCart total: ${cart.get('total', 0):.2f} ({cart.get('item_count', 0)} items)")

        return "\n".join(lines) if lines else "No shopping data"

    def _extract_items_from_response(self, fridge_response: str) -> list[str]:
        """Extract item names from fridge agent response."""
        # Simple extraction - look for common food items
        common_items = [
            "chicken", "spinach", "eggs", "milk", "yogurt", "cheese",
            "lettuce", "tomato", "carrot", "broccoli", "salmon", "beef",
            "rice", "pasta", "bread", "avocado", "banana", "apple"
        ]
        response_lower = fridge_response.lower()
        return [item for item in common_items if item in response_lower]

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
