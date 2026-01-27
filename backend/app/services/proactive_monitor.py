"""
Proactive Monitoring Service - Background tasks for smart alerts.

Features:
- Calendar event ingredient checking
- 24-hour expiry warnings
- Store deal notifications
- Smart budgeting alerts
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ProactiveMonitor:
    """
    Monitors fridge state and calendar to send proactive alerts.
    """

    def __init__(self):
        self._running = False
        self._check_interval = 3600  # Check every hour
        self._pending_alerts: List[Dict[str, Any]] = []
        self._sent_alerts: set = set()  # Track sent alerts to avoid duplicates

    async def start(self):
        """Start the monitoring loop."""
        if self._running:
            return
        self._running = True
        logger.info("Proactive monitor started")
        asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        logger.info("Proactive monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._run_checks()
            except Exception as e:
                logger.error(f"Monitor check failed: {e}")
            await asyncio.sleep(self._check_interval)

    async def _run_checks(self):
        """Run all proactive checks."""
        # These would run for all households in production
        # For now, we'll check when explicitly called
        pass

    async def check_calendar_ingredients(
        self,
        user_id: str,
        household_id: str,
        inventory: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Check calendar events and find missing ingredients.

        Returns alerts for food-related events missing ingredients.
        """
        from app.services.calendar_service import calendar_service

        alerts = []
        events = await calendar_service.get_meal_events(user_id, days_ahead=7)

        # Get inventory item names (lowercase for matching)
        inventory_names = set(
            item.get("name", "").lower()
            for item in inventory
        )

        for event in events:
            event_start = datetime.fromisoformat(
                event["start"].replace("Z", "+00:00")
            )
            days_until = (event_start - datetime.now(timezone.utc)).days

            needed = event.get("ingredients_needed", [])
            missing = [
                ing for ing in needed
                if ing.lower() not in inventory_names
            ]

            if missing:
                alert_id = f"calendar_{event['id']}_{household_id}"

                # Don't re-alert for same event
                if alert_id not in self._sent_alerts:
                    alert = {
                        "type": "calendar_ingredients",
                        "alert_id": alert_id,
                        "event_name": event["summary"],
                        "event_date": event["start"],
                        "days_until": days_until,
                        "missing_items": missing,
                        "message": self._format_calendar_alert(
                            event["summary"],
                            missing,
                            days_until
                        ),
                        "action": {
                            "type": "order_instacart",
                            "items": missing
                        }
                    }
                    alerts.append(alert)

        return alerts

    async def check_expiring_items(
        self,
        household_id: str,
        inventory: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Check for items expiring within 24 hours.

        Returns alerts for soon-to-expire items.
        """
        alerts = []
        now = datetime.now(timezone.utc)

        for item in inventory:
            exp_str = item.get("expiration_estimate")
            if not exp_str:
                continue

            try:
                # Parse expiration date
                exp_date = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                hours_until = (exp_date - now).total_seconds() / 3600

                # Alert if expiring within 24 hours
                if 0 < hours_until <= 24:
                    alert_id = f"expiry_{item.get('name')}_{household_id}"

                    if alert_id not in self._sent_alerts:
                        alert = {
                            "type": "expiry_warning",
                            "alert_id": alert_id,
                            "item_name": item.get("name"),
                            "hours_until": round(hours_until),
                            "message": f"Your {item.get('name')} expires in {round(hours_until)} hours! Use it today to avoid waste.",
                            "action": {
                                "type": "suggest_recipes",
                                "item": item.get("name")
                            }
                        }
                        alerts.append(alert)

                # Already expired
                elif hours_until <= 0:
                    alert_id = f"expired_{item.get('name')}_{household_id}"

                    if alert_id not in self._sent_alerts:
                        alert = {
                            "type": "item_expired",
                            "alert_id": alert_id,
                            "item_name": item.get("name"),
                            "message": f"Your {item.get('name')} has expired. Consider discarding it.",
                            "action": {
                                "type": "reorder",
                                "item": item.get("name")
                            }
                        }
                        alerts.append(alert)

            except (ValueError, TypeError):
                continue

        return alerts

    async def check_bulk_buy_deals(
        self,
        household_id: str,
        inventory: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Check for bulk buy opportunities based on consumption patterns.

        Returns alerts for optimal buying times.
        """
        from app.services.instacart_service import instacart_service
        from app.services.store_deals_service import store_deals_service

        alerts = []

        # Get items that are running low or frequently used
        low_stock_items = [
            item.get("name") for item in inventory
            if item.get("quantity", 1) <= 1
        ]

        # Check for deals on these items
        deals = await store_deals_service.get_deals_for_items(low_stock_items)

        for deal in deals:
            alert_id = f"deal_{deal['item']}_{household_id}"

            if alert_id not in self._sent_alerts:
                alert = {
                    "type": "bulk_buy_deal",
                    "alert_id": alert_id,
                    "item_name": deal["item"],
                    "store": deal["store"],
                    "regular_price": deal["regular_price"],
                    "sale_price": deal["sale_price"],
                    "savings": deal["savings"],
                    "expires": deal["expires"],
                    "message": f"Deal Alert: {deal['item']} is {deal['discount_percent']}% off at {deal['store']}! Save ${deal['savings']:.2f}",
                    "action": {
                        "type": "order_instacart",
                        "items": [deal["item"]]
                    }
                }
                alerts.append(alert)

        return alerts

    async def get_all_alerts(
        self,
        user_id: str,
        household_id: str,
        inventory: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Get all proactive alerts for a user."""

        calendar_alerts = await self.check_calendar_ingredients(
            user_id, household_id, inventory
        )
        expiry_alerts = await self.check_expiring_items(
            household_id, inventory
        )
        deal_alerts = await self.check_bulk_buy_deals(
            household_id, inventory
        )

        all_alerts = calendar_alerts + expiry_alerts + deal_alerts

        # Sort by priority (expiry > calendar > deals)
        priority_order = {
            "item_expired": 0,
            "expiry_warning": 1,
            "calendar_ingredients": 2,
            "bulk_buy_deal": 3,
        }
        all_alerts.sort(key=lambda x: priority_order.get(x["type"], 99))

        return {
            "alerts": all_alerts,
            "count": len(all_alerts),
            "calendar_count": len(calendar_alerts),
            "expiry_count": len(expiry_alerts),
            "deal_count": len(deal_alerts),
        }

    def mark_alert_sent(self, alert_id: str):
        """Mark an alert as sent to avoid duplicates."""
        self._sent_alerts.add(alert_id)

    def clear_sent_alerts(self):
        """Clear sent alert tracking (for testing)."""
        self._sent_alerts.clear()

    def _format_calendar_alert(
        self,
        event_name: str,
        missing: List[str],
        days_until: int
    ) -> str:
        """Format a calendar ingredient alert message."""
        items_str = ", ".join(missing[:-1])
        if len(missing) > 1:
            items_str += f" and {missing[-1]}"
        else:
            items_str = missing[0]

        time_str = "tomorrow" if days_until == 1 else f"in {days_until} days"

        return f"{items_str} {'is' if len(missing) == 1 else 'are'} missing for {event_name} {time_str}. Order now from Instacart?"


# Global instance
proactive_monitor = ProactiveMonitor()
