"""
Instacart Agent - Manages shopping and product recommendations
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentType, AgentStatus, AgentContext, AgentResponse
from app.llm import GeminiService, get_gemini_service, SYSTEM_PROMPTS
from app.services.instacart_service import InstacartService, get_instacart_service

logger = logging.getLogger(__name__)


# Keywords that indicate shopping-related queries
INSTACART_KEYWORDS = [
    'buy', 'purchase', 'order', 'shop', 'shopping', 'cart',
    'instacart', 'delivery', 'groceries', 'grocery',
    'need', 'running low', 'out of', 'missing',
    'add to cart', 'checkout', 'store'
]


class InstacartAgent(BaseAgent):
    """
    Instacart Agent - Shopping assistant.

    Capabilities:
    - Manage shopping cart
    - Suggest items based on fridge contents
    - Recommend products for specific activities
    - Cross-reference with what's missing
    """

    def __init__(
        self,
        llm_service: Optional[GeminiService] = None,
        instacart_service: Optional[InstacartService] = None
    ):
        super().__init__(AgentType.INSTACART)
        self.llm = llm_service or get_gemini_service()
        self.instacart = instacart_service or get_instacart_service()
        self._tools = self._define_tools()

    def _define_tools(self) -> list[dict]:
        """Define the tools/functions this agent can use."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_cart",
                    "description": "Get the current shopping cart",
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
                    "name": "add_to_cart",
                    "description": "Add an item to the shopping cart",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product": {
                                "type": "string",
                                "description": "Product name or key"
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Quantity to add"
                            }
                        },
                        "required": ["product"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "suggest_missing",
                    "description": "Suggest items that might be missing based on context",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "activity": {
                                "type": "string",
                                "description": "Activity type (workout, cooking, etc.)"
                            }
                        },
                        "required": []
                    }
                }
            }
        ]

    def can_handle(self, message: str) -> bool:
        """Check if message is shopping-related."""
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in INSTACART_KEYWORDS)

    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Process a shopping-related request.

        Args:
            context: Agent context with message and state

        Returns:
            AgentResponse with shopping information
        """
        self.status = AgentStatus.PROCESSING

        try:
            # Get current cart
            cart = await self.instacart.get_cart(context.user_id)

            # Check for specific actions in message
            message_lower = context.message.lower()

            if "add" in message_lower and "cart" in message_lower:
                # Handle add to cart
                response_content = await self._handle_add_to_cart(
                    context.user_id,
                    context.message
                )
            elif "cart" in message_lower or "what's in my cart" in message_lower:
                # Show cart
                response_content = self._format_cart(cart)
            elif "suggest" in message_lower or "recommend" in message_lower:
                # Get suggestions
                fridge_items = self._extract_fridge_items(context.inventory)
                suggestions = await self.instacart.suggest_missing_items(
                    context.user_id,
                    fridge_items,
                    activity_type="workout"  # Default context
                )
                response_content = self._format_suggestions(suggestions)
            else:
                # Use LLM for complex queries
                system_prompt = self._get_default_prompt()
                cart_context = f"\nCurrent cart: {self._format_cart(cart)}"

                response = await self.llm.generate(
                    prompt=f"{system_prompt}{cart_context}\n\nUser: {context.message}",
                    chat_history=context.chat_history
                )
                response_content = response.content

            self.status = AgentStatus.COMPLETED

            return AgentResponse(
                content=response_content,
                agent_type=self.agent_type,
                status=self.status,
                metadata={
                    "cart_total": cart.get("total", 0),
                    "cart_items": cart.get("item_count", 0)
                }
            )

        except Exception as e:
            logger.error(f"Instacart agent error: {e}")
            self.status = AgentStatus.ERROR
            return AgentResponse(
                content="I encountered an error with shopping services. Please try again.",
                agent_type=self.agent_type,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )

    async def _handle_add_to_cart(self, user_id: str, message: str) -> str:
        """Handle add to cart requests."""
        # Simple keyword matching for products
        product_map = {
            "protein": "protein_powder",
            "protein powder": "protein_powder",
            "chicken": "chicken_breast",
            "spinach": "spinach",
            "eggs": "eggs",
            "yogurt": "greek_yogurt",
            "salmon": "salmon",
            "rice": "brown_rice",
            "avocado": "avocado",
            "banana": "banana",
            "milk": "almond_milk",
        }

        message_lower = message.lower()
        added_items = []

        for keyword, product_key in product_map.items():
            if keyword in message_lower:
                result = await self.instacart.add_to_cart(user_id, product_key)
                if result.get("success"):
                    added_items.append(result["added"]["name"])

        if added_items:
            return f"✅ Added to your cart: {', '.join(added_items)}"
        else:
            return "I couldn't identify the product. Try specifying: protein powder, chicken, spinach, eggs, yogurt, salmon, rice, avocado, or banana."

    def _format_cart(self, cart: dict) -> str:
        """Format cart for display."""
        if not cart.get("items"):
            return "🛒 Your cart is empty."

        lines = [f"🛒 **Your Cart** ({cart['store']}):", ""]
        for item in cart["items"]:
            lines.append(
                f"• {item['name']} x{item['quantity']} - ${item['subtotal']:.2f}"
            )

        lines.append("")
        lines.append(f"**Total: ${cart['total']:.2f}**")

        return "\n".join(lines)

    def _format_suggestions(self, suggestions: list[dict]) -> str:
        """Format product suggestions for display."""
        if not suggestions:
            return "You seem well-stocked! No suggestions at this time."

        lines = ["📦 **Suggested Items:**", ""]
        for item in suggestions:
            lines.append(f"• {item['name']} - ${item['price']:.2f}")
            if item.get("reason"):
                lines.append(f"  _{item['reason']}_")

        lines.append("")
        lines.append("Say 'add [item] to cart' to add any of these.")

        return "\n".join(lines)

    def _extract_fridge_items(self, inventory: Optional[dict]) -> list[str]:
        """Extract item names from inventory."""
        if not inventory:
            return []
        return [item.get("name", "") for item in inventory.get("items", [])]

    def _get_default_prompt(self) -> str:
        """Get default system prompt for Instacart agent."""
        return """You are a shopping assistant. Help users manage their grocery shopping,
suggest items they might need, and add products to their cart. Be helpful and suggest
items that complement what they already have."""

    async def suggest_for_activity(
        self,
        user_id: str,
        activity_type: str,
        fridge_items: list[str]
    ) -> dict:
        """
        Get shopping suggestions for a specific activity.

        Used for cross-agent coordination.
        """
        suggestions = await self.instacart.suggest_missing_items(
            user_id,
            fridge_items,
            activity_type=activity_type
        )

        return {
            "activity": activity_type,
            "suggestions": suggestions,
            "suggestion_count": len(suggestions)
        }

    async def add_recommended_item(
        self,
        user_id: str,
        product_key: str,
        reason: str
    ) -> dict:
        """
        Add a recommended item to cart.

        Used for cross-agent coordination.
        """
        result = await self.instacart.add_to_cart(user_id, product_key)
        result["reason"] = reason
        return result
