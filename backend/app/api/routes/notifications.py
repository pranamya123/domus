"""
Notification endpoints.

Handles notification delivery and management.
WebSocket support for real-time notifications.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, verify_token
from app.models.household import HouseholdMember
from app.models.user import User
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

router = APIRouter()


class NotificationResponse(BaseModel):
    """Single notification response."""
    id: str
    notification_type: str
    severity: str
    title: str
    message: str
    is_read: bool = False
    created_at: str
    read_at: Optional[str] = None


class NotificationListResponse(BaseModel):
    """List of notifications."""
    notifications: List[NotificationResponse]
    total: int
    unread_count: int


class MarkReadRequest(BaseModel):
    """Request to mark notifications as read."""
    notification_ids: List[str]


@router.get("/", response_model=NotificationListResponse)
async def get_notifications(
    user: User = Depends(get_current_user),
    unread_only: bool = False,
    limit: int = 50,
):
    """Get notifications for the current user."""
    notifications = await notification_service.get_user_notifications(
        user_id=user.id,
        limit=limit,
        unread_only=unread_only,
    )

    all_notifications = await notification_service.get_user_notifications(
        user_id=user.id,
        limit=1000,
    )
    unread_count = len([n for n in all_notifications if not n.get("is_read")])

    return NotificationListResponse(
        notifications=[
            NotificationResponse(
                id=n["id"],
                notification_type=n["notification_type"],
                severity=n["severity"],
                title=n["title"],
                message=n["message"],
                is_read=n.get("is_read", False),
                created_at=n["created_at"],
                read_at=n.get("read_at"),
            )
            for n in notifications
        ],
        total=len(notifications),
        unread_count=unread_count,
    )


@router.get("/household", response_model=NotificationListResponse)
async def get_household_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Get notifications for the user's household."""
    # Get household
    membership_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()

    if not membership:
        return NotificationListResponse(notifications=[], total=0, unread_count=0)

    notifications = await notification_service.get_household_notifications(
        household_id=membership.household_id,
        limit=limit,
    )

    unread_count = len([n for n in notifications if not n.get("is_read")])

    return NotificationListResponse(
        notifications=[
            NotificationResponse(
                id=n["id"],
                notification_type=n["notification_type"],
                severity=n["severity"],
                title=n["title"],
                message=n["message"],
                is_read=n.get("is_read", False),
                created_at=n["created_at"],
                read_at=n.get("read_at"),
            )
            for n in notifications
        ],
        total=len(notifications),
        unread_count=unread_count,
    )


@router.post("/read/{notification_id}")
async def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
):
    """Mark a single notification as read."""
    success = await notification_service.mark_as_read(notification_id, user.id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"status": "marked_read", "notification_id": notification_id}


@router.post("/read-all")
async def mark_all_notifications_read(
    user: User = Depends(get_current_user),
):
    """Mark all notifications as read."""
    count = await notification_service.mark_all_read(user.id)
    return {"status": "success", "marked_count": count}


@router.post("/read")
async def mark_notifications_read(
    request: MarkReadRequest,
    user: User = Depends(get_current_user),
):
    """Mark multiple notifications as read."""
    marked = 0
    for notification_id in request.notification_ids:
        if await notification_service.mark_as_read(notification_id, user.id):
            marked += 1

    return {"status": "success", "marked_count": marked}


# WebSocket for real-time notifications
class NotificationConnectionManager:
    """Manages WebSocket connections for notifications."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"Notification WebSocket connected: {user_id}")

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"Notification WebSocket disconnected: {user_id}")

    async def send_notification(self, user_id: str, notification: dict):
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_json({
                    "type": "notification",
                    "notification": notification,
                })
            except Exception as e:
                logger.error(f"Failed to send notification via WebSocket: {e}")
                self.disconnect(user_id)

    async def broadcast_to_household(self, household_id: str, notification: dict, db: AsyncSession):
        """Broadcast notification to all users in a household."""
        result = await db.execute(
            select(HouseholdMember).where(HouseholdMember.household_id == household_id)
        )
        members = result.scalars().all()

        for member in members:
            await self.send_notification(member.user_id, notification)


notification_manager = NotificationConnectionManager()


@router.websocket("/ws/{token}")
async def notification_websocket(
    websocket: WebSocket,
    token: str,
):
    """
    WebSocket endpoint for real-time notifications.

    Token should be the JWT access token.
    """
    # Verify token
    token_data = verify_token(token)
    if not token_data:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = token_data.user_id
    await notification_manager.connect(websocket, user_id)

    try:
        while True:
            # Keep connection alive, handle ping/pong
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "mark_read":
                notification_id = data.get("notification_id")
                if notification_id:
                    await notification_service.mark_as_read(notification_id, user_id)
                    await websocket.send_json({
                        "type": "read_confirmed",
                        "notification_id": notification_id
                    })

    except WebSocketDisconnect:
        notification_manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Notification WebSocket error: {e}")
        notification_manager.disconnect(user_id)
