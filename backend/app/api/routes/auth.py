"""
Authentication endpoints.

Supports Google OAuth for user authentication.
Phase 1 includes mock auth for development.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user, TokenResponse
from app.models.user import User
from app.models.household import Household, HouseholdMember, MemberRole

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request for development/mock auth."""
    email: EmailStr
    name: str


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    name: str
    picture_url: Optional[str] = None
    household_id: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Authentication response."""
    user: UserResponse
    token: TokenResponse


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Development login endpoint.

    Creates user and household if they don't exist.
    In production, use /auth/google for OAuth.
    """
    # Check if user exists
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Create new user
        user = User(
            id=str(uuid4()),
            email=request.email,
            name=request.name,
            is_verified=True,
        )
        db.add(user)

        # Create default household
        household = Household(
            id=str(uuid4()),
            name=f"{request.name}'s Home",
        )
        db.add(household)

        # Add user as owner
        membership = HouseholdMember(
            id=str(uuid4()),
            user_id=user.id,
            household_id=household.id,
            role=MemberRole.OWNER.value,
        )
        db.add(membership)

        await db.commit()
        await db.refresh(user)

        logger.info(f"Created new user: {user.email}")
    else:
        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()

    # Get household ID
    membership_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()
    household_id = membership.household_id if membership else None

    # Create token
    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "household_id": household_id,
    })

    return AuthResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            picture_url=user.picture_url,
            household_id=household_id,
            created_at=user.created_at.isoformat(),
        ),
        token=TokenResponse(access_token=token),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user info."""
    # Get household ID
    membership_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()
    household_id = membership.household_id if membership else None

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        picture_url=user.picture_url,
        household_id=household_id,
        created_at=user.created_at.isoformat(),
    )


@router.post("/logout")
async def logout():
    """
    Logout endpoint.

    JWT tokens are stateless, so this is a no-op on the server.
    Client should discard the token.
    """
    return {"status": "logged_out"}


# Google OAuth endpoints (to be implemented with real credentials)
@router.get("/google")
async def google_login():
    """Redirect to Google OAuth."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured. Use /auth/login for development."
        )

    # In production, redirect to Google OAuth
    return {
        "message": "Google OAuth not fully implemented. Use /auth/login for development.",
        "google_client_id": settings.google_client_id,
    }


@router.get("/callback")
async def google_callback():
    """Handle Google OAuth callback."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google OAuth callback not implemented. Use /auth/login for development."
    )
