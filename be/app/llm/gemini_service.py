"""
Gemini LLM Service - Google Generative AI Integration
"""

import json
import logging
from typing import Optional, AsyncIterator, Any
from dataclasses import dataclass

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from LLM"""
    content: str
    tool_calls: list[dict] = None
    finish_reason: str = "stop"
    usage: dict = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


class GeminiService:
    """
    Gemini LLM Service for Domus agents.

    Supports:
    - Text generation with system prompts
    - Function/tool calling
    - Streaming responses
    - Multi-turn conversations
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key

        if not self.api_key:
            logger.warning("No Gemini API key configured - using mock mode")
            self._mock_mode = True
        else:
            self._mock_mode = False
            genai.configure(api_key=self.api_key)

        self.model_name = settings.gemini_model
        self._model = None
        self._chat_sessions: dict[str, Any] = {}

    @property
    def model(self):
        """Lazy load the Gemini model"""
        if self._model is None and not self._mock_mode:
            self._model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[list[dict]] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Generate a response from Gemini.

        Args:
            prompt: User message
            system_prompt: System instructions for the model
            chat_history: Previous messages for context
            tools: Function definitions for tool calling
            temperature: Creativity parameter (0-1)

        Returns:
            LLMResponse with content and optional tool calls
        """
        if self._mock_mode:
            return await self._mock_generate(prompt, system_prompt, chat_history, tools)

        try:
            # Build the full prompt with system context
            full_prompt = self._build_prompt(prompt, system_prompt, chat_history)

            # Configure generation
            generation_config = {
                "temperature": temperature,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2048,
            }

            # Generate response
            if tools:
                # Convert tools to Gemini function declarations
                function_declarations = self._convert_tools_to_gemini(tools)
                response = await self._generate_with_tools(
                    full_prompt,
                    function_declarations,
                    generation_config
                )
            else:
                response = self.model.generate_content(
                    full_prompt,
                    generation_config=generation_config
                )

            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return LLMResponse(
                content=f"I apologize, but I encountered an error processing your request. Please try again.",
                finish_reason="error"
            )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a response from Gemini.

        Yields chunks of text as they're generated.
        """
        if self._mock_mode:
            # Mock streaming
            mock_response = await self._mock_generate(prompt, system_prompt, chat_history, None)
            for word in mock_response.content.split():
                yield word + " "
            return

        try:
            full_prompt = self._build_prompt(prompt, system_prompt, chat_history)

            response = self.model.generate_content(
                full_prompt,
                stream=True
            )

            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            logger.error(f"Gemini streaming error: {e}")
            yield "I apologize, but I encountered an error. Please try again."

    def _build_prompt(
        self,
        prompt: str,
        system_prompt: Optional[str],
        chat_history: Optional[list[dict]]
    ) -> str:
        """Build the full prompt with context"""
        parts = []

        if system_prompt:
            parts.append(f"System Instructions:\n{system_prompt}\n\n")

        if chat_history:
            parts.append("Conversation History:\n")
            for msg in chat_history[-10:]:  # Last 10 messages for context
                role = msg.get("role", "user")
                content = msg.get("content", "")
                parts.append(f"{role.capitalize()}: {content}\n")
            parts.append("\n")

        parts.append(f"User: {prompt}")

        return "".join(parts)

    def _convert_tools_to_gemini(self, tools: list[dict]) -> list:
        """Convert OpenAI-style tool definitions to Gemini format"""
        declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                declarations.append({
                    "name": func.get("name"),
                    "description": func.get("description"),
                    "parameters": func.get("parameters", {})
                })
        return declarations

    async def _generate_with_tools(
        self,
        prompt: str,
        function_declarations: list,
        generation_config: dict
    ) -> GenerateContentResponse:
        """Generate with function calling enabled"""
        # Note: Gemini's function calling is slightly different
        # We'll use the built-in function calling if available
        tools = genai.protos.Tool(
            function_declarations=[
                genai.protos.FunctionDeclaration(**fd)
                for fd in function_declarations
            ]
        )

        model_with_tools = genai.GenerativeModel(
            model_name=self.model_name,
            tools=[tools],
            generation_config=generation_config
        )

        return model_with_tools.generate_content(prompt)

    def _parse_response(self, response: GenerateContentResponse) -> LLMResponse:
        """Parse Gemini response into LLMResponse"""
        content = ""
        tool_calls = []

        if response.candidates:
            candidate = response.candidates[0]

            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    content += part.text
                elif hasattr(part, 'function_call'):
                    tool_calls.append({
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args)
                    })

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.candidates[0].finish_reason.name if response.candidates else "stop"
        )

    async def _mock_generate(
        self,
        prompt: str,
        system_prompt: Optional[str],
        chat_history: Optional[list[dict]],
        tools: Optional[list[dict]]
    ) -> LLMResponse:
        """Mock response for development without API key"""
        prompt_lower = prompt.lower()

        # Fridge-related queries
        if any(word in prompt_lower for word in ['fridge', 'refrigerator', 'food', 'groceries', 'ingredients', 'eat', 'meal', 'cook']):
            return LLMResponse(
                content=self._get_mock_fridge_response(prompt_lower),
                tool_calls=[],
                finish_reason="stop"
            )

        # Calendar-related queries
        if any(word in prompt_lower for word in ['calendar', 'schedule', 'meeting', 'appointment', 'event', 'reminder', 'today', 'tomorrow', 'week']):
            return LLMResponse(
                content="I can help you manage your calendar! Currently, you have no upcoming events scheduled. Would you like me to help you plan your meals around your schedule?",
                tool_calls=[],
                finish_reason="stop"
            )

        # Energy-related queries
        if any(word in prompt_lower for word in ['energy', 'electricity', 'power', 'bill', 'usage', 'consumption', 'solar', 'thermostat', 'temperature']):
            return LLMResponse(
                content="Your home energy usage looks normal. Current thermostat is set to 72°F. Your estimated electricity bill for this month is around $85. Would you like me to suggest ways to optimize your energy consumption?",
                tool_calls=[],
                finish_reason="stop"
            )

        # Security-related queries
        if any(word in prompt_lower for word in ['security', 'camera', 'lock', 'door', 'alarm', 'motion', 'intruder']):
            return LLMResponse(
                content="All security systems are operational. Front door is locked. No motion detected in the past hour. All cameras are online. Would you like me to show you the camera feeds?",
                tool_calls=[],
                finish_reason="stop"
            )

        # Default response
        return LLMResponse(
            content="Hello! I'm Domus, your smart home assistant. I can help you with:\n\n• **Fridge Management** - Check inventory, suggest meals, track expiration\n• **Calendar** - Manage schedules and meal planning\n• **Energy** - Monitor usage and optimize consumption\n• **Security** - Check cameras, locks, and alarms\n\nWhat would you like help with?",
            tool_calls=[],
            finish_reason="stop"
        )

    def _get_mock_fridge_response(self, prompt: str, has_inventory: bool = True) -> str:
        """Get mock fridge response based on query"""
        if not has_inventory:
            return """I don't have access to your fridge yet! To see what's in your fridge, you'll need to connect your Blink camera first.

**To get started:**
1. Go to Settings → Connect Devices
2. Select "Blink Camera"
3. Follow the setup instructions

Once connected, I'll be able to scan your fridge and help you with:
• Inventory tracking
• Expiration alerts
• Meal suggestions
• Shopping lists

Would you like me to guide you through the Blink setup?"""

        if 'what' in prompt and ('in' in prompt or 'have' in prompt):
            return """Based on my last scan of your fridge, here's what I found:

**Fresh Produce:**
• Apples (4) - Good condition
• Spinach - Use within 2 days
• Carrots (bunch) - Fresh
• Bell peppers (2) - Red and yellow

**Dairy:**
• Milk (1 gallon) - Expires in 5 days
• Greek yogurt (2) - Good until next week
• Cheddar cheese - Fresh

**Proteins:**
• Chicken breast (2 lbs) - Use within 3 days
• Eggs (8 remaining)

**Other:**
• Leftover pasta - Eat today!
• Orange juice - Half full

Would you like meal suggestions based on these ingredients?"""

        elif 'expir' in prompt or 'expire' in prompt or 'bad' in prompt:
            return """⚠️ **Items expiring soon:**

• **Spinach** - Use within 2 days
• **Leftover pasta** - Should be eaten today
• **Chicken breast** - Use within 3 days
• **Milk** - Expires in 5 days

I'd recommend making a chicken stir-fry with spinach tonight to use up those items. Want me to find a recipe?"""

        elif 'recipe' in prompt or 'cook' in prompt or 'make' in prompt or 'meal' in prompt or 'suggest' in prompt:
            return """Based on your current inventory, here are some meal ideas:

🍳 **Tonight's Recommendation: Chicken Stir-Fry**
Uses: chicken, spinach, bell peppers, carrots
Time: 25 minutes

🥗 **Quick Lunch: Greek Yogurt Bowl**
Uses: yogurt, apples
Time: 5 minutes

🍝 **Use It Up: Pasta Remix**
Heat up leftover pasta, add fresh spinach and cheese
Time: 10 minutes

Would you like the full recipe for any of these?"""

        else:
            return """I can help you manage your fridge! Here's what I can do:

• **Check inventory** - "What's in my fridge?"
• **Track expiration** - "What's expiring soon?"
• **Suggest meals** - "What can I cook tonight?"
• **Create shopping list** - "What do I need to buy?"
• **Scan fridge** - "Scan my fridge" (requires connected camera)

What would you like to know?"""


# Singleton instance
_gemini_service: Optional[GeminiService] = None


def get_gemini_service() -> GeminiService:
    """Get or create the singleton Gemini service instance"""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
