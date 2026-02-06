"""
Domus Orchestrator - Routes messages to appropriate agents

Coordinates multi-agent workflows for complex queries that span
multiple domains (e.g., meal planning with workout schedule).
"""

import logging
from enum import Enum
from typing import Optional, Callable, Awaitable

from .base import (
    BaseAgent, AgentType, AgentStatus, AgentContext, AgentResponse,
    ConversationState, InteractionPhase, ShoppingContext
)
from .fridge_agent import FridgeAgent
from .calendar_agent import CalendarAgent
from .instacart_agent import InstacartAgent
from app.llm import GeminiService, get_gemini_service, SYSTEM_PROMPTS, AGENT_PROMPTS

logger = logging.getLogger(__name__)


# =============================================================================
# Short Reply Expansion
# =============================================================================
# When user sends a short acknowledgment mid-conversation, expand it to include context

SHORT_REPLY_PATTERNS = {
    # Affirmative responses - trigger show options when in OFFERED_OPTIONS phase
    "yes": "Yes, please show me the options.",
    "yes please": "Yes, please show me the options.",
    "sure": "Sure, please show me the options.",
    "ok": "OK, please show me the options.",
    "okay": "OK, please show me the options.",
    "yep": "Yes, please show me the options.",
    "yeah": "Yes, please show me the options.",
    "go ahead": "Go ahead and show me the options.",
    "sounds good": "Sounds good, please show me the options.",

    # Explicit show options
    "show options": "Please show me the budget meal options.",
    "show me options": "Please show me the budget meal options.",
    "show the options": "Please show me the budget meal options.",
    "what are the options": "What are the budget meal options?",
    "tell me more": "Tell me more about the budget meal options.",
    "more details": "Please give me more details on the options.",
    "which options": "Which budget meal options do you have?",
}


def is_short_reply(message: str) -> bool:
    """Check if a message is a short reply that needs context expansion."""
    # Short replies are typically < 5 words and contain common acknowledgment patterns
    words = message.strip().split()
    if len(words) > 6:
        return False

    message_lower = message.lower().strip().rstrip('?!.')
    return message_lower in SHORT_REPLY_PATTERNS or len(words) <= 2


def expand_short_reply(message: str, conv_state: ConversationState) -> str:
    """
    Expand a short reply into a full instruction with context.

    When the user says "Yes" after we offered options, expand it to:
    "Yes, please show me the budget meal options."
    """
    message_lower = message.lower().strip().rstrip('?!.')

    # Check for exact match in patterns
    if message_lower in SHORT_REPLY_PATTERNS:
        expanded = SHORT_REPLY_PATTERNS[message_lower]
        logger.info(f"Expanded '{message}' → '{expanded}' (phase: {conv_state.interaction_phase})")
        return expanded

    # If we're in OFFERED_OPTIONS phase and user gives short affirmative
    if conv_state.interaction_phase == InteractionPhase.OFFERED_OPTIONS:
        affirmatives = ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'y']
        if message_lower in affirmatives:
            intent = conv_state.active_intent or "the options"
            expanded = f"Yes, please show me {intent} options."
            logger.info(f"Expanded affirmative '{message}' → '{expanded}'")
            return expanded

    # No expansion needed
    return message


# =============================================================================
# Intent Detection & Agent Bundles
# =============================================================================

class Intent(str, Enum):
    """User intent categories that map to agent bundles."""
    NUTRITION_WITH_ACTIVITY = "nutrition_with_activity"  # meal + workout/schedule
    MEAL_PLANNING = "meal_planning"                      # meal + schedule
    SHOPPING_FOR_MEAL = "shopping_for_meal"              # meal + shopping
    EVENT_PREP = "event_prep"                            # bake sale, dinner party prep
    BUDGET_MEAL_PLANNING = "budget_meal_planning"        # cheapest way to eat this week (initial)
    BUDGET_SHOW_OPTIONS = "budget_show_options"          # show the 3 budget options
    FRIDGE_COMPREHENSIVE = "fridge_comprehensive"        # deep fridge analysis ("really")
    FRIDGE_ONLY = "fridge_only"                          # just fridge
    CALENDAR_ONLY = "calendar_only"                      # just calendar
    SHOPPING_ONLY = "shopping_only"                      # just shopping
    GROCERY_SHOPPING = "grocery_shopping"                  # any turn during active shopping context
    GENERAL = "general"                                  # no specific intent


# Intent → Agent Bundle mapping (deterministic)
INTENT_AGENT_BUNDLES: dict[Intent, list[AgentType]] = {
    Intent.NUTRITION_WITH_ACTIVITY: [AgentType.FRIDGE, AgentType.CALENDAR, AgentType.INSTACART],
    Intent.MEAL_PLANNING: [AgentType.FRIDGE, AgentType.CALENDAR],
    Intent.SHOPPING_FOR_MEAL: [AgentType.FRIDGE, AgentType.INSTACART],
    Intent.EVENT_PREP: [AgentType.CALENDAR, AgentType.FRIDGE],  # Bake sale, dinner party prep
    Intent.BUDGET_MEAL_PLANNING: [AgentType.FRIDGE],  # Cheapest way to eat - only needs fridge
    Intent.BUDGET_SHOW_OPTIONS: [AgentType.FRIDGE],   # Show the 3 budget options
    Intent.FRIDGE_COMPREHENSIVE: [AgentType.FRIDGE],  # Deep analysis triggers comprehensive mode
    Intent.FRIDGE_ONLY: [AgentType.FRIDGE],
    Intent.CALENDAR_ONLY: [AgentType.CALENDAR],
    Intent.SHOPPING_ONLY: [AgentType.INSTACART],
    Intent.GROCERY_SHOPPING: [],   # Handled via Gemini with shopping context
    Intent.GENERAL: [],
}


# Intent detection rules (keyword patterns)
INTENT_PATTERNS: dict[Intent, list[tuple[str, ...]]] = {
    Intent.BUDGET_MEAL_PLANNING: [
        ('cheapest', 'eat'), ('cheapest', 'week'), ('cheap', 'eat'),
        ('budget', 'eat'), ('budget', 'meal'), ('budget', 'week'),
        ('save', 'money', 'food'), ('save', 'money', 'eat'),
        ('affordable', 'eat'), ('low', 'cost', 'meal'),
        ('stretch', 'food'), ('stretch', 'groceries'),
    ],
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
    Intent.EVENT_PREP: [
        ('bake', 'sale'), ('bake', 'need'), ('bake', 'prep'),
        ('dinner', 'party'), ('potluck',), ('hosting',),
        ('need', 'bake'), ('prep', 'event'), ('prepare', 'event'),
        ('ready', 'bake'), ('ready', 'party'),
    ],
}

# Budget meal planning keywords - trigger budget intent
BUDGET_MEAL_KEYWORDS = [
    'cheapest way to eat', 'cheapest way to feed',
    'budget meals', 'budget friendly',
    'eat cheap', 'eat on a budget',
    'save money on food', 'affordable meals',
    'stretch my groceries', 'make food last',
]

# Follow-up keywords for showing budget options
BUDGET_SHOW_OPTIONS_KEYWORDS = [
    'show options', 'show me options', 'show the options',
    'yes show', 'yes please', 'show me',
    'what are the options', 'tell me more',
]

# Event prep keywords - trigger event prep intent
EVENT_PREP_KEYWORDS = [
    'bake sale', 'baking', 'dinner party', 'potluck', 'hosting',
    'party prep', 'event prep', 'what do i need for',
]


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

        # Conversation state store: key = "{user_id}:{session_id}"
        self._conversation_states: dict[str, ConversationState] = {}

        # Initialize agents
        self._initialize_agents()

    def _get_conversation_key(self, user_id: str, session_id: str) -> str:
        """Generate a unique key for conversation state lookup."""
        return f"{user_id}:{session_id}"

    def _get_or_create_conversation_state(
        self,
        user_id: str,
        session_id: str
    ) -> ConversationState:
        """Get existing conversation state or create a new one."""
        key = self._get_conversation_key(user_id, session_id)
        if key not in self._conversation_states:
            self._conversation_states[key] = ConversationState(
                conversation_id=key,
                user_id=user_id,
                session_id=session_id
            )
            logger.info(f"Created new conversation state for {key}")
        return self._conversation_states[key]

    def _update_conversation_state(
        self,
        conv_state: ConversationState,
        user_message: str,
        assistant_response: str,
        intent: Optional[Intent] = None,
        phase: Optional[InteractionPhase] = None,
        output_type: Optional[str] = None
    ) -> None:
        """Update conversation state after a turn."""
        conv_state.last_user_message = user_message
        conv_state.last_assistant_message = assistant_response
        conv_state.turn_count += 1

        if intent:
            conv_state.active_intent = intent.value
            conv_state.intent_context["last_intent"] = intent.value

        if phase:
            conv_state.interaction_phase = phase
            logger.info(f"Conversation phase → {phase.value}")

        if output_type:
            conv_state.last_structured_output_type = output_type

        logger.debug(f"Conversation state updated: turn={conv_state.turn_count}, "
                    f"intent={conv_state.active_intent}, phase={conv_state.interaction_phase}")

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

        # Check for "show options" (follow-up to budget meal planning)
        if any(trigger in message_lower for trigger in BUDGET_SHOW_OPTIONS_KEYWORDS):
            logger.info("Detected budget show options intent")
            return Intent.BUDGET_SHOW_OPTIONS

        # Check for budget meal planning first (most specific for this feature)
        if any(trigger in message_lower for trigger in BUDGET_MEAL_KEYWORDS):
            logger.info("Detected budget meal planning intent")
            return Intent.BUDGET_MEAL_PLANNING

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

        # Check for event prep queries (bake sale, dinner party, potluck)
        if any(trigger in message_lower for trigger in EVENT_PREP_KEYWORDS):
            logger.info("Detected event prep intent")
            return Intent.EVENT_PREP

        # Check for comprehensive fridge queries ("really", "full scan", etc.)
        comprehensive_triggers = [
            'really', 'full scan', 'complete analysis', 'comprehensive',
            'deep check', 'thorough', 'everything in my fridge', 'detailed',
            'tell me everything'
        ]
        fridge_keywords = ['fridge', 'refrigerator', 'food']
        is_fridge_query = any(kw in message_lower for kw in fridge_keywords)
        is_comprehensive = any(trigger in message_lower for trigger in comprehensive_triggers)

        if is_fridge_query and is_comprehensive:
            logger.info("Detected comprehensive fridge intent")
            return Intent.FRIDGE_COMPREHENSIVE

        # Fall back to single-agent detection
        if any(kw in message_lower for kw in ['fridge', 'food', 'eat', 'cook', 'meal', 'ingredient']):
            return Intent.FRIDGE_ONLY
        if any(kw in message_lower for kw in ['calendar', 'schedule', 'workout', 'gym', 'tonight', 'today']):
            return Intent.CALENDAR_ONLY
        if any(kw in message_lower for kw in ['buy', 'shop', 'cart', 'order', 'instacart']):
            return Intent.SHOPPING_ONLY

        return Intent.GENERAL

    def _detect_intent_with_context(
        self,
        message: str,
        conv_state: ConversationState
    ) -> Intent:
        """
        Detect intent considering conversation state.

        If we're in the middle of a conversation flow, use context to
        determine if this is a follow-up to a previous interaction.
        """
        # ── Grocery shopping context takes priority when active ──
        if conv_state.is_shopping_context_active():
            logger.info("Active shopping context — routing to Gemini")
            return Intent.GROCERY_SHOPPING

        # First, try standard intent detection
        detected_intent = self.detect_intent(message)

        # If we got a specific intent, use it
        if detected_intent != Intent.GENERAL:
            return detected_intent

        # Check if this is a follow-up to a previous interaction
        if conv_state.is_mid_conversation():
            logger.info(f"Mid-conversation: phase={conv_state.interaction_phase}, "
                       f"active_intent={conv_state.active_intent}")

            # If we're in OFFERED_OPTIONS phase, short affirmatives should trigger SHOW_OPTIONS
            if conv_state.interaction_phase == InteractionPhase.OFFERED_OPTIONS:
                affirmatives = ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'y',
                              'show', 'option', 'please', 'go ahead', 'sounds good']
                msg_lower = message.lower().strip()

                if any(word in msg_lower for word in affirmatives):
                    # Check what the active intent was
                    if conv_state.active_intent == Intent.BUDGET_MEAL_PLANNING.value:
                        logger.info("Follow-up detected: OFFERED_OPTIONS → BUDGET_SHOW_OPTIONS")
                        return Intent.BUDGET_SHOW_OPTIONS

            # If assistant asked a follow-up question, treat as continuation
            if conv_state.assistant_asked_followup():
                logger.info("Assistant asked follow-up, continuing with active intent")
                # Return the active intent to continue the flow
                if conv_state.active_intent:
                    try:
                        return Intent(conv_state.active_intent)
                    except ValueError:
                        pass

        return detected_intent

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
        Maintains conversation state to handle short follow-up messages.

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

        # Step 0: Get or create conversation state
        conv_state = self._get_or_create_conversation_state(user_id, session_id)
        logger.info(f"Processing message: '{message[:50]}...' (turn={conv_state.turn_count}, "
                   f"phase={conv_state.interaction_phase}, intent={conv_state.active_intent})")

        # Step 0.5: Expand short replies when mid-conversation
        original_message = message
        if conv_state.is_mid_conversation() and is_short_reply(message):
            message = expand_short_reply(message, conv_state)
            logger.info(f"Short reply expansion: '{original_message}' → '{message}'")

        # Build context with conversation state
        context = AgentContext(
            user_id=user_id,
            session_id=session_id,
            message=message,
            chat_history=chat_history or [],
            inventory=inventory,
            calendar_events=kwargs.get("calendar_events"),
            energy_data=kwargs.get("energy_data"),
            security_status=kwargs.get("security_status"),
            user_preferences=kwargs.get("user_preferences"),
            conversation_state=conv_state
        )

        # Step 1: Detect intent (considering conversation state)
        intent = self._detect_intent_with_context(message, conv_state)
        agent_bundle = INTENT_AGENT_BUNDLES.get(intent, [])

        logger.info("Intent: %s → Agents: %s", intent, [a.value for a in agent_bundle])

        # Step 2: Execute agent bundle
        if len(agent_bundle) > 1:
            # Multi-agent coordination
            response = await self._execute_agent_bundle(context, intent, agent_bundle)
            # Update conversation state for multi-agent responses
            self._update_conversation_state(
                conv_state,
                user_message=original_message,
                assistant_response=response.content,
                intent=intent,
                phase=InteractionPhase.FOLLOW_UP
            )
            return response, AgentType.ORCHESTRATOR

        # Special handling for budget meal planning (initial query)
        elif intent == Intent.BUDGET_MEAL_PLANNING:
            response = await self._handle_budget_meal_planning(context, show_options=False)
            # Update conversation state: we offered options, waiting for user response
            self._update_conversation_state(
                conv_state,
                user_message=original_message,
                assistant_response=response.content,
                intent=Intent.BUDGET_MEAL_PLANNING,
                phase=InteractionPhase.OFFERED_OPTIONS,
                output_type="OPTIONS_OFFER"
            )
            return response, AgentType.FRIDGE

        # Special handling for showing budget options (follow-up)
        elif intent == Intent.BUDGET_SHOW_OPTIONS:
            response = await self._handle_budget_meal_planning(context, show_options=True)
            # Update conversation state: options shown, flow continues
            self._update_conversation_state(
                conv_state,
                user_message=original_message,
                assistant_response=response.content,
                intent=Intent.BUDGET_SHOW_OPTIONS,
                phase=InteractionPhase.EXPANDING_OPTIONS,
                output_type="OPTIONS_LIST"
            )
            return response, AgentType.FRIDGE

        # Active shopping context — all turns go through Gemini
        elif intent == Intent.GROCERY_SHOPPING:
            response = await self._handle_grocery_shopping_turn(context, conv_state)
            self._update_conversation_state(
                conv_state,
                user_message=original_message,
                assistant_response=response.content,
                intent=Intent.GROCERY_SHOPPING,
                phase=InteractionPhase.FOLLOW_UP,
            )
            return response, AgentType.FRIDGE

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

                # Update conversation state for single-agent responses
                self._update_conversation_state(
                    conv_state,
                    user_message=original_message,
                    assistant_response=response.content,
                    intent=intent,
                    phase=InteractionPhase.FOLLOW_UP
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

        # Update conversation state for general chat
        self._update_conversation_state(
            conv_state,
            user_message=original_message,
            assistant_response=response.content,
            phase=InteractionPhase.FOLLOW_UP
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

                    # For EVENT_PREP intent, also get prep context
                    prep_ctx = None
                    if intent == Intent.EVENT_PREP:
                        # Extract event keyword from message (e.g., "bake sale")
                        event_keyword = self._extract_event_keyword(context.message)
                        prep_ctx = await agent.get_prep_context(context.user_id, event_keyword)
                        logger.info("Event prep context: %s", prep_ctx)

                    results["calendar"] = {
                        "workout": workout_ctx,
                        "events": events,
                        "prep_context": prep_ctx,
                        "available": True
                    }

                    if prep_ctx:
                        status_msg = f"Found event: {prep_ctx.get('event_title', 'Unknown')}"
                    elif workout_ctx and workout_ctx.get("has_workout"):
                        status_msg = "Found workout scheduled"
                    else:
                        status_msg = "No relevant events found"

                    await self._emit_status(
                        agent_type,
                        AgentStatus.COMPLETED,
                        status_msg
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
        intent = results.get("intent", "")

        # Format each data source
        fridge_data = self._format_fridge_data(results.get("fridge", {}))
        calendar_data = self._format_calendar_data(results.get("calendar", {}))
        instacart_data = self._format_instacart_data(results.get("instacart", {}))

        # Use specialized prompt for EVENT_PREP
        if intent == Intent.EVENT_PREP.value:
            synthesis_prompt = self._get_event_prep_synthesis_prompt(
                context.message, fridge_data, calendar_data, instacart_data
            )
        else:
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

    def _get_event_prep_synthesis_prompt(
        self,
        user_question: str,
        fridge_data: str,
        calendar_data: str,
        instacart_data: str
    ) -> str:
        """Get specialized synthesis prompt for event prep queries (bake sale, dinner party)."""
        return f"""You are helping the user prepare for an upcoming event that requires cooking or baking.

**User Question:** {user_question}

---
**EVENT DETAILS** (from calendar)
{calendar_data}

---
**WHAT'S IN THE FRIDGE** (from camera vision analysis)
{fridge_data}

---
**SHOPPING OPTIONS** (if available)
{instacart_data}

---

**Your Task:**
1. First, acknowledge the event and when it is
2. Compare the "suggested items needed" from the event with what's visible in the fridge
3. Create two clear lists:
   - ✅ **Items you have:** (things from the suggested list that appear to be in the fridge)
   - 🛒 **Items to get:** (things from the suggested list NOT visible in the fridge)
4. If the event is baking-related, suggest 1-2 simple recipes that would work
5. Note the urgency - if the event is tomorrow, emphasize what needs to happen today

**Format:** Use clear headers and bullet points. Be encouraging and helpful!
"""

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

        # Prep-required event info (takes priority)
        prep_ctx = calendar.get("prep_context")
        if prep_ctx:
            lines.append(f"📅 **{prep_ctx.get('event_title', 'Event')}**")
            lines.append(f"   When: {prep_ctx.get('event_time', 'Unknown')}")
            lines.append(f"   Location: {prep_ctx.get('location', 'Unknown')}")
            lines.append(f"   Time until event: {prep_ctx.get('days_until', 0):.1f} days ({prep_ctx.get('hours_until', 0):.0f} hours)")
            lines.append(f"   Prep urgency: {prep_ctx.get('urgency', 'planning')}")
            lines.append(f"   Prep type: {prep_ctx.get('prep_type', 'cooking')}")

            suggested = prep_ctx.get("suggested_items", [])
            if suggested:
                lines.append(f"\n   **Suggested items needed:**")
                for item in suggested:
                    lines.append(f"   • {item}")

            if prep_ctx.get("description"):
                lines.append(f"\n   Note: {prep_ctx.get('description')}")

            return "\n".join(lines)

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
            "rice", "pasta", "bread", "avocado", "banana", "apple",
            "flour", "sugar", "butter", "vanilla", "baking powder", "chocolate"
        ]
        response_lower = fridge_response.lower()
        return [item for item in common_items if item in response_lower]

    def _extract_event_keyword(self, message: str) -> Optional[str]:
        """Extract event keyword from user message for event lookup."""
        message_lower = message.lower()

        # Common event keywords to look for
        event_keywords = [
            "bake sale", "baking", "dinner party", "potluck",
            "party", "hosting", "event"
        ]

        for keyword in event_keywords:
            if keyword in message_lower:
                return keyword

        return None

    # ─── Grocery Shopping Turn (Gemini-powered) ─────────────────────────

    async def _handle_grocery_shopping_turn(
        self,
        context: AgentContext,
        conv_state: ConversationState,
    ) -> AgentResponse:
        """
        Handle any message during an active shopping context via Gemini.

        Code decides: is the context active, what item/store is involved.
        Gemini decides: what to say, how to interpret the user, what to suggest.

        Special branch: if the user asks about fridge contents, do a vision
        analysis against the thumbnail and return a conversational answer.
        Shopping context stays active — the next turn resumes normally.
        """
        ctx = conv_state.shopping_context

        # ── Fridge-check branch (model-driven routing) ────────────────
        if await self._is_fridge_check(context.message):
            logger.info("Fridge check detected mid-shopping for user %s", context.user_id)
            fridge_answer = await self._do_fridge_check(context)
            if fridge_answer:
                # Shopping context intentionally NOT dismissed
                return fridge_answer

        # ── Normal shopping continuation ──────────────────────────────
        system_prompt = (
            "You are continuing an active grocery task. "
            "Do not reset the conversation or explain context.\n\n"
            f"Store: {ctx.store_name}\n"
            f"Item: {ctx.item_name} (status: {ctx.item_status})\n\n"
            "Rules:\n"
            "- 1-2 sentences max\n"
            "- Use your knowledge of typical grocery store layouts when relevant\n"
            "- Do not re-introduce yourself\n"
            "- At most one optional follow-up question\n"
            "- If the user is done or says thanks, say goodbye briefly"
        )

        # Build chat history: seed + any prior turns
        history = []
        if conv_state.last_assistant_message:
            history.append({"role": "assistant", "content": conv_state.last_assistant_message})
        if conv_state.last_user_message:
            history.append({"role": "user", "content": conv_state.last_user_message})
        if context.chat_history:
            history.extend(context.chat_history[-4:])

        response = await self.llm.generate(
            prompt=context.message,
            system_prompt=system_prompt,
            chat_history=history if history else None,
        )

        # Context lifecycle: dismiss on clear endings (state concern, not language)
        endings = ["bye", "thanks", "thank you", "that's all", "all set", "done"]
        if any(e in context.message.lower() for e in endings):
            ctx.dismiss()
            logger.info("Shopping context dismissed by user")

        return AgentResponse(
            content=response.content,
            agent_type=AgentType.FRIDGE,
            status=AgentStatus.COMPLETED,
            metadata={"grocery_flow": "gemini", "store": ctx.store_name, "item": ctx.item_name},
        )

    async def _is_fridge_check(self, message: str) -> bool:
        """
        Ask Gemini whether the user is asking about their fridge contents.

        Single lightweight text call — no vision, no tools.
        Returns True if the user wants a fridge inventory check.
        """
        try:
            result = await self.llm.generate(
                prompt=(
                    f"The user is currently shopping at a grocery store. "
                    f"Their message is: \"{message}\"\n\n"
                    f"Is the user asking about what is currently in their fridge or "
                    f"refrigerator at home (e.g. checking if they already have an item, "
                    f"how many they have, or if something is still fresh)?\n\n"
                    f"Answer with exactly one word: YES or NO"
                ),
                system_prompt="You are a routing classifier. Answer only YES or NO.",
            )
            answer = result.content.strip().upper()
            return answer.startswith("YES")
        except Exception as e:
            logger.warning("Fridge-check classification failed: %s", e)
            return False

    async def _do_fridge_check(self, context: AgentContext) -> Optional[AgentResponse]:
        """
        Perform a fridge vision analysis mid-shopping and return a short,
        conversational answer. Returns None if vision is unavailable.

        Uses the FridgeAgent's existing vision chat (thumbnail + Gemini).
        """
        fridge_agent = self._agents.get(AgentType.FRIDGE)
        if not fridge_agent:
            return None

        # Emit status so the UI shows "Checking your inventory..."
        await self._emit_status(
            AgentType.FRIDGE,
            AgentStatus.PROCESSING,
            "Checking your inventory..."
        )

        # Ensure the vision chat session is ready (uploads thumbnail if needed)
        vision_ready = await fridge_agent._ensure_vision_chat(context.user_id)
        if not vision_ready:
            logger.warning("Vision chat unavailable for fridge check")
            return None

        # Ask the vision model with a conversational-answer constraint
        prompt = (
            f"{context.message}\n\n"
            "Answer in 1-2 short, casual sentences. "
            "Say whether the item is present, approximate quantity if visible, "
            "and freshness if inferable. No lists, no cards."
        )
        answer = await fridge_agent._ask_vision_chat(context.user_id, prompt)
        if not answer:
            return None

        await self._emit_status(
            AgentType.FRIDGE,
            AgentStatus.COMPLETED,
            "Inventory checked"
        )

        logger.info("Fridge check complete for user %s", context.user_id)
        return AgentResponse(
            content=answer,
            agent_type=AgentType.FRIDGE,
            status=AgentStatus.COMPLETED,
            metadata={"grocery_flow": "fridge_check"},
        )

    async def _handle_general_chat(self, context: AgentContext) -> AgentResponse:
        """
        Handle general chat that doesn't need a specific agent.

        SAFEGUARD: If we're mid-conversation, enrich the prompt with context
        to prevent cold-start generic greetings.
        """
        try:
            conv_state = context.conversation_state
            system_prompt = SYSTEM_PROMPTS.get("orchestrator", "")

            # Build the prompt with context if mid-conversation
            prompt = context.message
            enhanced_history = context.chat_history or []

            if conv_state and conv_state.is_mid_conversation():
                logger.info(f"General chat mid-conversation: phase={conv_state.interaction_phase}, "
                           f"last_output={conv_state.last_structured_output_type}")

                # Add context reminder to system prompt
                context_reminder = f"""

IMPORTANT CONTEXT:
- You are continuing an existing conversation (turn {conv_state.turn_count + 1})
- The last topic discussed was: {conv_state.active_intent or 'general conversation'}
- Your last message was: "{(conv_state.last_assistant_message or '')[:200]}..."
- The user just said: "{context.message}"

Do NOT start with a generic greeting. Continue the conversation naturally.
If the user seems to be responding to your previous message, acknowledge that context.
"""
                system_prompt = system_prompt + context_reminder

                # Ensure last assistant message is in history
                if conv_state.last_assistant_message and conv_state.last_user_message:
                    # Check if already in history
                    has_last_turn = any(
                        msg.get("content") == conv_state.last_assistant_message
                        for msg in enhanced_history
                    )
                    if not has_last_turn:
                        # Prepend the last turn
                        enhanced_history = [
                            {"role": "assistant", "content": conv_state.last_assistant_message},
                            {"role": "user", "content": conv_state.last_user_message}
                        ] + enhanced_history[-4:]  # Keep last 4 + the prepended turn

            response = await self.llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=enhanced_history if enhanced_history else None
            )

            # Post-process: Block obvious cold-start greetings mid-conversation
            response_content = response.content
            if conv_state and conv_state.turn_count > 0:
                cold_start_phrases = [
                    "hello! i'm domus",
                    "hi! i'm domus",
                    "hello! how can i help",
                    "hi there! i'm your",
                    "welcome! i'm domus"
                ]
                response_lower = response_content.lower()[:100]

                if any(phrase in response_lower for phrase in cold_start_phrases):
                    logger.warning("Blocked cold-start greeting mid-conversation, regenerating...")
                    # Regenerate with stronger context
                    retry_prompt = f"""Continue the conversation. The user said: "{context.message}"
Your previous response was about: {conv_state.active_intent or 'helping the user'}.
Do not introduce yourself again - just respond to what they said."""

                    retry_response = await self.llm.generate(
                        prompt=retry_prompt,
                        system_prompt=system_prompt,
                        chat_history=enhanced_history
                    )
                    response_content = retry_response.content

            return AgentResponse(
                content=response_content,
                agent_type=AgentType.ORCHESTRATOR,
                status=AgentStatus.COMPLETED,
                metadata={"model": "gemini", "mid_conversation": conv_state.is_mid_conversation() if conv_state else False}
            )

        except Exception as e:
            logger.error(f"General chat error: {e}")
            # Even fallback should check for mid-conversation
            if context.conversation_state and context.conversation_state.turn_count > 0:
                return AgentResponse(
                    content="I'm sorry, I had trouble processing that. Could you rephrase your question?",
                    agent_type=AgentType.ORCHESTRATOR,
                    status=AgentStatus.COMPLETED
                )
            return AgentResponse(
                content="Hello! I'm Domus, your smart home assistant. How can I help you today?",
                agent_type=AgentType.ORCHESTRATOR,
                status=AgentStatus.COMPLETED
            )

    async def _handle_budget_meal_planning(
        self,
        context: AgentContext,
        show_options: bool = False
    ) -> AgentResponse:
        """
        Handle budget meal planning queries.

        Feature 3: "Cheapest way to eat this week?"
        - show_options=False: Initial query, returns short intro with "Show options?"
        - show_options=True: Follow-up, returns full 3 options

        IMPORTANT: Always includes chat history to maintain context across turns.
        """
        try:
            conv_state = context.conversation_state
            logger.info(f"Budget meal planning: show_options={show_options}, "
                       f"has_conv_state={conv_state is not None}")

            # Step 1: Emit status - analyzing fridge
            await self._emit_status(
                AgentType.FRIDGE,
                AgentStatus.ACTIVATING,
                "Checking your fridge..."
            )

            # Step 2: Get fridge contents using FridgeAgent
            fridge_agent = self._agents.get(AgentType.FRIDGE)
            if not fridge_agent:
                raise ValueError("FridgeAgent not available")

            # Get comprehensive fridge analysis
            await self._emit_status(
                AgentType.FRIDGE,
                AgentStatus.PROCESSING,
                "Analyzing fridge contents..."
            )

            fridge_response = await fridge_agent.process(context)
            fridge_contents = fridge_response.content

            await self._emit_status(
                AgentType.FRIDGE,
                AgentStatus.COMPLETED,
                "Fridge analysis complete"
            )

            # Step 3: Use appropriate budget prompt
            status_msg = "Creating budget meal options..." if show_options else "Preparing options..."
            await self._emit_status(
                AgentType.ORCHESTRATOR,
                AgentStatus.PROCESSING,
                status_msg
            )

            # Choose prompt based on whether we're showing options
            prompt_key = "budget_meal_planning_options" if show_options else "budget_meal_planning"
            budget_prompt = AGENT_PROMPTS.get(prompt_key, "")
            if not budget_prompt:
                raise ValueError(f"Budget prompt '{prompt_key}' not found")

            # Format the prompt with fridge contents
            formatted_prompt = budget_prompt.format(fridge_contents=fridge_contents)

            # Build enhanced chat history with context
            # This ensures Gemini always knows what was said before
            enhanced_chat_history = []

            # Include last assistant message if available (critical for follow-ups)
            if conv_state and conv_state.last_assistant_message:
                # For show_options, include what we offered previously
                if show_options:
                    enhanced_chat_history.append({
                        "role": "assistant",
                        "content": conv_state.last_assistant_message
                    })
                    enhanced_chat_history.append({
                        "role": "user",
                        "content": conv_state.last_user_message or context.message
                    })
                    logger.info("Including previous turn in chat history for context")

            # Add any existing chat history
            if context.chat_history:
                # Limit to last 6 messages to avoid token overflow
                recent_history = context.chat_history[-6:]
                for msg in recent_history:
                    if msg not in enhanced_chat_history:
                        enhanced_chat_history.append(msg)

            response = await self.llm.generate(
                prompt=formatted_prompt,
                system_prompt="You are a household budgeting assistant for Domus.",
                chat_history=enhanced_chat_history if enhanced_chat_history else None,
                temperature=0.5  # Balanced for structured output
            )

            logger.info("Budget meal planning response generated (show_options=%s, "
                       f"history_len={len(enhanced_chat_history)})", show_options)

            return AgentResponse(
                content=response.content,
                agent_type=AgentType.FRIDGE,
                status=AgentStatus.COMPLETED,
                metadata={
                    "intent": "budget_show_options" if show_options else "budget_meal_planning",
                    "fridge_analyzed": True,
                    "options_shown": show_options,
                    "context_turns": len(enhanced_chat_history)
                }
            )

        except Exception as e:
            logger.error(f"Budget meal planning error: {e}")
            return AgentResponse(
                content="I had trouble analyzing your fridge for budget meal options. "
                        "Could you try asking again or check if Fridge Sense is connected?",
                agent_type=AgentType.FRIDGE,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )

    def set_shopping_context(
        self,
        user_id: str,
        session_id: str,
        store_name: str,
        item_name: str,
        item_status: str,
    ) -> None:
        """
        Set an active shopping context on the conversation state.

        Called by the websocket handler when a grocery notification fires.
        This primes the orchestrator to route follow-up messages through
        Gemini with shopping context for the next 10 minutes.
        """
        conv_state = self._get_or_create_conversation_state(user_id, session_id)
        conv_state.shopping_context = ShoppingContext(
            store_name=store_name,
            item_name=item_name,
            item_status=item_status,
        )
        conv_state.interaction_phase = InteractionPhase.GROCERY_SHOPPING
        conv_state.active_intent = Intent.GROCERY_SHOPPING.value

        # Store the chat seed as "last assistant message" so Gemini
        # has conversation continuity from the notification text.
        days_qualifier = "for a few days" if item_status == "out" else ""
        seed = (
            f"You've been out of **{item_name}** {days_qualifier} "
            f"— and you're at {store_name}, which makes this a good moment to grab it.\n\n"
            f"Want me to add it to your list?"
        )
        conv_state.last_assistant_message = seed
        logger.info(
            "Shopping context set: user=%s, store=%s, item=%s (TTL=10min)",
            user_id, store_name, item_name,
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
