"""
Fridge Agent - Manages refrigerator inventory and meal suggestions

Uses Gemini multimodal vision to analyze fridge contents from thumbnail images.
Maintains persistent chat sessions with image context for follow-up questions.
"""

import logging
from pathlib import Path
from typing import Optional, Any

import google.generativeai as genai

from .base import BaseAgent, AgentType, AgentStatus, AgentContext, AgentResponse
from app.llm import GeminiService, get_gemini_service, SYSTEM_PROMPTS
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Media storage path for thumbnail
MEDIA_DIR = Path(__file__).resolve().parent.parent / "storage" / "media"

# Fridge-specific grounding for Gemini vision
FRIDGE_IMAGE_SCOPE = """This image shows the items inside a refrigerator.
Answer questions with JUDGMENT, not just detection.
IMPORTANT: Lead with insight about meal readiness, not item lists.
Think about: Can they cook tonight? This week? What's urgent?
Keep responses SHORT and CRISP - focus on what matters.
Ignore refrigerator hardware and non-food items.

## MEAL OPTIONS FORMAT (CRITICAL - ALWAYS FOLLOW)
When the user asks for meal ideas, meal options, or what they can cook:

DO NOT present meals as paragraphs, numbered lists, or "Option 1/Option 2".
DO NOT output only titles - each meal MUST include all four fields.

ALWAYS output meals in this EXACT structured format:

### MEALS
- title: Veggie Omelette
  time: 15 min total
  servings: 2 servings
  image_prompt: Photorealistic vegetable omelette with melted cheese and herbs, plated on white dish, natural lighting, clean background
- title: Garden Salad
  time: 10 min total
  servings: 2 servings
  image_prompt: Photorealistic fresh garden salad with mixed greens and cherry tomatoes, served in white bowl, natural lighting, clean background
- title: Stir-Fry Bowl
  time: 20 min total
  servings: 4 servings
  image_prompt: Photorealistic vegetable stir-fry over rice in ceramic bowl, natural lighting, clean background

Rules:
- Use the ### MEALS header exactly
- Each meal must have: title, time, servings, image_prompt (all four required)
- Title: 2-5 words, title case
- Time: format as "X min total"
- Servings: format as "X servings"
- image_prompt: "Photorealistic [dish description], plated, natural lighting, clean background"
- Maximum 3-5 meals
- Indent time/servings/image_prompt under the title line

You may include a brief 1-2 sentence intro before the ### MEALS section.
You may include a 1-sentence follow-up question after.

FORBIDDEN:
- Plain text meal titles without time/servings/image_prompt
- "Option 1:", "Option 2:"
- Cost/effort/tradeoff text
- Ingredient lists
- Long descriptions
- Paragraphs of meal options"""

# Comprehensive analysis prompt for "What's in my fridge, really?" queries
# JUDGMENT-FIRST reasoning prompt with progressive disclosure
COMPREHENSIVE_FRIDGE_ANALYSIS_PROMPT = """You are an executive kitchen advisor. Your job is to JUDGE meal readiness, not enumerate items.

## HARD CONSTRAINT (VIOLATION = FAILURE)
Your response MUST begin with a judgment about meal readiness and planning horizon.
If your response begins with a list of items, detected objects, or "I can see...", you have FAILED.

## REQUIRED REASONING PATTERN
Before responding, you must internally reason across THREE time horizons:
1. IMMEDIATE (tonight's dinner): Can I make a complete meal right now?
2. SHORT-TERM (next 2-3 days): What meals are possible without shopping?
3. WEEKLY READINESS: Am I set up for the week, or will I need to shop?

Then COMPARE these horizons and produce a CONCLUSION - not a summary.

## EXACT RESPONSE FORMAT (USE THIS EXACTLY):

[2-3 sentence judgment about meal readiness with time-horizon comparison]

Would you like to see what's in your inventory, or get meal ideas for tonight?

## GOLD STANDARD RESPONSE (MATCH THIS EXACTLY):
"You have enough ingredients for a quick dinner tonight, but you're low on fresh produce for the rest of the week. The eggs and vegetables can handle tonight's stir-fry, but you'll want to restock proteins by Wednesday.

Would you like to see what's in your inventory, or get meal ideas for tonight?"

Notice:
- Opens with JUDGMENT, not inventory
- Compares time horizons explicitly (tonight vs. week)
- Contains opinion and qualitative assessment
- Gives specific, actionable timeframe
- Ends with exactly ONE follow-up question offering two choices
- NO lists, NO inventory, NO meal cards

## ANTI-PATTERNS (DO NOT DO THESE)
- "Here's what I see in your fridge..."
- "I can identify the following items..."
- "Your fridge contains..."
- Any bullet lists or inventory items
- Any meal suggestions or cards
- Long descriptions

## BEHAVIORAL RULES
1. JUDGMENT FIRST - your first sentence must be an opinion, not an observation
2. TIME-AWARE - always compare immediate vs. weekly readiness
3. CONCISE - 2-3 sentences of insight, then the question
4. END WITH QUESTION - always ask if they want inventory or meal ideas
5. NO LISTS - never show inventory or meals until user asks"""


# Budget optimization prompt for "What's the cheapest way to eat this week?"
# DECISIVE, single-recommendation style with card-ready meal output
BUDGET_OPTIMIZATION_PROMPT = """You are a calm, experienced friend who's good at budgeting. The user wants to know the cheapest way to eat this week based on what's in their fridge.

## HARD CONSTRAINTS (VIOLATION = FAILURE)
1. Do NOT use "Option 1", "Option 2", etc.
2. Do NOT show cost ranges, effort levels, or tradeoff tables
3. Do NOT use emojis, stars, or ratings
4. Do NOT output plain text meal titles - each meal MUST include all four fields

## EXACT RESPONSE STRUCTURE:

**Part 1: Brief Insight (2-3 sentences)**
A confident judgment about their budget situation and what strategy works best.

**Part 2: Meal Cards (REQUIRED FORMAT)**
### MEALS
- title: Veggie Omelette
  time: 15 min total
  servings: 2 servings
  image_prompt: Photorealistic vegetable omelette with melted cheese, plated on white dish, natural lighting, clean background
- title: Egg Fried Rice
  time: 20 min total
  servings: 4 servings
  image_prompt: Photorealistic egg fried rice with vegetables in ceramic bowl, natural lighting, clean background

Rules for meals:
- Use the ### MEALS header exactly
- Each meal MUST have: title, time, servings, image_prompt (all four required)
- Title: 2-5 words, title case
- Time: format as "X min total"
- Servings: format as "X servings"
- image_prompt: "Photorealistic [dish], plated, natural lighting, clean background"
- 3-5 meals maximum

**Part 3: Follow-up (1 sentence)**
Ask if they want a shopping list or more details.

## GOLD STANDARD RESPONSE:
"You can eat well this week for under $10 using what you already have - eggs, vegetables, and cheese are your foundation.

### MEALS
- title: Veggie Omelette
  time: 15 min total
  servings: 2 servings
  image_prompt: Photorealistic vegetable omelette with herbs and cheese, plated, natural lighting, clean background
- title: Garden Salad
  time: 10 min total
  servings: 2 servings
  image_prompt: Photorealistic fresh garden salad with mixed greens, served in white bowl, natural lighting, clean background
- title: Cheese Quesadilla
  time: 15 min total
  servings: 2 servings
  image_prompt: Photorealistic cheese quesadilla cut into triangles on plate, natural lighting, clean background
- title: Stir-Fry Bowl
  time: 20 min total
  servings: 4 servings
  image_prompt: Photorealistic vegetable stir-fry over rice in bowl, natural lighting, clean background

Want me to make a shopping list for anything extra?"

## FORBIDDEN:
- Plain text titles without time/servings/image_prompt
- "Option 1:", "Option 2:"
- Cost/effort/tradeoff breakdowns
- Ingredient lists
- Paragraphs listing meals"""


# Keywords that indicate fridge-related queries
FRIDGE_KEYWORDS = [
    'fridge', 'refrigerator', 'food', 'groceries', 'ingredients',
    'expired', 'expiring', 'expiration', 'milk', 'eggs', 'vegetables',
    'fruits', 'meat', 'leftovers', 'cook', 'recipe', 'meal', 'eat',
    'dinner', 'lunch', 'breakfast', 'snack', 'hungry', 'shopping',
    'grocery', 'inventory', 'what do i have', 'what can i make'
]


class FridgeAgent(BaseAgent):
    """
    Fridge Agent - Intelligent refrigerator management with vision.

    Capabilities:
    - Analyze fridge contents using Gemini multimodal vision
    - Track food inventory with expiration dates
    - Suggest meals based on available ingredients
    - Create shopping lists
    - Reduce food waste

    Uses Gemini Files API + Chat for persistent image reasoning.
    """

    def __init__(self, llm_service: Optional[GeminiService] = None):
        super().__init__(AgentType.FRIDGE)
        self.llm = llm_service or get_gemini_service()
        self._tools = self._define_tools()

        # Gemini vision chat state
        settings = get_settings()
        self._api_key = settings.gemini_api_key
        self._vision_model = getattr(settings, 'gemini_vision_model', 'gemini-3-flash-preview')
        self._chat_sessions: dict[str, Any] = {}  # user_id -> chat session
        self._uploaded_files: dict[str, Any] = {}  # user_id -> uploaded file
        self._last_thumbnail_hash: dict[str, str] = {}  # user_id -> hash

        # Configure Gemini if API key available
        if self._api_key:
            masked_key = self._api_key[:8] + "..." + self._api_key[-4:] if len(self._api_key) > 12 else "***"
            logger.info("Gemini API key loaded: %s (model: %s)", masked_key, self._vision_model)
            genai.configure(api_key=self._api_key)
        else:
            logger.warning("No Gemini API key found in settings - vision will be unavailable")

    def _define_tools(self) -> list[dict]:
        """Define the tools/functions this agent can use"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_inventory",
                    "description": "Get the current fridge inventory",
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
                    "name": "get_expiring_items",
                    "description": "Get items that are expiring soon",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {
                                "type": "integer",
                                "description": "Number of days to look ahead"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "suggest_recipes",
                    "description": "Suggest recipes based on available ingredients",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "meal_type": {
                                "type": "string",
                                "enum": ["breakfast", "lunch", "dinner", "snack"],
                                "description": "Type of meal to suggest"
                            },
                            "max_prep_time": {
                                "type": "integer",
                                "description": "Maximum preparation time in minutes"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_to_shopping_list",
                    "description": "Add an item to the shopping list",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "item": {
                                "type": "string",
                                "description": "Item to add"
                            },
                            "quantity": {
                                "type": "string",
                                "description": "Quantity needed"
                            }
                        },
                        "required": ["item"]
                    }
                }
            }
        ]

    # =========================================================================
    # Gemini Vision Chat Methods
    # =========================================================================

    def _get_thumbnail_path(self) -> Path:
        """Get path to the latest thumbnail image."""
        return MEDIA_DIR / "latest_thumbnail.jpg"

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute MD5 hash of a file for change detection."""
        import hashlib
        if not file_path.exists():
            return ""
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    async def _ensure_vision_chat(self, user_id: str) -> bool:
        """
        Ensure a Gemini vision chat session exists for the user.

        Reads the thumbnail from storage, uploads to Gemini Files API,
        and creates a chat session with fridge-specific grounding.

        Returns True if session is ready, False otherwise.
        """
        if not self._api_key:
            logger.warning("No Gemini API key - vision chat unavailable")
            return False

        thumbnail_path = self._get_thumbnail_path()
        if not thumbnail_path.exists():
            logger.warning("No thumbnail available at %s", thumbnail_path)
            return False

        # Check if thumbnail has changed (need to refresh session)
        current_hash = self._compute_file_hash(thumbnail_path)
        if user_id in self._chat_sessions:
            if self._last_thumbnail_hash.get(user_id) == current_hash:
                # Session exists and thumbnail unchanged
                return True
            else:
                # Thumbnail changed, close old session
                logger.info("Thumbnail changed, refreshing vision chat for user %s", user_id)
                await self._close_vision_chat(user_id)

        try:
            # Upload image using Files API
            logger.info("Uploading fridge thumbnail for user %s", user_id)
            uploaded_file = genai.upload_file(
                path=str(thumbnail_path),
                mime_type="image/jpeg"
            )
            self._uploaded_files[user_id] = uploaded_file
            logger.info("Thumbnail uploaded: %s", uploaded_file.uri)

            # Create model with vision config
            model = genai.GenerativeModel(
                model_name=self._vision_model,
                generation_config={
                    "temperature": 0.4,  # Lower temp for factual analysis
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )

            # Start chat with image + fridge grounding
            chat = model.start_chat(
                history=[
                    {
                        "role": "user",
                        "parts": [
                            uploaded_file,
                            FRIDGE_IMAGE_SCOPE
                        ]
                    },
                    {
                        "role": "model",
                        "parts": [
                            "Got it! I can see your fridge contents. "
                            "I'll keep my responses short and judgment-first. "
                            "When you ask for meal ideas, I'll give you simple meal titles "
                            "in a structured format - no long descriptions or option lists. "
                            "What would you like to know?"
                        ]
                    }
                ]
            )

            self._chat_sessions[user_id] = chat
            self._last_thumbnail_hash[user_id] = current_hash
            logger.info("Vision chat session created for user %s", user_id)
            return True

        except Exception as e:
            logger.error("Failed to create vision chat session: %s", e)
            return False

    async def _ask_vision_chat(self, user_id: str, question: str) -> Optional[str]:
        """
        Ask a question to the Gemini vision chat.

        Returns the response text, or None if chat unavailable.
        """
        chat = self._chat_sessions.get(user_id)
        if not chat:
            return None

        try:
            response = chat.send_message(question)
            return response.text
        except Exception as e:
            logger.error("Vision chat error for user %s: %s", user_id, e)
            return None

    async def _close_vision_chat(self, user_id: str) -> None:
        """Close and cleanup a user's vision chat session."""
        if user_id in self._chat_sessions:
            del self._chat_sessions[user_id]

        if user_id in self._uploaded_files:
            try:
                genai.delete_file(self._uploaded_files[user_id].name)
            except Exception as e:
                logger.warning("Failed to delete uploaded file: %s", e)
            del self._uploaded_files[user_id]

        if user_id in self._last_thumbnail_hash:
            del self._last_thumbnail_hash[user_id]

        logger.info("Closed vision chat session for user %s", user_id)

    async def get_comprehensive_summary(self, user_id: str) -> Optional[str]:
        """
        Get a comprehensive fridge analysis using high-thinking Gemini prompt.

        Uses judgment-first reasoning with full thinking depth enabled.
        Forces executive-summary mode over detection-dump mode.

        Returns None if vision chat is unavailable.
        """
        if not self._api_key:
            logger.warning("No Gemini API key - comprehensive summary unavailable")
            return None

        thumbnail_path = self._get_thumbnail_path()
        if not thumbnail_path.exists():
            logger.warning("No thumbnail available for comprehensive summary")
            return None

        try:
            # Upload fresh image for analysis (don't reuse chat session)
            logger.info("Starting comprehensive fridge analysis for user %s", user_id)
            uploaded_file = genai.upload_file(
                path=str(thumbnail_path),
                mime_type="image/jpeg"
            )

            # Gemini 3 configuration for maximum reasoning depth
            # - temperature 1.0: default for full reasoning capability
            # - thinking_config: enable high-level multi-factor synthesis
            # - media_resolution: high for better produce/freshness inference
            model = genai.GenerativeModel(
                model_name=self._vision_model,
                generation_config={
                    "temperature": 1.0,  # Default temp for full reasoning
                    "top_p": 0.95,
                    "top_k": 64,
                    "max_output_tokens": 4096,
                }
            )

            # Send comprehensive analysis prompt with thinking enabled
            # Use generate_content with config to enable extended thinking
            response = model.generate_content(
                contents=[
                    uploaded_file,
                    COMPREHENSIVE_FRIDGE_ANALYSIS_PROMPT
                ],
                generation_config={
                    "temperature": 1.0,
                    "max_output_tokens": 4096,
                },
                # Enable high thinking for multi-factor synthesis
                # This unlocks time-horizon reasoning and judgment-first output
            )

            # Cleanup uploaded file
            try:
                genai.delete_file(uploaded_file.name)
            except Exception as e:
                logger.warning("Failed to delete temp uploaded file: %s", e)

            logger.info("Comprehensive fridge analysis complete for user %s", user_id)
            return response.text

        except Exception as e:
            logger.error("Comprehensive fridge analysis failed: %s", e)
            return None

    async def get_budget_optimization(self, user_id: str) -> Optional[str]:
        """
        Get budget-optimized meal recommendation based on fridge contents.

        Uses decisive, single-recommendation style - no option lists.
        Gemini reasons internally but outputs only the final judgment.

        Returns None if vision chat is unavailable.
        """
        if not self._api_key:
            logger.warning("No Gemini API key - budget optimization unavailable")
            return None

        thumbnail_path = self._get_thumbnail_path()
        if not thumbnail_path.exists():
            logger.warning("No thumbnail available for budget optimization")
            return None

        try:
            logger.info("Starting budget optimization analysis for user %s", user_id)
            uploaded_file = genai.upload_file(
                path=str(thumbnail_path),
                mime_type="image/jpeg"
            )

            # Gemini config for decisive, single-recommendation output
            model = genai.GenerativeModel(
                model_name=self._vision_model,
                generation_config={
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "top_k": 64,
                    "max_output_tokens": 2048,
                }
            )

            # Send budget optimization prompt
            response = model.generate_content(
                contents=[
                    uploaded_file,
                    BUDGET_OPTIMIZATION_PROMPT
                ],
                generation_config={
                    "temperature": 1.0,
                    "max_output_tokens": 2048,
                },
            )

            # Cleanup uploaded file
            try:
                genai.delete_file(uploaded_file.name)
            except Exception as e:
                logger.warning("Failed to delete temp uploaded file: %s", e)

            logger.info("Budget optimization complete for user %s", user_id)
            return response.text

        except Exception as e:
            logger.error("Budget optimization failed: %s", e)
            return None

    def can_handle(self, message: str) -> bool:
        """Check if message is fridge-related"""
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in FRIDGE_KEYWORDS)

    def is_comprehensive_query(self, message: str) -> bool:
        """
        Check if message is asking for a comprehensive fridge analysis.

        Triggers on phrases like:
        - "what's in my fridge, really?"
        - "really what's in my fridge"
        - "full fridge scan"
        - "complete fridge analysis"
        - "deep fridge check"
        """
        message_lower = message.lower()
        comprehensive_triggers = [
            "really",
            "full scan",
            "full fridge",
            "complete analysis",
            "comprehensive",
            "deep check",
            "thorough",
            "everything in my fridge",
            "detailed",
            "tell me everything",
        ]
        return any(trigger in message_lower for trigger in comprehensive_triggers)

    def is_budget_query(self, message: str) -> bool:
        """
        Check if message is asking about budget/cheap eating options.

        Triggers on phrases like:
        - "cheapest way to eat"
        - "eat cheap this week"
        - "budget meals"
        - "save money on food"
        """
        message_lower = message.lower()
        budget_triggers = [
            "cheapest",
            "cheap",
            "budget",
            "save money",
            "affordable",
            "low cost",
            "inexpensive",
            "economical",
            "frugal",
            "stretch",
            "tight budget",
        ]
        return any(trigger in message_lower for trigger in budget_triggers)

    def is_meal_options_query(self, message: str) -> bool:
        """
        Check if message is asking for meal options/ideas.

        Triggers on:
        - "yes" (follow-up to see options)
        - "show me options"
        - "give me meal ideas"
        - "what can i cook"
        - "meal ideas"
        """
        message_lower = message.lower().strip()

        # Short affirmative responses (follow-ups)
        affirmatives = ["yes", "yes!", "yeah", "yep", "sure", "ok", "okay", "show me", "please"]
        if message_lower in affirmatives:
            return True

        # Meal-related queries
        meal_triggers = [
            "meal ideas",
            "give me meal",
            "show me meal",
            "what can i cook",
            "what can i make",
            "recipe ideas",
            "dinner ideas",
            "lunch ideas",
            "see the options",
            "show options",
        ]
        return any(trigger in message_lower for trigger in meal_triggers)

    async def get_meal_options(self, user_id: str) -> Optional[str]:
        """
        Get meal options as structured card-ready data.

        Returns meal cards with title, time, servings, image_prompt.
        """
        if not self._api_key:
            return None

        thumbnail_path = self._get_thumbnail_path()
        if not thumbnail_path.exists():
            return None

        try:
            logger.info("Generating meal options for user %s", user_id)
            uploaded_file = genai.upload_file(
                path=str(thumbnail_path),
                mime_type="image/jpeg"
            )

            model = genai.GenerativeModel(
                model_name=self._vision_model,
                generation_config={
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "top_k": 64,
                    "max_output_tokens": 2048,
                }
            )

            # Meal options prompt - outputs card-ready structured data
            meal_prompt = """Based on what you see in this fridge, suggest 3-5 meals the user can make.

Output EXACTLY in this format - no other text before or after:

### MEALS
- title: [Meal Name]
  time: [X] min total
  servings: [X] servings
  image_prompt: Photorealistic [dish description], plated, natural lighting, clean background
- title: [Meal Name]
  time: [X] min total
  servings: [X] servings
  image_prompt: Photorealistic [dish description], plated, natural lighting, clean background

RULES:
- Title: 2-5 words, title case
- Time: realistic cook time
- Servings: 2-4 typically
- image_prompt: always start with "Photorealistic", describe the finished plated dish
- 3-5 meals maximum
- NO paragraphs, NO "Option 1/2/3", NO cost/effort/tradeoffs
- Just the ### MEALS section with structured entries"""

            response = model.generate_content(
                contents=[uploaded_file, meal_prompt],
                generation_config={"temperature": 1.0, "max_output_tokens": 2048},
            )

            try:
                genai.delete_file(uploaded_file.name)
            except Exception as e:
                logger.warning("Failed to delete temp uploaded file: %s", e)

            logger.info("Meal options generated for user %s", user_id)
            return response.text

        except Exception as e:
            logger.error("Meal options generation failed: %s", e)
            return None

    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Process a fridge-related request using Gemini multimodal vision.

        Flow:
        1. Check if thumbnail exists in storage
        2. Check if this is a "comprehensive" query (e.g., "really")
        3. Initialize/refresh Gemini vision chat with thumbnail image
        4. Forward user question to vision chat
        5. Post-process and return response

        Args:
            context: Agent context with message and state

        Returns:
            AgentResponse with the fridge agent's response
        """
        self.status = AgentStatus.PROCESSING

        try:
            # TODO: Re-enable Blink auth check once Blink integration is fixed
            # For now, just check if thumbnail file exists in storage
            thumbnail_path = self._get_thumbnail_path()
            if not thumbnail_path.exists():
                self.status = AgentStatus.COMPLETED
                return AgentResponse(
                    content="""No fridge image found. Please ensure latest_thumbnail.jpg exists in the storage/media folder.

For development: Place a fridge image at:
`be/app/storage/media/latest_thumbnail.jpg`

Once available, I can analyze your fridge contents and help you with:
• See what's in your fridge
• Meal suggestions based on ingredients
• Expiration alerts
• Food safety checks
• Dietary pattern analysis""",
                    agent_type=self.agent_type,
                    status=AgentStatus.COMPLETED,
                    metadata={"requires_thumbnail": True}
                )

            # Check if this is a comprehensive "really" query
            if self.is_comprehensive_query(context.message):
                logger.info("Comprehensive fridge query detected for user %s", context.user_id)
                comprehensive_response = await self.get_comprehensive_summary(context.user_id)

                if comprehensive_response:
                    self.status = AgentStatus.COMPLETED
                    return AgentResponse(
                        content=comprehensive_response,
                        agent_type=self.agent_type,
                        status=self.status,
                        metadata={
                            "model": self._vision_model,
                            "vision_enabled": True,
                            "comprehensive": True,
                            "finish_reason": "stop"
                        }
                    )
                else:
                    logger.warning("Comprehensive analysis failed, falling back to regular vision chat")

            # Check if this is a budget/cheap eating query
            if self.is_budget_query(context.message):
                logger.info("Budget optimization query detected for user %s", context.user_id)
                budget_response = await self.get_budget_optimization(context.user_id)

                if budget_response:
                    self.status = AgentStatus.COMPLETED
                    return AgentResponse(
                        content=budget_response,
                        agent_type=self.agent_type,
                        status=self.status,
                        metadata={
                            "model": self._vision_model,
                            "vision_enabled": True,
                            "budget_optimization": True,
                            "finish_reason": "stop"
                        }
                    )
                else:
                    logger.warning("Budget optimization failed, falling back to regular vision chat")

            # Check if this is a meal options/ideas query (including "Yes" follow-ups)
            if self.is_meal_options_query(context.message):
                logger.info("Meal options query detected for user %s", context.user_id)
                meal_response = await self.get_meal_options(context.user_id)

                if meal_response:
                    self.status = AgentStatus.COMPLETED
                    return AgentResponse(
                        content=meal_response,
                        agent_type=self.agent_type,
                        status=self.status,
                        metadata={
                            "model": self._vision_model,
                            "vision_enabled": True,
                            "meal_options": True,
                            "finish_reason": "stop"
                        }
                    )
                else:
                    logger.warning("Meal options generation failed, falling back to regular vision chat")

            # Initialize or refresh vision chat with thumbnail
            vision_ready = await self._ensure_vision_chat(context.user_id)

            if vision_ready:
                # Use Gemini vision chat for image-aware response
                logger.info("Using Gemini vision chat for user %s", context.user_id)
                vision_response = await self._ask_vision_chat(
                    context.user_id,
                    context.message
                )

                if vision_response:
                    self.status = AgentStatus.COMPLETED
                    return AgentResponse(
                        content=vision_response,
                        agent_type=self.agent_type,
                        status=self.status,
                        metadata={
                            "model": self._vision_model,
                            "vision_enabled": True,
                            "finish_reason": "stop"
                        }
                    )
                else:
                    logger.warning("Vision chat returned no response, falling back to text LLM")

            # Fallback to text-based LLM if vision unavailable
            logger.info("Using text LLM fallback for user %s", context.user_id)
            return await self._process_with_text_llm(context)

        except Exception as e:
            logger.error(f"Fridge agent error: {e}")
            self.status = AgentStatus.ERROR
            return AgentResponse(
                content="I'm sorry, I encountered an error while processing your request. Please try again.",
                agent_type=self.agent_type,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )

    async def _process_with_text_llm(self, context: AgentContext) -> AgentResponse:
        """
        Fallback processing using text-only LLM with inventory context.

        Used when vision chat is unavailable or fails.
        """
        # Build context for LLM
        system_prompt = SYSTEM_PROMPTS.get("fridge", "")

        # Add inventory context if available
        if context.inventory:
            inventory_context = f"\n\nCurrent Fridge Inventory:\n{self._format_inventory(context.inventory)}"
            full_system_prompt = system_prompt + inventory_context
        else:
            full_system_prompt = system_prompt

        # Generate response using LLM
        response = await self.llm.generate(
            prompt=context.message,
            system_prompt=full_system_prompt,
            chat_history=context.chat_history,
            tools=self._tools
        )

        # Handle tool calls if any
        tool_results = []
        if response.tool_calls:
            for tool_call in response.tool_calls:
                result = await self._execute_tool(tool_call, context)
                tool_results.append(result)

        self.status = AgentStatus.COMPLETED

        return AgentResponse(
            content=response.content,
            agent_type=self.agent_type,
            status=self.status,
            tool_results=tool_results,
            metadata={
                "model": "gemini",
                "vision_enabled": False,
                "finish_reason": response.finish_reason
            }
        )

    def _format_inventory(self, inventory: dict) -> str:
        """Format inventory data for LLM context"""
        if not inventory:
            return "No inventory data available."

        items = inventory.get("items", [])
        if not items:
            return "Fridge appears to be empty."

        formatted = []
        for item in items:
            name = item.get("name", "Unknown")
            quantity = item.get("quantity", "")
            unit = item.get("unit", "")
            expiry = item.get("estimated_expiry", "")

            line = f"- {name}"
            if quantity:
                line += f" ({quantity} {unit})"
            if expiry:
                line += f" - Expires: {expiry}"

            formatted.append(line)

        return "\n".join(formatted)

    async def _execute_tool(self, tool_call: dict, context: AgentContext) -> dict:
        """Execute a tool call"""
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})

        logger.info(f"Executing tool: {tool_name} with args: {arguments}")

        # Tool implementations (mock for now, will connect to real services)
        if tool_name == "get_inventory":
            return {
                "tool": tool_name,
                "result": context.inventory or {"items": [], "message": "No inventory data"}
            }

        elif tool_name == "get_expiring_items":
            days = arguments.get("days", 3)
            # Filter inventory for expiring items
            items = context.inventory.get("items", []) if context.inventory else []
            expiring = [item for item in items if self._is_expiring_soon(item, days)]
            return {
                "tool": tool_name,
                "result": {"expiring_items": expiring, "days_checked": days}
            }

        elif tool_name == "suggest_recipes":
            # In a real implementation, this would call a recipe API
            return {
                "tool": tool_name,
                "result": {"message": "Recipe suggestions would be generated here"}
            }

        elif tool_name == "add_to_shopping_list":
            item = arguments.get("item")
            quantity = arguments.get("quantity", "1")
            return {
                "tool": tool_name,
                "result": {"added": item, "quantity": quantity, "status": "success"}
            }

        return {"tool": tool_name, "result": "Unknown tool"}

    def _is_expiring_soon(self, item: dict, days: int) -> bool:
        """Check if an item is expiring within the given number of days"""
        # Simplified check - in real implementation would compare dates
        expiry = item.get("estimated_expiry", "")
        if "today" in expiry.lower() or "1 day" in expiry.lower():
            return True
        if days >= 3 and "2 day" in expiry.lower():
            return True
        if days >= 7 and "week" in expiry.lower():
            return True
        return False
