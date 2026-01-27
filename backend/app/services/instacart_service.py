"""
Instacart Service - Mocked grocery ordering integration.

This is a mock implementation to demonstrate architecture.
Real integration would require Instacart API credentials.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class InstacartService:
    """
    Mocked Instacart service for grocery procurement.

    In production, this would integrate with Instacart API.
    """

    def __init__(self):
        self._mock_orders: List[Dict[str, Any]] = []
        self._mock_products: Dict[str, Dict[str, Any]] = self._setup_mock_products()

    def _setup_mock_products(self) -> Dict[str, Dict[str, Any]]:
        """Set up mock product catalog."""
        return {
            "milk": {
                "id": "prod_milk",
                "name": "Organic Whole Milk",
                "brand": "Horizon",
                "price": 5.99,
                "unit": "gallon",
                "category": "dairy",
                "image_url": "https://example.com/milk.jpg",
            },
            "eggs": {
                "id": "prod_eggs",
                "name": "Large Brown Eggs",
                "brand": "Vital Farms",
                "price": 6.99,
                "unit": "dozen",
                "category": "dairy",
                "image_url": "https://example.com/eggs.jpg",
            },
            "bread": {
                "id": "prod_bread",
                "name": "Whole Wheat Bread",
                "brand": "Dave's Killer Bread",
                "price": 5.49,
                "unit": "loaf",
                "category": "bakery",
                "image_url": "https://example.com/bread.jpg",
            },
            "butter": {
                "id": "prod_butter",
                "name": "Unsalted Butter",
                "brand": "Kerrygold",
                "price": 4.99,
                "unit": "8oz",
                "category": "dairy",
                "image_url": "https://example.com/butter.jpg",
            },
            "cheese": {
                "id": "prod_cheese",
                "name": "Sharp Cheddar Cheese",
                "brand": "Tillamook",
                "price": 7.99,
                "unit": "block",
                "category": "dairy",
                "image_url": "https://example.com/cheese.jpg",
            },
            "chicken": {
                "id": "prod_chicken",
                "name": "Boneless Skinless Chicken Breast",
                "brand": "Bell & Evans",
                "price": 9.99,
                "unit": "lb",
                "category": "meat",
                "image_url": "https://example.com/chicken.jpg",
            },
            "lettuce": {
                "id": "prod_lettuce",
                "name": "Organic Romaine Hearts",
                "brand": "Earthbound Farm",
                "price": 4.49,
                "unit": "3-pack",
                "category": "produce",
                "image_url": "https://example.com/lettuce.jpg",
            },
            "vegetables": {
                "id": "prod_veggies",
                "name": "Mixed Vegetables",
                "brand": "Green Giant",
                "price": 3.99,
                "unit": "bag",
                "category": "produce",
                "image_url": "https://example.com/veggies.jpg",
            },
        }

    async def search_products(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search for products by name (mocked).

        Returns matching products from mock catalog.
        """
        query_lower = query.lower()
        results = []

        for key, product in self._mock_products.items():
            if query_lower in key or query_lower in product["name"].lower():
                results.append(product)
                if len(results) >= limit:
                    break

        return results

    async def get_product_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a product by name."""
        name_lower = name.lower()
        return self._mock_products.get(name_lower)

    async def create_shopping_list(
        self,
        user_id: str,
        items: List[str],
    ) -> Dict[str, Any]:
        """
        Create a shopping list from item names.

        Returns list with product details and total price.
        """
        shopping_list = []
        total_price = 0.0
        not_found = []

        for item_name in items:
            product = await self.get_product_by_name(item_name)
            if product:
                shopping_list.append({
                    "product": product,
                    "quantity": 1,
                    "subtotal": product["price"],
                })
                total_price += product["price"]
            else:
                not_found.append(item_name)

        return {
            "user_id": user_id,
            "items": shopping_list,
            "item_count": len(shopping_list),
            "total_price": round(total_price, 2),
            "not_found": not_found,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async def create_order(
        self,
        user_id: str,
        household_id: str,
        items: List[Dict[str, Any]],
        delivery_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Create a grocery order (mocked).

        Returns order confirmation with estimated delivery.
        """
        order_id = f"order_{uuid4().hex[:8]}"

        # Calculate totals
        subtotal = sum(item.get("subtotal", 0) for item in items)
        delivery_fee = 5.99
        service_fee = round(subtotal * 0.05, 2)
        total = round(subtotal + delivery_fee + service_fee, 2)

        # Set delivery time
        if not delivery_time:
            delivery_time = datetime.now(timezone.utc) + timedelta(hours=2)

        order = {
            "order_id": order_id,
            "user_id": user_id,
            "household_id": household_id,
            "status": "pending_approval",
            "items": items,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "service_fee": service_fee,
            "total": total,
            "delivery_time": delivery_time.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._mock_orders.append(order)
        logger.info(f"Created mock order: {order_id}")

        return order

    async def approve_order(self, order_id: str) -> Dict[str, Any]:
        """Approve a pending order."""
        for order in self._mock_orders:
            if order["order_id"] == order_id:
                order["status"] = "approved"
                order["approved_at"] = datetime.now(timezone.utc).isoformat()
                return order

        return {"error": "Order not found"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        for order in self._mock_orders:
            if order["order_id"] == order_id:
                order["status"] = "cancelled"
                order["cancelled_at"] = datetime.now(timezone.utc).isoformat()
                return order

        return {"error": "Order not found"}

    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status."""
        for order in self._mock_orders:
            if order["order_id"] == order_id:
                return order
        return None

    async def get_user_orders(
        self,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get orders for a user."""
        user_orders = [o for o in self._mock_orders if o["user_id"] == user_id]
        return user_orders[-limit:]

    async def get_bulk_buy_opportunities(
        self,
        items: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Check for bulk buy opportunities on specified items.

        Returns items with potential savings.
        """
        opportunities = []

        for item_name in items:
            product = await self.get_product_by_name(item_name)
            if product and product["price"] > 5.00:
                # Simulate bulk discount
                bulk_price = round(product["price"] * 0.85, 2)
                savings = round(product["price"] - bulk_price, 2)

                opportunities.append({
                    "product": product,
                    "regular_price": product["price"],
                    "bulk_price": bulk_price,
                    "bulk_quantity": 3,
                    "savings_per_unit": savings,
                    "total_savings": round(savings * 3, 2),
                })

        return opportunities


# Global instacart service instance
instacart_service = InstacartService()
