"""
Domus Authentication

Mock Gmail OAuth for Phase 1.
JWT-based session tokens.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from shared.schemas.state import UserSession, UserProfile
from shared.schemas.events import CapabilitiesPayload
from .config import settings


# Password hashing (for future use)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenData(BaseModel):
    """JWT token payload."""
    session_id: str
    user_id: str
    exp: datetime


class MockGmailUser(BaseModel):
    """Mock Gmail OAuth response."""
    id: str
    email: str
    name: str
    picture: Optional[str] = None


# Mock Gmail users for development
MOCK_GMAIL_USERS = {
    "demo@domus.ai": MockGmailUser(
        id="mock-user-001",
        email="demo@domus.ai",
        name="Domus Demo User",
        picture="https://ui-avatars.com/api/?name=Domus+Demo&background=E8F5E9&color=2E7D32"
    ),
    "test@example.com": MockGmailUser(
        id="mock-user-002",
        email="test@example.com",
        name="Test User",
        picture="https://ui-avatars.com/api/?name=Test+User&background=E8F5E9&color=2E7D32"
    ),
}


def create_access_token(session_id: UUID, user_id: str) -> str:
    """Create JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {
        "session_id": str(session_id),
        "user_id": user_id,
        "exp": expire
    }
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenData(
            session_id=payload["session_id"],
            user_id=payload["user_id"],
            exp=datetime.fromtimestamp(payload["exp"])
        )
    except JWTError:
        return None


async def mock_gmail_oauth(email: str) -> Optional[MockGmailUser]:
    """
    Mock Gmail OAuth flow.

    In production, this would:
    1. Redirect to Google OAuth
    2. Exchange code for tokens
    3. Fetch user info

    For Phase 1, we accept any email and create a mock user.
    """
    # Check if we have a predefined mock user
    if email in MOCK_GMAIL_USERS:
        return MOCK_GMAIL_USERS[email]

    # Create a dynamic mock user for any email
    return MockGmailUser(
        id=f"mock-{uuid4().hex[:8]}",
        email=email,
        name=email.split("@")[0].replace(".", " ").title(),
        picture=f"https://ui-avatars.com/api/?name={email.split('@')[0]}&background=E8F5E9&color=2E7D32"
    )


async def create_session_from_gmail(gmail_user: MockGmailUser) -> tuple[UserSession, UserProfile, str]:
    """
    Create session and profile from Gmail user.

    Returns: (session, profile, token)
    """
    session_id = uuid4()
    expires_at = datetime.utcnow() + timedelta(seconds=settings.session_ttl_seconds)

    # Create user profile
    profile = UserProfile(
        user_id=gmail_user.id,
        email=gmail_user.email,
        name=gmail_user.name,
        picture_url=gmail_user.picture,
        last_login=datetime.utcnow()
    )

    # Create session with default capabilities
    session = UserSession(
        session_id=session_id,
        user_id=gmail_user.id,
        user_name=gmail_user.name,
        user_email=gmail_user.email,
        expires_at=expires_at,
        capabilities=CapabilitiesPayload(
            gmail_connected=True,  # We just authenticated with Gmail
            blink_connected=False,
            fridge_sense_available=False,
            calendar_connected=False,
            instacart_connected=False
        )
    )

    # Create JWT token
    token = create_access_token(session_id, gmail_user.id)

    return session, profile, token
