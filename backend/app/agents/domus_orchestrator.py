"""
Domus Orchestrator - Level 0 Agent.

Role: Sole authority for user-facing communication, notification routing,
and external service invocation.

Capabilities:
- Receives intents from Level 1 agents
- Synthesizes intents with User Context, Calendar, Preferences
- Routes approved actions to External Services
- Manages user conversation state

Conversation Ownership:
- All conversational turns are authored and owned by the Orchestrator
- Level 1 agents may only provide data or reasoning context
- No agent may independently generate user-visible responses
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agents.base import AgentIntent, IntentType, Level0Agent
from app.agents.domus_fridge import DomusFridge
from app.core.event_bus import Event, EventType, event_bus
from app.services.calendar_service import calendar_service, MissingIngredients

logger = logging.getLogger(__name__)


class DomusOrchestrator(Level0Agent):
    """
    Level 0 Orchestrator Agent.

    Central coordinator for all agent activities and user communication.
    """

    def __init__(self):
        super().__init__(
            agent_id="domus_orchestrator",
            agent_name="Domus"
        )
        self._conversation_history: Dict[str, List[Dict[str, Any]]] = {}
        self._user_contexts: Dict[str, Dict[str, Any]] = {}
        self._fridge_agents: Dict[str, DomusFridge] = {}

    def get_or_create_fridge_agent(self, household_id: str) -> DomusFridge:
        """Get or create a fridge agent for a household."""
        if household_id not in self._fridge_agents:
            agent = DomusFridge(household_id)
            self._fridge_agents[household_id] = agent
            self.register_l1_agent(agent)
        return self._fridge_agents[household_id]

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process user request and coordinate with L1 agents.

        This is the ONLY method that generates user-visible responses.
        """
        action = context.get("action")
        user_id = context.get("user_id")
        household_id = context.get("household_id")

        if action == "chat":
            return await self._handle_chat(context)
        elif action == "process_image":
            return await self._handle_image_processing(context)
        elif action == "get_inventory":
            return await self._handle_get_inventory(context)
        elif action == "process_intents":
            return await self._process_pending_intents(household_id)
        elif action == "check_calendar":
            return await self._check_calendar_procurement(
                household_id,
                user_id,
                days_ahead=context.get("days_ahead", 7)
            )
        else:
            return {
                "status": "error",
                "response": "I'm not sure how to help with that. Try asking about your fridge contents or upload an image."
            }

    async def _handle_chat(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle user chat message.

        Orchestrator owns all conversation output.
        """
        user_message = context.get("message", "")
        user_id = context.get("user_id")
        household_id = context.get("household_id")

        # Store in conversation history
        if user_id not in self._conversation_history:
            self._conversation_history[user_id] = []

        self._conversation_history[user_id].append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Analyze intent from message
        response = await self._generate_response(
            user_message,
            household_id,
            context
        )

        # Store response in history
        self._conversation_history[user_id].append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return {
            "status": "success",
            "response": response,
        }

    async def _generate_response(
        self,
        user_message: str,
        household_id: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Generate response using Gemini with fridge inventory as context.
        """
        message_lower = user_message.lower()

        # Get fridge agent for context
        fridge_agent = self.get_or_create_fridge_agent(household_id)
        fridge_state = await fridge_agent.process({"action": "get_state"})

        # Simple greetings don't need AI
        if any(word in message_lower for word in ["hello", "hi", "hey"]) and len(user_message.split()) < 4:
            return "Hello! I'm Domus, your smart home assistant. I can help you manage your fridge inventory, track expiration dates, suggest meals, and answer questions about your food. What would you like to know?"

        if any(word in message_lower for word in ["help", "what can"]) and len(user_message.split()) < 6:
            return self._get_help_message()

        # Use Gemini for all other responses with inventory context
        return await self._generate_with_gemini(user_message, fridge_state)

    def _format_inventory_response(self, fridge_state: Dict[str, Any]) -> str:
        """Format inventory for user display."""
        inventory = fridge_state.get("inventory", [])
        if not inventory:
            return "Your fridge appears to be empty. Upload a photo to scan your fridge contents!"

        item_count = len(inventory)
        items_by_category: Dict[str, List[str]] = {}

        for item in inventory:
            category = item.get("category", "other")
            name = item.get("name", "Unknown")
            qty = item.get("quantity", 1)
            item_str = f"{name}" if qty == 1 else f"{name} (x{qty})"

            if category not in items_by_category:
                items_by_category[category] = []
            items_by_category[category].append(item_str)

        response = f"Your fridge contains {item_count} items:\n\n"
        for category, items in items_by_category.items():
            response += f"**{category.title()}**: {', '.join(items)}\n"

        confidence = fridge_state.get("confidence", 0)
        if confidence < 0.7:
            response += f"\n_Note: Detection confidence is {confidence:.0%}. Consider uploading a clearer image._"

        return response

    def _format_expiry_response(self, expiry_data: Dict[str, Any]) -> str:
        """Format expiry information for user."""
        expired = expiry_data.get("expired", [])
        expiring_soon = expiry_data.get("expiring_soon", [])

        if not expired and not expiring_soon:
            return "Great news! Nothing in your fridge is expired or expiring soon."

        response = ""
        if expired:
            response += f"**Expired ({len(expired)} items)** - Please discard:\n"
            for item in expired:
                response += f"- {item['name']} (expired {item['days_expired']} days ago)\n"
            response += "\n"

        if expiring_soon:
            response += f"**Expiring Soon ({len(expiring_soon)} items)** - Use these first:\n"
            for item in expiring_soon:
                days = item['days_until_expiry']
                urgency = "TODAY!" if days == 0 else f"in {days} day{'s' if days > 1 else ''}"
                response += f"- {item['name']} ({urgency})\n"

        return response

    def _format_shopping_response(self, fridge_state: Dict[str, Any]) -> str:
        """Format shopping suggestions."""
        inventory = fridge_state.get("inventory", [])
        current_items = {item.get("name", "").lower() for item in inventory}

        # Common staples to check
        staples = {
            "milk": "dairy",
            "eggs": "dairy",
            "bread": "bakery",
            "butter": "dairy",
            "cheese": "dairy",
            "vegetables": "produce",
            "fruit": "produce",
        }

        missing = []
        for item, category in staples.items():
            if item not in current_items:
                missing.append(f"- {item.title()} ({category})")

        if not missing:
            return "You seem well-stocked on basics! Your fridge has all common staples."

        response = "**Suggested Shopping List:**\n"
        response += "\n".join(missing)
        response += "\n\n_Based on common household staples not detected in your fridge._"

        return response

    def _format_recipe_response(self, fridge_state: Dict[str, Any]) -> str:
        """Suggest recipes based on available ingredients."""
        inventory = fridge_state.get("inventory", [])

        if not inventory:
            return "I need to know what's in your fridge first! Upload a photo to scan your contents."

        items = [item.get("name", "").lower() for item in inventory]

        # Simple recipe suggestions based on ingredients
        suggestions = []

        if "eggs" in items:
            if "cheese" in items:
                suggestions.append("Cheese Omelette")
            if "milk" in items:
                suggestions.append("French Toast")
            suggestions.append("Scrambled Eggs")

        if "chicken" in items:
            suggestions.append("Grilled Chicken")
            if any(v in items for v in ["vegetables", "broccoli", "carrots"]):
                suggestions.append("Chicken Stir Fry")

        if not suggestions:
            suggestions = ["Check online for recipes using: " + ", ".join(items[:5])]

        response = "**Recipe Ideas Based on Your Ingredients:**\n"
        for recipe in suggestions[:5]:
            response += f"- {recipe}\n"

        return response

    async def _generate_with_gemini(
        self,
        user_message: str,
        fridge_state: Dict[str, Any]
    ) -> str:
        """Generate response using Gemini with fridge context."""
        from app.config import get_settings
        settings = get_settings()

        # Format inventory for context
        inventory = fridge_state.get("inventory", [])
        if inventory:
            inventory_text = self._format_inventory_for_context(inventory)
        else:
            inventory_text = "The fridge is empty or hasn't been scanned yet."

        prompt = f"""You are Domus, a helpful smart home assistant that manages a user's fridge inventory.

**Current Fridge Contents:**
{inventory_text}

**User's Question:** {user_message}

FORMATTING RULES (VERY IMPORTANT):
1. If the user asks about fridge contents/inventory, display as a MARKDOWN TABLE:
   | Category | Items |
   |----------|-------|
   | Produce | Lettuce, Tomatoes |
   | Dairy | Milk, Cheese |

2. If the user asks for recipe/dinner ideas, format like this:

   ## Dinner Ideas

   ### 1. Recipe Name
   **Ingredients you have:** item1, item2, item3

   **Quick steps:**
   - Step 1
   - Step 2

   ---

   ### 2. Another Recipe
   (same format)

3. Keep responses clean and well-spaced
4. Use headers (##, ###) to organize sections
5. Use bullet points for lists
6. Add line breaks between sections for readability
7. Be concise - don't repeat the full inventory unless asked"""

        try:
            if settings.has_gemini_key:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                model = genai.GenerativeModel("gemini-2.5-flash-lite")
                response = await model.generate_content_async(prompt)
                return response.text
            else:
                # Fallback if no API key
                return self._fallback_response(user_message, fridge_state)
        except Exception as e:
            logger.error(f"Gemini response generation failed: {e}")
            return self._fallback_response(user_message, fridge_state)

    def _format_inventory_for_context(self, inventory: List[Dict[str, Any]]) -> str:
        """Format inventory list for Gemini context."""
        items_by_category: Dict[str, List[str]] = {}

        for item in inventory:
            category = item.get("category", "other")
            name = item.get("name", "Unknown")
            qty = item.get("quantity", 1)
            item_str = name if qty == 1 else f"{name} (x{qty})"

            if category not in items_by_category:
                items_by_category[category] = []
            items_by_category[category].append(item_str)

        lines = []
        for category, items in items_by_category.items():
            lines.append(f"• {category.title()}: {', '.join(items)}")

        return "\n".join(lines)

    def _fallback_response(self, user_message: str, fridge_state: Dict[str, Any]) -> str:
        """Fallback response when Gemini is unavailable - provide formatted responses."""
        inventory = fridge_state.get("inventory", [])
        message_lower = user_message.lower()

        if not inventory:
            return "The fridge is currently empty. Please scan your items so I can help you manage your inventory!"

        # Check what the user is asking for
        if any(word in message_lower for word in ["what", "show", "list", "inventory", "fridge", "have", "contents"]):
            return self._format_inventory_table(inventory)

        if any(word in message_lower for word in ["dinner", "lunch", "breakfast", "meal", "recipe", "cook", "make", "idea", "eat"]):
            return self._format_recipe_suggestions(inventory)

        if any(word in message_lower for word in ["expir", "expire", "bad", "old", "spoil"]):
            return self._format_expiry_info(inventory)

        # Default helpful response
        return self._format_inventory_table(inventory) + "\n\n---\n\n**What would you like to do?**\n- Ask for dinner ideas\n- Check what's expiring\n- Get shopping suggestions"

    def _format_inventory_table(self, inventory: List[Dict[str, Any]]) -> str:
        """Format inventory as a markdown table."""
        items_by_category: Dict[str, List[str]] = {}

        for item in inventory:
            category = item.get("category", "Other").title()
            name = item.get("name", "Unknown")
            qty = item.get("quantity", 1)
            item_str = name if qty == 1 else f"{name} (x{qty})"

            if category not in items_by_category:
                items_by_category[category] = []
            items_by_category[category].append(item_str)

        response = f"## Your Fridge Inventory\n\n"
        response += f"**Total Items:** {len(inventory)}\n\n"
        response += "| Category | Items |\n"
        response += "|----------|-------|\n"

        for category, items in sorted(items_by_category.items()):
            items_str = ", ".join(items)
            response += f"| {category} | {items_str} |\n"

        return response

    def _format_recipe_suggestions(self, inventory: List[Dict[str, Any]]) -> str:
        """Generate recipe suggestions based on inventory."""
        items = [item.get("name", "").lower() for item in inventory]
        items_set = set(items)

        response = "## Dinner Ideas\n\n"
        recipes = []

        # Check for protein + veggie combinations
        has_chicken = any("chicken" in i for i in items)
        has_eggs = any("egg" in i for i in items)
        has_cheese = any("cheese" in i for i in items)
        has_lettuce = any("lettuce" in i or "salad" in i for i in items)
        has_tomatoes = any("tomato" in i for i in items)
        has_milk = any("milk" in i for i in items)
        has_bread = any("bread" in i for i in items)

        if has_chicken:
            recipes.append({
                "name": "Grilled Chicken Salad",
                "ingredients": "Chicken, Lettuce, Tomatoes, Cheese",
                "steps": ["Season and grill chicken breast", "Chop vegetables", "Combine and add your favorite dressing"]
            })

        if has_eggs and has_cheese:
            recipes.append({
                "name": "Cheese Omelette",
                "ingredients": "Eggs, Cheese, Vegetables",
                "steps": ["Beat eggs with salt and pepper", "Cook in pan, add cheese", "Fold and serve"]
            })

        if has_eggs and has_milk:
            recipes.append({
                "name": "French Toast",
                "ingredients": "Bread, Eggs, Milk",
                "steps": ["Mix eggs and milk", "Dip bread slices", "Fry until golden brown"]
            })

        if has_lettuce and has_tomatoes:
            recipes.append({
                "name": "Fresh Garden Salad",
                "ingredients": "Lettuce, Tomatoes, any vegetables",
                "steps": ["Wash and chop vegetables", "Toss together", "Add dressing of choice"]
            })

        if not recipes:
            # Generic suggestions
            top_items = ", ".join([item.get("name", "") for item in inventory[:6]])
            recipes.append({
                "name": "Custom Stir Fry",
                "ingredients": top_items,
                "steps": ["Heat oil in pan", "Add proteins first, then vegetables", "Season with soy sauce or your favorite sauce"]
            })

        for i, recipe in enumerate(recipes[:3], 1):
            response += f"### {i}. {recipe['name']}\n\n"
            response += f"**Ingredients you have:** {recipe['ingredients']}\n\n"
            response += "**Quick steps:**\n"
            for step in recipe['steps']:
                response += f"- {step}\n"
            response += "\n---\n\n"

        return response

    def _format_expiry_info(self, inventory: List[Dict[str, Any]]) -> str:
        """Format expiry information."""
        response = "## Expiration Check\n\n"

        # Check for items with expiration estimates
        expiring_items = []
        for item in inventory:
            exp = item.get("expiration_estimate")
            if exp:
                expiring_items.append(f"- **{item.get('name')}**: {exp}")

        if expiring_items:
            response += "**Items with expiration dates:**\n\n"
            response += "\n".join(expiring_items)
        else:
            response += "No specific expiration dates detected. Generally:\n\n"
            response += "- **Dairy** (milk, cheese): Use within 1-2 weeks\n"
            response += "- **Meat**: Use within 3-5 days or freeze\n"
            response += "- **Produce**: Varies, check for freshness\n"
            response += "- **Condiments**: Usually last several months"

        return response

    def _get_help_message(self) -> str:
        """Return help message."""
        return """**I'm Domus, your smart fridge assistant!**

Here's what I can help you with:

**Inventory Management**
- "What's in my fridge?"
- "Show my fridge contents"

**Expiration Tracking**
- "What's expiring soon?"
- "Is anything expired?"

**Shopping Assistance**
- "What should I buy?"
- "What staples am I missing?"

**Meal Planning**
- "What can I make for dinner?"
- "Recipe ideas"

**Fridge Scanning**
- Upload a photo of your fridge to update inventory
- IoT camera auto-updates when door opens

Just ask naturally and I'll help!"""

    async def _handle_image_processing(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle image analysis results from vision service.

        Routes to fridge agent and processes resulting intents.
        """
        household_id = context.get("household_id")
        image_analysis = context.get("image_analysis", {})
        image_path = context.get("image_path")  # TODO: Remove - debugging only

        # Get fridge agent and process
        fridge_agent = self.get_or_create_fridge_agent(household_id)
        result = await fridge_agent.process({
            "action": "analyze_image",
            "image_analysis": image_analysis,
            "image_path": image_path,  # TODO: Remove - debugging only
        })

        # Collect and process intents
        intents = fridge_agent.get_pending_intents()
        await self._route_intents(intents, context)

        # Generate user response
        if result.get("status") == "success":
            response = f"Fridge scan complete! Found {result.get('inventory_count', 0)} items."
            if result.get("items_added"):
                response += f" Added: {', '.join(i['name'] for i in result['items_added'][:3])}"
            if result.get("items_removed"):
                response += f" Removed: {', '.join(i['name'] for i in result['items_removed'][:3])}"
        else:
            response = "I had trouble analyzing the image. Please try again with a clearer photo."

        return {
            "status": result.get("status"),
            "response": response,
            "inventory_count": result.get("inventory_count", 0),
        }

    async def _handle_get_inventory(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get current inventory for a household."""
        household_id = context.get("household_id")
        fridge_agent = self.get_or_create_fridge_agent(household_id)
        state = await fridge_agent.process({"action": "get_state"})

        return {
            "status": "success",
            "inventory": state.get("inventory", []),
            "item_count": state.get("item_count", 0),
            "last_updated": state.get("last_analysis", {}).get("timestamp"),
            "latest_image_url": state.get("latest_image_url"),
            "confidence": state.get("confidence", 0),
        }

    async def _process_pending_intents(self, household_id: str) -> Dict[str, Any]:
        """Collect and process all pending intents from L1 agents."""
        intents = await self.collect_intents()
        await self._route_intents(intents, {"household_id": household_id})
        return {"status": "success", "intents_processed": len(intents)}

    async def _check_calendar_procurement(
        self,
        household_id: str,
        user_id: Optional[str] = None,
        days_ahead: int = 7
    ) -> Dict[str, Any]:
        """
        Cross-reference calendar events with inventory.

        Checks upcoming meal events and emits intents for missing ingredients.

        Args:
            household_id: Household to check
            user_id: Optional user ID for calendar lookup
            days_ahead: Days to look ahead

        Returns:
            Summary of calendar check results
        """
        from app.services.notification_service import notification_service

        # Get current inventory from fridge agent
        fridge_agent = self.get_or_create_fridge_agent(household_id)
        state = await fridge_agent.process({"action": "get_state"})
        inventory = state.get("inventory", [])

        # Get events with missing ingredients
        events_with_missing = await calendar_service.get_events_with_missing_ingredients(
            user_id=user_id or household_id,
            inventory=inventory,
            days_ahead=days_ahead
        )

        notifications_created = 0

        for missing_info in events_with_missing:
            event = missing_info.event
            days_until = event.days_away()

            # Determine severity based on urgency
            severity_map = {
                "urgent": "urgent",
                "high": "high",
                "medium": "medium",
                "low": "low"
            }
            severity = severity_map.get(missing_info.procurement_urgency, "medium")

            # Create notification
            await notification_service.create_notification(
                user_id=user_id,
                household_id=household_id,
                notification_type="calendar_event_ingredient_missing",
                title=f"Missing ingredients for {event.title}",
                message=f"You need: {', '.join(missing_info.missing)}. Event in {days_until:.1f} days.",
                severity=severity,
                context={
                    "event_id": event.event_id,
                    "event_title": event.title,
                    "event_date": event.date.isoformat(),
                    "missing_ingredients": missing_info.missing,
                    "available_ingredients": missing_info.available,
                    "procurement_urgency": missing_info.procurement_urgency,
                }
            )
            notifications_created += 1

            # Publish event for calendar missing ingredients
            await event_bus.publish(Event(
                event_type=EventType.INTENT_CALENDAR_INGREDIENT_MISSING,
                payload={
                    "event_id": event.event_id,
                    "event_title": event.title,
                    "missing_ingredients": missing_info.missing,
                    "urgency": missing_info.procurement_urgency,
                },
                source="orchestrator",
                household_id=household_id,
                user_id=user_id,
            ))

        return {
            "status": "success",
            "events_checked": len(events_with_missing) if events_with_missing else 0,
            "notifications_created": notifications_created,
            "events_with_missing": [
                {
                    "event": m.event.title,
                    "missing": m.missing,
                    "urgency": m.procurement_urgency
                }
                for m in events_with_missing
            ]
        }

    async def _route_intents(
        self,
        intents: List[AgentIntent],
        context: Dict[str, Any]
    ) -> None:
        """
        Route intents to appropriate services.

        The Orchestrator may:
        - Override agent conclusions
        - Request re-analysis
        - Transform intents into notifications
        """
        for intent in intents:
            logger.info(f"Processing intent: {intent.intent_type.value}")

            # Publish event for the intent
            await event_bus.publish(Event(
                event_type=self._intent_to_event_type(intent.intent_type),
                payload=intent.to_dict(),
                source="orchestrator",
                household_id=intent.household_id,
            ))

            # Route to notification service if needed
            if intent.intent_type in [
                IntentType.DETECTED_EXPIRY,
                IntentType.EXPIRY_WARNING,
                IntentType.REQUIRE_PROCUREMENT,
                IntentType.HARDWARE_DISCONNECTED,
            ]:
                await self._create_notification_from_intent(intent, context)

    def _intent_to_event_type(self, intent_type: IntentType) -> EventType:
        """Map intent type to event type."""
        mapping = {
            IntentType.DETECTED_EXPIRY: EventType.INTENT_DETECTED_EXPIRY,
            IntentType.EXPIRY_WARNING: EventType.INTENT_EXPIRY_WARNING,
            IntentType.REQUIRE_PROCUREMENT: EventType.INTENT_REQUIRE_PROCUREMENT,
            IntentType.INVENTORY_UPDATED: EventType.INVENTORY_UPDATED,
            IntentType.HARDWARE_DISCONNECTED: EventType.HARDWARE_DISCONNECTED,
            # Temporal events
            IntentType.ITEM_ADDED: EventType.INTENT_ITEM_ADDED,
            IntentType.ITEM_REMOVED: EventType.INTENT_ITEM_REMOVED,
            IntentType.ITEM_MOVED: EventType.INTENT_ITEM_MOVED,
            IntentType.CONSUMPTION_LIKELY: EventType.INTENT_CONSUMPTION_LIKELY,
            # Calendar events
            IntentType.CALENDAR_EVENT_INGREDIENT_MISSING: EventType.INTENT_CALENDAR_INGREDIENT_MISSING,
        }
        return mapping.get(intent_type, EventType.SYSTEM_ERROR)

    async def _create_notification_from_intent(
        self,
        intent: AgentIntent,
        context: Dict[str, Any]
    ) -> None:
        """Transform an intent into a notification."""
        # Import here to avoid circular imports
        from app.services.notification_service import notification_service

        notification_type_map = {
            IntentType.DETECTED_EXPIRY: "perishable_expiry",
            IntentType.EXPIRY_WARNING: "perishable_expiry",
            IntentType.REQUIRE_PROCUREMENT: "procurement_required",
            IntentType.HARDWARE_DISCONNECTED: "hardware_disconnected",
        }

        notification_type = notification_type_map.get(intent.intent_type)
        if not notification_type:
            return

        title, message = self._format_notification_content(intent)

        await notification_service.create_notification(
            user_id=context.get("user_id"),
            household_id=intent.household_id,
            notification_type=notification_type,
            title=title,
            message=message,
            context=intent.payload,
            severity=self._determine_severity(intent),
        )

    def _format_notification_content(self, intent: AgentIntent) -> tuple:
        """Format notification title and message from intent."""
        if intent.intent_type == IntentType.DETECTED_EXPIRY:
            count = intent.payload.get("count", 0)
            return (
                "Expired Items Detected",
                f"{count} item(s) in your fridge have expired and should be discarded."
            )
        elif intent.intent_type == IntentType.EXPIRY_WARNING:
            count = intent.payload.get("count", 0)
            return (
                "Items Expiring Soon",
                f"{count} item(s) will expire within 3 days. Use them soon!"
            )
        elif intent.intent_type == IntentType.REQUIRE_PROCUREMENT:
            items = intent.payload.get("missing_items", [])
            return (
                "Shopping Reminder",
                f"You're running low on: {', '.join(items)}"
            )
        elif intent.intent_type == IntentType.HARDWARE_DISCONNECTED:
            return (
                "Fridge Camera Offline",
                "Your fridge camera has disconnected. Check the device connection."
            )
        else:
            return ("Domus Alert", intent.reasoning or "Check your fridge.")

    def _determine_severity(self, intent: AgentIntent) -> str:
        """Determine notification severity from intent."""
        if intent.intent_type == IntentType.DETECTED_EXPIRY:
            return "high"
        elif intent.intent_type == IntentType.EXPIRY_WARNING:
            return "medium"
        elif intent.intent_type == IntentType.HARDWARE_DISCONNECTED:
            return "high"
        else:
            return "low"


# Global orchestrator instance
orchestrator = DomusOrchestrator()
