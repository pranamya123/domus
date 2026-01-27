"""
Proactive Alerts API endpoints.

Handles:
- Getting proactive alerts (calendar, expiry, deals)
- Triggering Instacart orders
- Push notification subscriptions
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.domus_orchestrator import orchestrator
from app.core.database import get_db
from app.core.security import verify_token
from app.services.calendar_service import calendar_service
from app.services.instacart_service import instacart_service
from app.services.proactive_monitor import proactive_monitor
from app.services.store_deals_service import store_deals_service

logger = logging.getLogger(__name__)

router = APIRouter()

ANONYMOUS_USER_ID = "anonymous"
ANONYMOUS_HOUSEHOLD_ID = "anonymous_household"


class OrderRequest(BaseModel):
    """Request to create an Instacart order."""
    items: list[str]


class OrderResponse(BaseModel):
    """Response after order creation."""
    order_id: str
    status: str
    items: list
    total: float
    delivery_time: str
    message: str


class PushSubscription(BaseModel):
    """Push notification subscription."""
    endpoint: str
    keys: dict


@router.get("/proactive")
async def get_proactive_alerts(
    authorization: Optional[str] = Header(None),
):
    """
    Get all proactive alerts for the current user.

    Returns calendar ingredient alerts, expiry warnings, and deal notifications.
    """
    user_id = ANONYMOUS_USER_ID
    household_id = ANONYMOUS_HOUSEHOLD_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            user_id = token_data.user_id

    # Get current inventory
    fridge_agent = orchestrator.get_or_create_fridge_agent(household_id)
    fridge_state = await fridge_agent.process({"action": "get_state"})
    inventory = fridge_state.get("inventory", [])

    # Get all alerts
    alerts = await proactive_monitor.get_all_alerts(
        user_id, household_id, inventory
    )

    return alerts


@router.get("/calendar-events")
async def get_calendar_events(
    authorization: Optional[str] = Header(None),
    days_ahead: int = 7,
):
    """Get upcoming calendar events with food-related info."""
    user_id = ANONYMOUS_USER_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            user_id = token_data.user_id

    events = await calendar_service.get_meal_events(user_id, days_ahead)
    return {"events": events, "count": len(events)}


@router.get("/deals")
async def get_store_deals():
    """Get current store deals."""
    deals = await store_deals_service.get_all_deals()
    return {"deals": deals, "count": len(deals)}


@router.get("/deals/recommended")
async def get_recommended_deals(
    authorization: Optional[str] = Header(None),
):
    """Get deals recommended based on your inventory."""
    household_id = ANONYMOUS_HOUSEHOLD_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            # In production, get user's household
            pass

    # Get current inventory
    fridge_agent = orchestrator.get_or_create_fridge_agent(household_id)
    fridge_state = await fridge_agent.process({"action": "get_state"})
    inventory = fridge_state.get("inventory", [])

    recommendations = await store_deals_service.get_bulk_buy_recommendations(
        inventory
    )

    return {"recommendations": recommendations}


@router.post("/order/instacart", response_model=OrderResponse)
async def create_instacart_order(
    request: OrderRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Create an Instacart order for missing items.

    This is a mock implementation - in production would connect to Instacart API.
    """
    user_id = ANONYMOUS_USER_ID
    household_id = ANONYMOUS_HOUSEHOLD_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            user_id = token_data.user_id

    # Create shopping list with products
    shopping_list = await instacart_service.create_shopping_list(
        user_id, request.items
    )

    if not shopping_list["items"]:
        raise HTTPException(
            status_code=400,
            detail=f"No products found for: {', '.join(request.items)}"
        )

    # Create the order
    order = await instacart_service.create_order(
        user_id=user_id,
        household_id=household_id,
        items=shopping_list["items"],
    )

    return OrderResponse(
        order_id=order["order_id"],
        status=order["status"],
        items=order["items"],
        total=order["total"],
        delivery_time=order["delivery_time"],
        message=f"Order created! {len(order['items'])} items totaling ${order['total']:.2f}. Estimated delivery: 2 hours."
    )


@router.post("/order/{order_id}/approve")
async def approve_order(order_id: str):
    """Approve a pending order."""
    result = await instacart_service.approve_order(order_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"status": "approved", "order": result}


@router.post("/order/{order_id}/cancel")
async def cancel_order(order_id: str):
    """Cancel an order."""
    result = await instacart_service.cancel_order(order_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"status": "cancelled", "order": result}


@router.get("/orders")
async def get_orders(
    authorization: Optional[str] = Header(None),
    limit: int = 10,
):
    """Get user's order history."""
    user_id = ANONYMOUS_USER_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            user_id = token_data.user_id

    orders = await instacart_service.get_user_orders(user_id, limit)
    return {"orders": orders, "count": len(orders)}


@router.post("/push/subscribe")
async def subscribe_push(
    subscription: PushSubscription,
    authorization: Optional[str] = Header(None),
):
    """
    Subscribe to push notifications.

    Stores the push subscription for sending mobile notifications.
    """
    user_id = ANONYMOUS_USER_ID

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_data = verify_token(token)
        if token_data:
            user_id = token_data.user_id

    # In production, store this subscription in database
    logger.info(f"Push subscription received for user {user_id}")

    return {
        "status": "subscribed",
        "message": "You will now receive mobile notifications from Domus"
    }


@router.get("/push/vapid-key")
async def get_vapid_key():
    """Get the VAPID public key for push notifications."""
    # In production, this would be a real VAPID key
    return {
        "publicKey": "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U"
    }
