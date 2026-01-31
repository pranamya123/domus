"""
Fridge Agent - Manages refrigerator inventory and meal suggestions
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentType, AgentStatus, AgentContext, AgentResponse
from app.llm import GeminiService, get_gemini_service, SYSTEM_PROMPTS

logger = logging.getLogger(__name__)


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
    DFridge Agent - Intelligent refrigerator management.

    Capabilities:
    - Track food inventory with expiration dates
    - Suggest meals based on available ingredients
    - Create shopping lists
    - Reduce food waste
    """

    def __init__(self, llm_service: Optional[GeminiService] = None):
        super().__init__(AgentType.FRIDGE)
        self.llm = llm_service or get_gemini_service()
        self._tools = self._define_tools()

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

    def can_handle(self, message: str) -> bool:
        """Check if message is fridge-related"""
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in FRIDGE_KEYWORDS)

    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Process a fridge-related request.

        Args:
            context: Agent context with message and state

        Returns:
            AgentResponse with the fridge agent's response
        """
        self.status = AgentStatus.PROCESSING

        try:
            # Check if Blink/FridgeSense is connected (inventory available)
            if not context.inventory:
                self.status = AgentStatus.COMPLETED
                return AgentResponse(
                    content="""I don't have access to your fridge yet! To see what's in your fridge, you'll need to connect your Blink camera first.

**To get started:**
1. Go to Settings → Connect Devices
2. Select "Blink Camera"
3. Follow the setup instructions

Once connected, I'll be able to scan your fridge and help you with:
• Inventory tracking
• Expiration alerts
• Meal suggestions
• Shopping lists

Would you like me to guide you through the Blink setup?""",
                    agent_type=self.agent_type,
                    status=AgentStatus.COMPLETED,
                    metadata={"requires_blink": True}
                )

            # Build context for LLM
            system_prompt = SYSTEM_PROMPTS.get("fridge", "")

            # Add inventory context
            inventory_context = f"\n\nCurrent Fridge Inventory:\n{self._format_inventory(context.inventory)}"
            full_system_prompt = system_prompt + inventory_context

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
                    "finish_reason": response.finish_reason
                }
            )

        except Exception as e:
            logger.error(f"Fridge agent error: {e}")
            self.status = AgentStatus.ERROR
            return AgentResponse(
                content="I'm sorry, I encountered an error while processing your request. Please try again.",
                agent_type=self.agent_type,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
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
