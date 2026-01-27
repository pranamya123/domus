"""
Store Deals Service - Mock store circulars and deals.

Cross-references inventory with local store sales
to recommend optimal buying times.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class StoreDealsService:
    """
    Mocked store deals service for smart budgeting.

    In production, this would integrate with store APIs
    or scrape weekly circulars.
    """

    def __init__(self):
        self._stores = ["Whole Foods", "Trader Joe's", "Costco", "Safeway", "Target"]
        self._mock_deals = self._setup_mock_deals()

    def _setup_mock_deals(self) -> List[Dict[str, Any]]:
        """Set up mock weekly deals."""
        now = datetime.now(timezone.utc)
        week_end = now + timedelta(days=7)

        return [
            {
                "id": "deal_1",
                "item": "eggs",
                "store": "Costco",
                "regular_price": 6.99,
                "sale_price": 4.99,
                "discount_percent": 29,
                "savings": 2.00,
                "quantity": "2 dozen",
                "expires": week_end.isoformat(),
                "bulk_recommended": True,
            },
            {
                "id": "deal_2",
                "item": "milk",
                "store": "Safeway",
                "regular_price": 5.99,
                "sale_price": 3.99,
                "discount_percent": 33,
                "savings": 2.00,
                "quantity": "gallon",
                "expires": week_end.isoformat(),
                "bulk_recommended": False,
            },
            {
                "id": "deal_3",
                "item": "chicken",
                "store": "Whole Foods",
                "regular_price": 9.99,
                "sale_price": 6.99,
                "discount_percent": 30,
                "savings": 3.00,
                "quantity": "per lb",
                "expires": (now + timedelta(days=3)).isoformat(),
                "bulk_recommended": True,
            },
            {
                "id": "deal_4",
                "item": "cheese",
                "store": "Trader Joe's",
                "regular_price": 7.99,
                "sale_price": 5.49,
                "discount_percent": 31,
                "savings": 2.50,
                "quantity": "8 oz block",
                "expires": week_end.isoformat(),
                "bulk_recommended": False,
            },
            {
                "id": "deal_5",
                "item": "bread",
                "store": "Target",
                "regular_price": 5.49,
                "sale_price": 3.99,
                "discount_percent": 27,
                "savings": 1.50,
                "quantity": "loaf",
                "expires": (now + timedelta(days=2)).isoformat(),
                "bulk_recommended": False,
            },
            {
                "id": "deal_6",
                "item": "butter",
                "store": "Costco",
                "regular_price": 4.99,
                "sale_price": 3.49,
                "discount_percent": 30,
                "savings": 1.50,
                "quantity": "4-pack",
                "expires": week_end.isoformat(),
                "bulk_recommended": True,
            },
            {
                "id": "deal_7",
                "item": "orange juice",
                "store": "Safeway",
                "regular_price": 6.99,
                "sale_price": 4.49,
                "discount_percent": 36,
                "savings": 2.50,
                "quantity": "64 oz",
                "expires": (now + timedelta(days=4)).isoformat(),
                "bulk_recommended": False,
            },
            {
                "id": "deal_8",
                "item": "yogurt",
                "store": "Whole Foods",
                "regular_price": 5.99,
                "sale_price": 3.99,
                "discount_percent": 33,
                "savings": 2.00,
                "quantity": "4-pack",
                "expires": week_end.isoformat(),
                "bulk_recommended": True,
            },
        ]

    async def get_all_deals(self) -> List[Dict[str, Any]]:
        """Get all current deals."""
        now = datetime.now(timezone.utc)
        return [
            deal for deal in self._mock_deals
            if datetime.fromisoformat(deal["expires"].replace("Z", "+00:00")) > now
        ]

    async def get_deals_for_items(
        self,
        items: List[str],
    ) -> List[Dict[str, Any]]:
        """Get deals matching specific items."""
        items_lower = set(i.lower() for i in items)
        now = datetime.now(timezone.utc)

        matching = []
        for deal in self._mock_deals:
            if deal["item"].lower() in items_lower:
                exp = datetime.fromisoformat(deal["expires"].replace("Z", "+00:00"))
                if exp > now:
                    matching.append(deal)

        return matching

    async def get_deals_by_store(
        self,
        store_name: str,
    ) -> List[Dict[str, Any]]:
        """Get deals from a specific store."""
        now = datetime.now(timezone.utc)
        return [
            deal for deal in self._mock_deals
            if deal["store"].lower() == store_name.lower()
            and datetime.fromisoformat(deal["expires"].replace("Z", "+00:00")) > now
        ]

    async def get_bulk_buy_recommendations(
        self,
        inventory: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Recommend items to buy in bulk based on:
        - Current deals
        - Low inventory
        - Non-perishable items
        """
        recommendations = []

        # Find items with bulk deals
        bulk_deals = [d for d in self._mock_deals if d.get("bulk_recommended")]

        for deal in bulk_deals:
            recommendation = {
                "item": deal["item"],
                "store": deal["store"],
                "current_price": deal["sale_price"],
                "regular_price": deal["regular_price"],
                "recommended_quantity": 3,
                "total_savings": round(deal["savings"] * 3, 2),
                "reason": f"Buy 3 and save ${round(deal['savings'] * 3, 2)} - deal expires soon!",
                "expires": deal["expires"],
            }
            recommendations.append(recommendation)

        return recommendations

    async def calculate_weekly_savings(
        self,
        shopping_list: List[str],
    ) -> Dict[str, Any]:
        """Calculate potential savings by shopping deals."""
        deals = await self.get_deals_for_items(shopping_list)

        total_regular = sum(d["regular_price"] for d in deals)
        total_sale = sum(d["sale_price"] for d in deals)
        total_savings = round(total_regular - total_sale, 2)

        return {
            "items_with_deals": len(deals),
            "total_items": len(shopping_list),
            "regular_total": round(total_regular, 2),
            "sale_total": round(total_sale, 2),
            "total_savings": total_savings,
            "deals": deals,
            "annual_projection": round(total_savings * 52, 2),  # If you shop weekly
        }


# Global instance
store_deals_service = StoreDealsService()
