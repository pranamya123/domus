"""
REST API Routes

Authentication, capabilities, and screen routing endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
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
)

from ..core.auth import (
    mock_gmail_oauth,
    create_session_from_gmail,
    decode_token,
    TokenData,
)
from ..storage.redis_store import RedisDomusStorage
from ..services.blink_service import get_blink_service

router = APIRouter()
security = HTTPBearer(auto_error=False)

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
