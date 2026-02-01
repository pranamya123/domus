"""
Instacart Service - Mock E-commerce Integration

TODO: Replace with real Instacart API integration
"""

import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CartItem:
    """Represents an item in the shopping cart."""
    id: str
    name: str
    quantity: int
    unit: str
    price: float
    category: str
    image_url: Optional[str] = None


@dataclass
class ShoppingCart:
    """Represents a user's shopping cart."""
    user_id: str
    items: list[CartItem] = field(default_factory=list)
    store: str = "Whole Foods"
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total(self) -> float:
        return sum(item.price * item.quantity for item in self.items)

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)


class InstacartService:
    """
    Mock Instacart Service for development.

    Provides shopping cart management and product recommendations
    based on what's missing from the user's fridge.
    """

    def __init__(self):
        self._carts: dict[str, ShoppingCart] = {}
        self._product_catalog = self._init_catalog()
        logger.info("InstacartService initialized (mock mode)")

    def _init_catalog(self) -> dict[str, dict]:
        """Initialize mock product catalog."""
        return {
            "protein_powder": {
                "id": "prod_001",
                "name": "Whey Protein Powder (Chocolate)",
                "price": 29.99,
                "category": "supplements",
                "unit": "container",
                "tags": ["protein", "workout", "recovery"]
            },
            "chicken_breast": {
                "id": "prod_002",
                "name": "Organic Chicken Breast",
                "price": 12.99,
                "category": "protein",
                "unit": "lb",
                "tags": ["protein", "meat", "lean"]
            },
            "spinach": {
                "id": "prod_003",
                "name": "Organic Baby Spinach",
                "price": 4.99,
                "category": "produce",
                "unit": "bag",
                "tags": ["vegetable", "greens", "iron"]
            },
            "eggs": {
                "id": "prod_004",
                "name": "Free Range Eggs (12 ct)",
                "price": 6.99,
                "category": "dairy",
                "unit": "dozen",
                "tags": ["protein", "breakfast"]
            },
            "greek_yogurt": {
                "id": "prod_005",
                "name": "Greek Yogurt (Plain)",
                "price": 5.49,
                "category": "dairy",
                "unit": "container",
                "tags": ["protein", "probiotic", "snack"]
            },
            "brown_rice": {
                "id": "prod_006",
                "name": "Organic Brown Rice",
                "price": 4.99,
                "category": "grains",
                "unit": "bag",
                "tags": ["carbs", "fiber", "whole grain"]
            },
            "salmon": {
                "id": "prod_007",
                "name": "Wild Caught Salmon Fillet",
                "price": 14.99,
                "category": "protein",
                "unit": "lb",
                "tags": ["protein", "omega3", "fish"]
            },
            "avocado": {
                "id": "prod_008",
                "name": "Organic Avocados (3 ct)",
                "price": 5.99,
                "category": "produce",
                "unit": "pack",
                "tags": ["healthy fat", "guacamole"]
            },
            "almond_milk": {
                "id": "prod_009",
                "name": "Unsweetened Almond Milk",
                "price": 3.99,
                "category": "dairy alternative",
                "unit": "carton",
                "tags": ["dairy-free", "smoothie"]
            },
            "banana": {
                "id": "prod_010",
                "name": "Organic Bananas",
                "price": 1.99,
                "category": "produce",
                "unit": "bunch",
                "tags": ["fruit", "potassium", "smoothie"]
            },
        }

    async def get_cart(self, user_id: str) -> dict:
        """Get user's current shopping cart."""
        cart = self._carts.get(user_id)
        if not cart:
            cart = ShoppingCart(user_id=user_id)
            self._carts[user_id] = cart

        return self._cart_to_dict(cart)

    async def add_to_cart(
        self,
        user_id: str,
        product_key: str,
        quantity: int = 1
    ) -> dict:
        """
        Add a product to the user's cart.

        Args:
            user_id: User identifier
            product_key: Product key from catalog
            quantity: Number of items to add

        Returns:
            Updated cart state
        """
        if product_key not in self._product_catalog:
            logger.warning("Product not found: %s", product_key)
            return {"success": False, "error": f"Product '{product_key}' not found"}

        product = self._product_catalog[product_key]

        # Get or create cart
        if user_id not in self._carts:
            self._carts[user_id] = ShoppingCart(user_id=user_id)

        cart = self._carts[user_id]

        # Check if item already in cart
        existing = next((i for i in cart.items if i.id == product["id"]), None)
        if existing:
            existing.quantity += quantity
        else:
            cart.items.append(CartItem(
                id=product["id"],
                name=product["name"],
                quantity=quantity,
                unit=product["unit"],
                price=product["price"],
                category=product["category"]
            ))

        logger.info(
            "Added to cart (user=%s, product=%s, qty=%d)",
            user_id, product["name"], quantity
        )

        return {
            "success": True,
            "added": {
                "name": product["name"],
                "quantity": quantity,
                "price": product["price"]
            },
            "cart": self._cart_to_dict(cart)
        }

    async def remove_from_cart(self, user_id: str, product_id: str) -> dict:
        """Remove a product from the cart."""
        cart = self._carts.get(user_id)
        if not cart:
            return {"success": False, "error": "Cart not found"}

        cart.items = [i for i in cart.items if i.id != product_id]
        return {"success": True, "cart": self._cart_to_dict(cart)}

    async def clear_cart(self, user_id: str) -> dict:
        """Clear all items from cart."""
        if user_id in self._carts:
            self._carts[user_id].items = []
        return {"success": True, "cart": await self.get_cart(user_id)}

    async def get_recommendations(
        self,
        user_id: str,
        context: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> list[dict]:
        """
        Get product recommendations based on context.

        Args:
            user_id: User identifier
            context: Context like "workout", "breakfast", etc.
            tags: Specific tags to filter by

        Returns:
            List of recommended products
        """
        recommendations = []

        for key, product in self._product_catalog.items():
            product_tags = product.get("tags", [])

            # Match by tags
            if tags and any(tag in product_tags for tag in tags):
                recommendations.append({
                    "product_key": key,
                    **product
                })
            # Match by context keywords
            elif context:
                context_lower = context.lower()
                if any(tag in context_lower for tag in product_tags):
                    recommendations.append({
                        "product_key": key,
                        **product
                    })

        logger.info(
            "Recommendations generated (user=%s, context=%s, count=%d)",
            user_id, context, len(recommendations)
        )

        return recommendations[:5]  # Return top 5

    async def suggest_missing_items(
        self,
        user_id: str,
        fridge_items: list[str],
        activity_type: Optional[str] = None
    ) -> list[dict]:
        """
        Suggest items that might be missing based on fridge contents and activity.

        Args:
            user_id: User identifier
            fridge_items: List of item names currently in fridge
            activity_type: Type of activity (workout, etc.)

        Returns:
            List of suggested items to purchase
        """
        suggestions = []
        fridge_lower = [item.lower() for item in fridge_items]

        # Check for common staples
        staple_checks = [
            ("protein_powder", ["protein powder", "whey"], "workout"),
            ("eggs", ["eggs", "egg"], None),
            ("chicken_breast", ["chicken"], None),
            ("greek_yogurt", ["yogurt", "greek yogurt"], "workout"),
            ("banana", ["banana", "bananas"], "workout"),
        ]

        for product_key, keywords, activity in staple_checks:
            # Check if item is missing
            has_item = any(kw in " ".join(fridge_lower) for kw in keywords)

            if not has_item:
                # If activity matches or no activity required
                if activity is None or activity_type == activity:
                    product = self._product_catalog[product_key]
                    suggestions.append({
                        "product_key": product_key,
                        "reason": f"Recommended for {activity_type}" if activity_type else "Common staple",
                        **product
                    })

        logger.info(
            "Missing items suggested (user=%s, activity=%s, count=%d)",
            user_id, activity_type, len(suggestions)
        )

        return suggestions

    def _cart_to_dict(self, cart: ShoppingCart) -> dict:
        """Convert ShoppingCart to dictionary."""
        return {
            "user_id": cart.user_id,
            "store": cart.store,
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "price": item.price,
                    "category": item.category,
                    "subtotal": item.price * item.quantity
                }
                for item in cart.items
            ],
            "total": cart.total,
            "item_count": cart.item_count,
        }


# Singleton instance
_instacart_service: Optional[InstacartService] = None


def get_instacart_service() -> InstacartService:
    """Get or create the singleton Instacart service instance."""
    global _instacart_service
    if _instacart_service is None:
        _instacart_service = InstacartService()
    return _instacart_service
