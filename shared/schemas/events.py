"""
Domus Event Protocol - Contract-First Design

All events emitted via WebSocket/SSE must conform to this schema.
This is the single source of truth for event structure.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Reserved event types for Domus system."""

    # UI Navigation (backend-driven screen routing)
    UI_SCREEN = "ui.screen"

    # Agent lifecycle
    AGENT_STATUS = "agent.status"

    # Workflow progression
    WORKFLOW_STEP = "workflow.step"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    # Approval flow
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_RESULT = "approval.result"

    # Notifications
    NOTIFICATION_SENT = "notification.sent"

    # Chat messages
    CHAT_USER_MESSAGE = "chat.user_message"
    CHAT_ASSISTANT_MESSAGE = "chat.assistant_message"

    # System
    HEARTBEAT = "system.heartbeat"
    ERROR = "error"

    # Capabilities
    CAPABILITIES_UPDATED = "capabilities.updated"


class AgentStatus(str, Enum):
    """Agent activation states."""
    ACTIVATING = "activating"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"


class AgentType(str, Enum):
    """Available agent types."""
    FRIDGE = "fridge"
    CALENDAR = "calendar"
    SERVICES = "services"
    IDENTITY = "identity"
    NOTIFICATION = "notification"


class ScreenType(str, Enum):
    """UI screens that backend can request."""
    SPLASH = "splash"
    LANDING = "landing"
    LOGIN = "login"
    CHAT = "chat"
    CONNECT_FRIDGE_SENSE = "connect_fridge_sense"
    BLINK_2FA = "blink_2fa"
    FRIDGE_SENSE_SUCCESS = "fridge_sense_success"
    ACTIVITY_CENTER = "activity_center"
    MENU = "menu"


class BlinkConnectionState(str, Enum):
    """Blink OAuth workflow states - resumable."""
    NOT_STARTED = "not_started"
    CONNECT_STARTED = "blink_connect_started"
    OAUTH_RETURNED = "oauth_returned"
    AWAITING_2FA = "awaiting_2fa"
    VERIFIED = "verified"
    CONNECTED = "connected"
    FAILED = "failed"


class WorkflowState(str, Enum):
    """Generic workflow states for activity center."""
    ACTIVE = "active"
    ACTION_REQUIRED = "action_required"
    COMPLETED = "completed"
    PROCESSING = "processing"
    PROACTIVE = "proactive"
    INTERRUPTED = "interrupted"


# ============================================================================
# Event Envelope - The core event structure
# ============================================================================

class DomusEvent(BaseModel):
    """
    Base event envelope for all Domus events.

    All events emitted via WebSocket/SSE must use this structure.
    The payload is typed per event_type.
    """
    event_id: UUID = Field(default_factory=uuid4, description="Unique event identifier")
    type: EventType = Field(..., description="Event type from reserved enum")
    ts: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    workflow_id: Optional[UUID] = Field(None, description="Associated workflow ID if applicable")
    sequence: int = Field(0, description="Monotonic sequence number per workflow")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }


# ============================================================================
# Typed Payloads for specific events
# ============================================================================

class UIScreenPayload(BaseModel):
    """Payload for ui.screen events."""
    screen: ScreenType
    data: Optional[dict[str, Any]] = None


class AgentStatusPayload(BaseModel):
    """Payload for agent.status events."""
    agent: AgentType
    status: AgentStatus
    message: Optional[str] = None


class WorkflowStepPayload(BaseModel):
    """Payload for workflow.step events."""
    step_name: str
    step_index: int
    total_steps: int
    state: WorkflowState
    message: Optional[str] = None


class ApprovalRequestPayload(BaseModel):
    """Payload for approval.request events."""
    approval_id: UUID = Field(default_factory=uuid4)
    action_type: str  # e.g., "order_instacart", "add_to_cart"
    description: str
    items: Optional[list[dict[str, Any]]] = None
    estimated_total: Optional[float] = None
    expires_at: Optional[datetime] = None


class ApprovalResultPayload(BaseModel):
    """Payload for approval.result events."""
    approval_id: UUID
    approved: bool
    user_message: Optional[str] = None


class ChatMessagePayload(BaseModel):
    """Payload for chat messages."""
    message_id: UUID = Field(default_factory=uuid4)
    content: str
    sender: str  # "user" or "domus"
    metadata: Optional[dict[str, Any]] = None


class NotificationPayload(BaseModel):
    """Payload for notification.sent events."""
    notification_id: UUID = Field(default_factory=uuid4)
    title: str
    body: str
    action_url: Optional[str] = None
    has_actions: bool = False


class ErrorPayload(BaseModel):
    """Payload for error events."""
    code: str
    message: str
    recoverable: bool = True
    retry_after: Optional[int] = None


class CapabilitiesPayload(BaseModel):
    """Payload for capabilities.updated events."""
    gmail_connected: bool = False
    blink_connected: bool = False
    fridge_sense_available: bool = False
    calendar_connected: bool = False
    instacart_connected: bool = False


# ============================================================================
# Event Factory Functions
# ============================================================================

def create_ui_screen_event(
    screen: ScreenType,
    workflow_id: Optional[UUID] = None,
    data: Optional[dict] = None
) -> DomusEvent:
    """Create a UI screen navigation event."""
    return DomusEvent(
        type=EventType.UI_SCREEN,
        workflow_id=workflow_id,
        payload=UIScreenPayload(screen=screen, data=data).model_dump()
    )


def create_agent_status_event(
    agent: AgentType,
    status: AgentStatus,
    workflow_id: Optional[UUID] = None,
    message: Optional[str] = None
) -> DomusEvent:
    """Create an agent status event."""
    return DomusEvent(
        type=EventType.AGENT_STATUS,
        workflow_id=workflow_id,
        payload=AgentStatusPayload(
            agent=agent,
            status=status,
            message=message
        ).model_dump()
    )


def create_chat_message_event(
    content: str,
    sender: str,
    workflow_id: Optional[UUID] = None,
    metadata: Optional[dict] = None
) -> DomusEvent:
    """Create a chat message event."""
    event_type = (
        EventType.CHAT_USER_MESSAGE if sender == "user"
        else EventType.CHAT_ASSISTANT_MESSAGE
    )
    return DomusEvent(
        type=event_type,
        workflow_id=workflow_id,
        payload=ChatMessagePayload(
            content=content,
            sender=sender,
            metadata=metadata
        ).model_dump()
    )


def create_error_event(
    code: str,
    message: str,
    recoverable: bool = True,
    workflow_id: Optional[UUID] = None
) -> DomusEvent:
    """Create an error event."""
    return DomusEvent(
        type=EventType.ERROR,
        workflow_id=workflow_id,
        payload=ErrorPayload(
            code=code,
            message=message,
            recoverable=recoverable
        ).model_dump()
    )


def create_heartbeat_event() -> DomusEvent:
    """Create a heartbeat event."""
    return DomusEvent(
        type=EventType.HEARTBEAT,
        payload={"status": "alive"}
    )
