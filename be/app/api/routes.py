"""
REST API Routes

Authentication, capabilities, and screen routing endpoints.
"""

from datetime import datetime
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from shared.schemas.events import (
    CapabilitiesPayload,
    ScreenType,
    create_ui_screen_event,
    BlinkConnectionState,
)
from shared.schemas.state import (
    UserSession,
    UserProfile,
    DomusState,
    BlinkConnectionWorkflow,
    NotificationRecord,
)

from ..core.auth import (
    mock_gmail_oauth,
    create_session_from_gmail,
    decode_token,
    TokenData,
)
from ..storage.redis_store import RedisDomusStorage
from ..services.blink_service import get_blink_service
from ..services.fridge_inventory_service import FridgeInventoryService

# Media storage path
MEDIA_DIR = Path(__file__).resolve().parent.parent / "storage" / "media"

router = APIRouter()
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

# Storage instance (set during app startup)
_storage: Optional[RedisDomusStorage] = None


def set_storage(storage: RedisDomusStorage):
    """Set storage instance for dependency injection."""
    global _storage
    _storage = storage


def get_storage() -> RedisDomusStorage:
    """Get storage instance."""
    if _storage is None:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    return _storage


async def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    storage: RedisDomusStorage = Depends(get_storage)
) -> UserSession:
    """Validate token and return current session."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )

    token_data = decode_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    session = await storage.state.get_session(UUID(token_data.session_id))
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found"
        )

    if session.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired"
        )

    return session


# ============================================================================
# Request/Response Models
# ============================================================================

class LoginRequest(BaseModel):
    """Gmail OAuth login request."""
    email: EmailStr


class LoginResponse(BaseModel):
    """Login response with token and user info."""
    token: str
    user_id: str
    user_name: str
    user_email: str
    session_id: str
    expires_at: datetime


class CapabilitiesResponse(BaseModel):
    """Current user capabilities."""
    gmail_connected: bool
    blink_connected: bool
    fridge_sense_available: bool
    calendar_connected: bool
    instacart_connected: bool


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    redis_connected: bool
    timestamp: datetime


class ScreenResponse(BaseModel):
    """Current screen for user."""
    screen: ScreenType
    data: Optional[dict] = None


class BlinkLoginRequest(BaseModel):
    """Blink login request."""
    email: EmailStr
    password: str


class BlinkLoginResponse(BaseModel):
    """Blink login response."""
    requires_2fa: bool
    message: str
    capabilities: CapabilitiesPayload


class BlinkVerifyRequest(BaseModel):
    """Blink 2FA verification request."""
    pin: str


class BlinkVerifyResponse(BaseModel):
    """Blink 2FA verification response."""
    success: bool
    message: str
    capabilities: CapabilitiesPayload




class FridgeRefreshRequest(BaseModel):
    """Fridge inventory refresh request."""
    camera_name: Optional[str] = None


# ============================================================================
# Auth Endpoints
# ============================================================================

@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
async def login(
    request: LoginRequest,
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Mock Gmail OAuth login.

    Phase 1: Accepts any email and creates a session.
    Phase 2+: Will integrate with real Google OAuth.
    """
    # Mock Gmail OAuth
    gmail_user = await mock_gmail_oauth(request.email)
    if not gmail_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

    # Create session and profile
    session, profile, token = await create_session_from_gmail(gmail_user)

    # Persist to Redis
    await storage.state.upsert_user(profile)
    await storage.state.create_session(session)

    # Create initial DomusState
    domus_state = DomusState(session=session)
    await storage.state.save_domus_state(domus_state)

    return LoginResponse(
        token=token,
        user_id=session.user_id,
        user_name=session.user_name,
        user_email=session.user_email,
        session_id=str(session.session_id),
        expires_at=session.expires_at
    )


@router.post("/auth/logout", tags=["auth"])
async def logout(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """Logout and invalidate session."""
    await storage.state.delete_session(session.session_id)
    return {"message": "Logged out successfully"}


# ============================================================================
# Capabilities Endpoint
# ============================================================================

@router.get("/capabilities", response_model=CapabilitiesResponse, tags=["capabilities"])
async def get_capabilities(
    session: UserSession = Depends(get_current_session)
):
    """
    Get current user capabilities.

    Returns which services are connected:
    - gmail_connected
    - blink_connected
    - fridge_sense_available
    - calendar_connected
    - instacart_connected
    """
    return CapabilitiesResponse(
        gmail_connected=session.capabilities.gmail_connected,
        blink_connected=session.capabilities.blink_connected,
        fridge_sense_available=session.capabilities.fridge_sense_available,
        calendar_connected=session.capabilities.calendar_connected,
        instacart_connected=session.capabilities.instacart_connected
    )


# ============================================================================
# Blink Integration
# ============================================================================

@router.post("/blink/login", response_model=BlinkLoginResponse, tags=["blink"])
async def blink_login(
    request: BlinkLoginRequest,
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Authenticate with Blink and start 2FA flow.
    """
    blink_service = get_blink_service()
    result = await blink_service.login(
        user_id=session.user_id,
        email=request.email,
        password=request.password
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.get("error", "Blink authentication failed")
        )

    requires_2fa = bool(result.get("requires_2fa"))

    # Update workflow state
    workflow = await storage.state.get_blink_workflow(session.user_id)
    if workflow is None:
        workflow = BlinkConnectionWorkflow(user_id=session.user_id)

    workflow.state = BlinkConnectionState.AWAITING_2FA if requires_2fa else BlinkConnectionState.CONNECTED
    workflow.requires_2fa = requires_2fa
    workflow.blink_account_id = str(result.get("account_id") or "") or None
    workflow.verification_attempts = 0
    workflow.error_message = None
    workflow.last_updated = datetime.utcnow()
    if not requires_2fa:
        workflow.completed_at = datetime.utcnow()

    if not requires_2fa:
        cameras_result = await blink_service.get_cameras(session.user_id)
        if cameras_result.get("success"):
            workflow.cameras = cameras_result.get("cameras", [])
            if not workflow.fridge_camera_name and workflow.cameras:
                workflow.fridge_camera_name = workflow.cameras[0].get("name")
            if not workflow.fridge_camera_name and not workflow.cameras:
                workflow.fridge_camera_name = "Outdoor 4 - KLHX"
            logger.info(
                "Blink cameras discovered (user=%s cameras=%s)",
                session.user_id,
                [cam.get("name") for cam in workflow.cameras],
            )
            media_result = await blink_service.sync_latest_media(
                session.user_id,
                workflow.fridge_camera_name or "Outdoor 4 - KLHX",
                force_video=True,  # Always download video on connect
            )
            logger.info("Blink media synced on connect (user=%s result=%s)", session.user_id, media_result)

    await storage.state.save_blink_workflow(workflow)

    # Update capabilities if fully connected
    if not requires_2fa:
        session.capabilities.blink_connected = True
        session.capabilities.fridge_sense_available = True
        await storage.state.create_session(session)

    # Update aggregate state
    domus_state = await storage.state.get_domus_state(session.session_id)
    if domus_state is None:
        domus_state = DomusState(session=session)
    domus_state.session = session
    domus_state.blink_connection = workflow
    await storage.state.save_domus_state(domus_state)

    return BlinkLoginResponse(
        requires_2fa=requires_2fa,
        message=result.get("message", "Blink login successful"),
        capabilities=session.capabilities
    )


@router.post("/blink/verify", response_model=BlinkVerifyResponse, tags=["blink"])
async def blink_verify_2fa(
    request: BlinkVerifyRequest,
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Verify Blink 2FA PIN and finalize connection.
    """
    workflow = await storage.state.get_blink_workflow(session.user_id)
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending Blink authentication. Please login again."
        )

    if not workflow.can_verify_2fa():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA verification not allowed. Please restart Blink login."
        )

    blink_service = get_blink_service()
    result = await blink_service.verify_2fa(session.user_id, request.pin)

    if not result.get("success"):
        workflow.verification_attempts += 1
        workflow.last_updated = datetime.utcnow()
        workflow.error_message = result.get("error", "Invalid verification code")
        if workflow.verification_attempts >= workflow.max_verification_attempts:
            workflow.state = BlinkConnectionState.FAILED
        await storage.state.save_blink_workflow(workflow)

        domus_state = await storage.state.get_domus_state(session.session_id)
        if domus_state is None:
            domus_state = DomusState(session=session)
        domus_state.session = session
        domus_state.blink_connection = workflow
        await storage.state.save_domus_state(domus_state)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=workflow.error_message
        )

    workflow.state = BlinkConnectionState.CONNECTED
    workflow.completed_at = datetime.utcnow()
    workflow.last_updated = datetime.utcnow()
    workflow.error_message = None

    cameras_result = await blink_service.get_cameras(session.user_id)
    if cameras_result.get("success"):
        workflow.cameras = cameras_result.get("cameras", [])
        if not workflow.fridge_camera_name and workflow.cameras:
            workflow.fridge_camera_name = workflow.cameras[0].get("name")
        if not workflow.fridge_camera_name and not workflow.cameras:
            workflow.fridge_camera_name = "Outdoor 4 - KLHX"
        logger.info(
            "Blink cameras discovered (user=%s cameras=%s)",
            session.user_id,
            [cam.get("name") for cam in workflow.cameras],
        )
        media_result = await blink_service.sync_latest_media(
            session.user_id,
            workflow.fridge_camera_name or "Outdoor 4 - KLHX",
            force_video=True,  # Always download video on connect
        )
        logger.info("Blink media synced on connect (user=%s result=%s)", session.user_id, media_result)

    await storage.state.save_blink_workflow(workflow)

    # Update capabilities
    session.capabilities.blink_connected = True
    session.capabilities.fridge_sense_available = True
    await storage.state.create_session(session)

    # Update aggregate state
    domus_state = await storage.state.get_domus_state(session.session_id)
    if domus_state is None:
        domus_state = DomusState(session=session)
    domus_state.session = session
    domus_state.blink_connection = workflow
    await storage.state.save_domus_state(domus_state)

    return BlinkVerifyResponse(
        success=True,
        message="Blink camera connected successfully",
        capabilities=session.capabilities
    )


# ============================================================================
# Fridge Inventory (Iteration 1)
# ============================================================================

@router.post("/fridge/refresh", tags=["fridge"])
async def refresh_fridge_inventory(
    request: FridgeRefreshRequest,
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage),
):
    """Capture a fridge snapshot and refresh inventory."""
    service = FridgeInventoryService(storage)
    result = await service.refresh(session.user_id, camera_name=request.camera_name)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Unable to refresh inventory"),
        )
    return result


@router.get("/fridge/inventory", tags=["fridge"])
async def get_fridge_inventory(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage),
):
    """Get latest stored fridge inventory."""
    service = FridgeInventoryService(storage)
    inventory = await service.get_latest(session.user_id)
    if not inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No inventory snapshot found",
        )
    return inventory




# ============================================================================
# Media Endpoints (Latest Thumbnail & Video)
# ============================================================================

@router.get("/media/thumbnail", tags=["media"])
async def get_latest_thumbnail(
    session: UserSession = Depends(get_current_session),
):
    """
    Get the latest thumbnail from Blink camera.

    Returns the most recent thumbnail image (JPEG).
    Updated on connect and when motion is detected.
    """
    thumbnail_path = MEDIA_DIR / "latest_thumbnail.jpg"

    if not thumbnail_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No thumbnail available. Connect Blink camera first."
        )

    return FileResponse(
        path=thumbnail_path,
        media_type="image/jpeg",
        filename="latest_thumbnail.jpg",
    )


@router.get("/media/video", tags=["media"])
async def get_latest_video(
    session: UserSession = Depends(get_current_session),
):
    """
    Get the latest video clip from Blink camera.

    Returns the most recent video clip (MP4).
    Updated on connect and when motion is detected.
    """
    video_path = MEDIA_DIR / "latest_clip.mp4"

    if not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No video available. Connect Blink camera first."
        )

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename="latest_clip.mp4",
    )


@router.get("/media/status", tags=["media"])
async def get_media_status(
    session: UserSession = Depends(get_current_session),
):
    """
    Get status of available media files.

    Returns info about latest thumbnail and video including file sizes and timestamps.
    """
    thumbnail_path = MEDIA_DIR / "latest_thumbnail.jpg"
    video_path = MEDIA_DIR / "latest_clip.mp4"

    result = {
        "thumbnail": None,
        "video": None,
    }

    if thumbnail_path.exists():
        stat = thumbnail_path.stat()
        result["thumbnail"] = {
            "available": True,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    if video_path.exists():
        stat = video_path.stat()
        result["video"] = {
            "available": True,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    return result


# ============================================================================
# Screen Router (Backend-Driven Navigation)
# ============================================================================

@router.get("/screen", response_model=ScreenResponse, tags=["navigation"])
async def get_current_screen(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Get current screen for user based on their state.

    Backend-driven screen routing:
    - If no Blink connected and fridge agent requested -> connect_fridge_sense
    - If Blink needs 2FA -> blink_2fa
    - Otherwise -> chat
    """
    # Get full state
    state = await storage.state.get_domus_state(session.session_id)

    # Determine screen based on state
    if state and state.blink_connection:
        from shared.schemas.events import BlinkConnectionState

        blink_state = state.blink_connection.state

        if blink_state == BlinkConnectionState.AWAITING_2FA:
            return ScreenResponse(
                screen=ScreenType.BLINK_2FA,
                data={"attempts_remaining": state.blink_connection.max_verification_attempts - state.blink_connection.verification_attempts}
            )
        elif blink_state == BlinkConnectionState.CONNECTED:
            return ScreenResponse(
                screen=ScreenType.CHAT,
                data={"fridge_connected": True}
            )
        elif blink_state == BlinkConnectionState.CONNECT_STARTED:
            return ScreenResponse(
                screen=ScreenType.CONNECT_FRIDGE_SENSE,
                data={"oauth_state": state.blink_connection.oauth_state_param}
            )

    # Default to chat
    return ScreenResponse(screen=ScreenType.CHAT)


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check(storage: RedisDomusStorage = Depends(get_storage)):
    """Health check endpoint."""
    redis_ok = await storage.health_check()
    return HealthResponse(
        status="healthy" if redis_ok else "degraded",
        redis_connected=redis_ok,
        timestamp=datetime.utcnow()
    )


# ============================================================================
# Session Info
# ============================================================================

@router.get("/me", tags=["auth"])
async def get_current_user(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """Get current user information."""
    profile = await storage.state.get_user(session.user_id)

    return {
        "user_id": session.user_id,
        "email": session.user_email,
        "name": session.user_name,
        "picture": profile.picture_url if profile else None,
        "session_expires": session.expires_at.isoformat(),
        "capabilities": session.capabilities.model_dump()
    }


# ============================================================================
# Notifications API
# ============================================================================

class NotificationResponse(BaseModel):
    """Single notification in response."""
    notification_id: str
    title: str
    body: str
    sent_at: datetime
    read_at: Optional[datetime] = None
    notification_type: str = "chat"  # "chat" | "proactive"
    chat_seed_content: Optional[str] = None
    event_id: Optional[str] = None


class NotificationsListResponse(BaseModel):
    """List of notifications with unread count."""
    notifications: list[NotificationResponse]
    unread_count: int


class NotificationResolveResponse(BaseModel):
    """Response when resolving notification to chat."""
    notification_id: str
    chat_seed_content: str
    marked_read: bool


@router.get("/notifications", response_model=NotificationsListResponse, tags=["notifications"])
async def get_notifications(
    limit: int = Query(default=50, le=100),
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Get all notifications for the current user.

    Returns notifications sorted by sent_at (newest first) with unread count.
    Used to populate the notifications bell panel.
    """
    notifications = await storage.state.get_notifications(session.user_id, limit=limit)
    unread_count = await storage.state.get_unread_count(session.user_id)
    logger.info("GET /notifications user_id=%s count=%d unread=%d", session.user_id, len(notifications), unread_count)

    return NotificationsListResponse(
        notifications=[
            NotificationResponse(
                notification_id=str(n.notification_id),
                title=n.title,
                body=n.body,
                sent_at=n.sent_at,
                read_at=n.read_at,
                notification_type=n.notification_type,
                chat_seed_content=n.chat_seed_content,
                event_id=n.event_id,
            )
            for n in notifications
        ],
        unread_count=unread_count
    )


@router.get("/notifications/unread-count", tags=["notifications"])
async def get_unread_count(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """Get just the unread notification count (for badge updates)."""
    count = await storage.state.get_unread_count(session.user_id)
    return {"unread_count": count}


@router.post("/notifications/{notification_id}/resolve", response_model=NotificationResolveResponse, tags=["notifications"])
async def resolve_notification_to_chat(
    notification_id: str,
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Resolve a notification to chat.

    When user clicks a notification:
    1. Fetch the notification
    2. Return the chat_seed_content (pre-seeded assistant message)
    3. Mark notification as read

    The frontend should insert chat_seed_content as the latest assistant message
    and continue the conversation normally.
    """
    notification = await storage.state.get_notification(UUID(notification_id))

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    if notification.user_id != session.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Mark as read
    updated = await storage.state.mark_notification_read(UUID(notification_id))

    # Return chat seed content (use body if no explicit seed)
    chat_content = notification.chat_seed_content or f"{notification.title}\n\n{notification.body}"

    return NotificationResolveResponse(
        notification_id=notification_id,
        chat_seed_content=chat_content,
        marked_read=updated.read_at is not None if updated else False
    )


@router.post("/notifications/test", tags=["notifications"])
async def create_test_notification(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Create a test proactive notification for development/testing.

    This simulates what the EventEvaluationRunner would create when it
    detects a calendar event with missing ingredients.
    """
    from uuid import uuid4

    notification_id = uuid4()
    title = "Prep reminder: School Bake Sale"
    body = "You may be missing: flour, sugar, vanilla. Check your fridge before tomorrow!"
    chat_seed_content = f"{title}\n\n{body}"

    notification = NotificationRecord(
        notification_id=notification_id,
        user_id=session.user_id,
        title=title,
        body=body,
        notification_type="proactive",
        chat_seed_content=chat_seed_content,
        event_id="test_event_001",
        idempotency_key=f"test_{uuid4()}",
    )

    await storage.state.save_notification(notification)
    logger.info("POST /notifications/test created notification_id=%s for user_id=%s", notification_id, session.user_id)

    # Also publish a WebSocket event for real-time UI update
    from shared.schemas.events import DomusEvent, EventType
    notification_event = DomusEvent(
        type=EventType.NOTIFICATION_CREATED,
        payload={
            "notification_id": str(notification_id),
            "title": title,
            "body": body,
            "notification_type": "proactive",
            "event_id": "test_event_001",
        }
    )
    await storage.events.publish(notification_event, session.user_id)

    return {
        "notification_id": str(notification_id),
        "title": title,
        "body": body,
        "message": "Test notification created and pushed via WebSocket"
    }


# ============================================================================
# Push Notification Configuration (Demo)
# ============================================================================

class SetDeviceTokenRequest(BaseModel):
    """Request to set demo device token."""
    token: str


@router.post("/push/device-token", tags=["push"])
async def set_device_token(
    request: SetDeviceTokenRequest,
    session: UserSession = Depends(get_current_session),
):
    """
    Set the demo device token for iOS push notifications.

    Get this token from iOS app console logs after push registration.
    Use this to configure the backend to send pushes to your test device.
    """
    from ..services.push_notification_service import get_push_notification_service

    push_service = get_push_notification_service()
    push_service.set_demo_token(request.token)

    return {
        "message": "Device token set successfully",
        "configured": push_service.is_configured
    }


@router.get("/push/status", tags=["push"])
async def get_push_status(
    session: UserSession = Depends(get_current_session),
):
    """
    Check push notification configuration status.

    Returns whether FCM is configured and ready to send notifications.
    """
    from ..services.push_notification_service import get_push_notification_service

    push_service = get_push_notification_service()

    return {
        "configured": push_service.is_configured,
        "has_server_key": bool(push_service.fcm_server_key),
        "has_device_token": bool(push_service.demo_device_token),
    }


@router.post("/push/test", tags=["push"])
async def send_test_push(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Send a test push notification to the configured demo device.

    This sends an actual iOS push notification and also creates a
    notification record for the bell panel.
    """
    from uuid import uuid4
    from ..services.push_notification_service import get_push_notification_service

    push_service = get_push_notification_service()

    if not push_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Push not configured. Set FCM_SERVER_KEY env var and call POST /push/device-token first."
        )

    notification_id = uuid4()
    title = "Test Push from Domus"
    body = "Tap to open the app and continue the conversation"
    chat_seed_content = f"{title}\n\n{body}"

    # Create notification record
    notification = NotificationRecord(
        notification_id=notification_id,
        user_id=session.user_id,
        title=title,
        body=body,
        notification_type="proactive",
        chat_seed_content=chat_seed_content,
        idempotency_key=f"test_push_{uuid4()}",
    )
    await storage.state.save_notification(notification)

    # Send actual iOS push
    result = await push_service.send_notification(
        user_id=session.user_id,
        title=title,
        body=body,
        notification_id=str(notification_id),
    )

    # Also emit WebSocket event
    from shared.schemas.events import DomusEvent, EventType
    notification_event = DomusEvent(
        type=EventType.NOTIFICATION_CREATED,
        payload={
            "notification_id": str(notification_id),
            "title": title,
            "body": body,
            "notification_type": "proactive",
        }
    )
    await storage.events.publish(notification_event, session.user_id)

    return {
        "notification_id": str(notification_id),
        "push_sent": result.success,
        "push_message_id": result.message_id,
        "push_error": result.error,
        "message": "Test push sent" if result.success else f"Push failed: {result.error}"
    }


# ============================================================================
# Location / Geofencing (Demo)
# ============================================================================

class GeofenceEntryRequest(BaseModel):
    """Request when user enters a geofence."""
    place_id: str
    timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@router.get("/location/geofences", tags=["location"])
async def get_demo_geofences(
    session: UserSession = Depends(get_current_session),
):
    """
    Get demo store geofences for iOS registration.

    Returns list of stores with coordinates and radius for CLCircularRegion.
    iOS app should call this on launch and register these geofences.
    """
    from ..services.location_service import get_location_service

    location_service = get_location_service()
    stores = location_service.get_demo_stores()

    return {
        "geofences": stores,
        "count": len(stores),
        "message": "Register these geofences with CLLocationManager"
    }


@router.post("/location/entered", tags=["location"])
async def handle_geofence_entry(
    request: GeofenceEntryRequest,
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Handle geofence entry event from iOS.

    Called when iOS detects user entered a registered geofence.
    This is the critical endpoint that triggers grocery notifications.

    Flow:
    1. iOS detects didEnterRegion
    2. iOS sends POST /location/entered with place_id
    3. Backend checks inventory for low/out items
    4. Backend sends push notification if conditions match
    """
    from ..services.location_service import get_location_service, GeofenceEntry
    from ..services.grocery_notification_service import get_grocery_notification_service

    location_service = get_location_service()
    grocery_service = get_grocery_notification_service(storage)

    # Create entry event
    entry = GeofenceEntry(
        user_id=session.user_id,
        place_id=request.place_id,
        timestamp=request.timestamp or datetime.utcnow(),
        latitude=request.latitude,
        longitude=request.longitude,
    )

    # Validate entry and get store info
    store = location_service.validate_entry(entry)
    if not store:
        return {
            "triggered": False,
            "reason": "Unknown or non-grocery store"
        }

    # Check inventory and send notification if needed
    notification = await grocery_service.handle_geofence_entry(entry, store)

    if notification:
        # Also emit WebSocket event for real-time UI update
        from shared.schemas.events import DomusEvent, EventType
        notification_event = DomusEvent(
            type=EventType.NOTIFICATION_CREATED,
            payload={
                "notification_id": notification["notification_id"],
                "title": notification["title"],
                "body": notification["body"],
                "notification_type": "proactive",
            }
        )
        await storage.events.publish(notification_event, session.user_id)

        return {
            "triggered": True,
            "notification_id": notification["notification_id"],
            "store": notification["store"],
            "item": notification["item"],
            "message": f"Notification sent for {notification['item']} at {notification['store']}"
        }

    return {
        "triggered": False,
        "reason": "No low items or cooldown active"
    }


@router.post("/location/test-entry", tags=["location"])
async def test_geofence_entry(
    session: UserSession = Depends(get_current_session),
    storage: RedisDomusStorage = Depends(get_storage)
):
    """
    Test endpoint to simulate a geofence entry.

    Simulates entering the demo Whole Foods location.
    Use this to test the notification flow without actually moving.
    """
    from ..services.location_service import get_location_service, GeofenceEntry
    from ..services.grocery_notification_service import get_grocery_notification_service

    location_service = get_location_service()
    grocery_service = get_grocery_notification_service(storage)

    # Simulate entering demo grocery store
    entry = GeofenceEntry(
        user_id=session.user_id,
        place_id="demo_grocery",
        timestamp=datetime.utcnow(),
    )

    store = location_service.validate_entry(entry)
    if not store:
        return {"error": "Demo store not found"}

    notification = await grocery_service.handle_geofence_entry(entry, store)

    if notification:
        # Emit WebSocket event
        from shared.schemas.events import DomusEvent, EventType
        notification_event = DomusEvent(
            type=EventType.NOTIFICATION_CREATED,
            payload={
                "notification_id": notification["notification_id"],
                "title": notification["title"],
                "body": notification["body"],
                "notification_type": "proactive",
            }
        )
        await storage.events.publish(notification_event, session.user_id)

        return {
            "success": True,
            "notification": notification,
            "message": "Test geofence entry triggered notification"
        }

    return {
        "success": False,
        "message": "No notification sent (cooldown active or no low items)"
    }
