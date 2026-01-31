"""
Domus State Model

Core state structures for the Domus system.
Designed with repository pattern for future storage backend swap (Redis → Postgres).
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from .events import (
    BlinkConnectionState,
    WorkflowState,
    CapabilitiesPayload,
)


# ============================================================================
# User & Session
# ============================================================================

class UserSession(BaseModel):
    """User session state."""
    session_id: UUID = Field(default_factory=uuid4)
    user_id: str
    user_name: str
    user_email: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    capabilities: CapabilitiesPayload = Field(default_factory=CapabilitiesPayload)


class UserProfile(BaseModel):
    """User profile (longer-lived than session)."""
    user_id: str
    email: str
    name: str
    picture_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None


# ============================================================================
# Workflow State
# ============================================================================

class WorkflowCheckpoint(BaseModel):
    """LangGraph-compatible workflow checkpoint."""
    workflow_id: UUID = Field(default_factory=uuid4)
    workflow_type: str  # e.g., "fridge_query", "order_flow", "blink_connect"
    user_id: str
    state: dict[str, Any] = Field(default_factory=dict)
    current_step: str
    step_sequence: int = 0
    status: WorkflowState = WorkflowState.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def advance(self, step_name: str, new_state: dict[str, Any]) -> "WorkflowCheckpoint":
        """Create a new checkpoint with advanced state."""
        return WorkflowCheckpoint(
            workflow_id=self.workflow_id,
            workflow_type=self.workflow_type,
            user_id=self.user_id,
            state={**self.state, **new_state},
            current_step=step_name,
            step_sequence=self.step_sequence + 1,
            status=self.status,
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )


# ============================================================================
# Blink Connection State (Resumable Workflow)
# ============================================================================

class BlinkConnectionWorkflow(BaseModel):
    """
    Blink OAuth + 2FA workflow state.

    Designed to be resumable - popup failures, user closes window, etc.
    """
    workflow_id: UUID = Field(default_factory=uuid4)
    user_id: str
    state: BlinkConnectionState = BlinkConnectionState.NOT_STARTED

    # OAuth state
    oauth_state_param: Optional[str] = None  # CSRF protection
    oauth_code: Optional[str] = None

    # 2FA state
    requires_2fa: bool = False
    verification_attempts: int = 0
    max_verification_attempts: int = 3

    # Connection result
    blink_account_id: Optional[str] = None
    cameras: list[dict[str, Any]] = Field(default_factory=list)

    # Timestamps
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def can_retry(self) -> bool:
        """Check if workflow can be retried."""
        return self.retry_count < self.max_retries

    def can_verify_2fa(self) -> bool:
        """Check if 2FA verification is allowed."""
        return (
            self.state == BlinkConnectionState.AWAITING_2FA
            and self.verification_attempts < self.max_verification_attempts
        )


# ============================================================================
# Inventory State
# ============================================================================

class InventoryItem(BaseModel):
    """Single item in fridge inventory."""
    item_id: UUID = Field(default_factory=uuid4)
    name: str
    category: str
    quantity: int = 1
    unit: Optional[str] = None
    location: Optional[str] = None  # "top shelf", "door", etc.
    confidence: float = 1.0

    # Temporal tracking
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    position_hash: Optional[str] = None  # For "unchanged for N days" detection

    # Expiry
    estimated_expiry: Optional[datetime] = None
    expiry_warning_sent: bool = False


class InventorySnapshot(BaseModel):
    """Complete inventory state at a point in time."""
    snapshot_id: UUID = Field(default_factory=uuid4)
    user_id: str
    items: list[InventoryItem] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    image_hash: Optional[str] = None
    confidence: float = 0.0

    def get_item_names(self) -> list[str]:
        """Get list of item names."""
        return [item.name for item in self.items]


# ============================================================================
# Activity / Audit Log
# ============================================================================

class ActivityEntry(BaseModel):
    """Single entry in activity center."""
    activity_id: UUID = Field(default_factory=uuid4)
    user_id: str
    workflow_id: Optional[UUID] = None

    status: WorkflowState
    title: str
    description: str

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # For action required
    requires_action: bool = False
    action_type: Optional[str] = None
    action_data: Optional[dict[str, Any]] = None


# ============================================================================
# Notification History
# ============================================================================

class NotificationRecord(BaseModel):
    """Record of sent notification."""
    notification_id: UUID = Field(default_factory=uuid4)
    user_id: str

    title: str
    body: str
    has_actions: bool = False
    action_url: Optional[str] = None

    # Delivery tracking
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    delivered: bool = False
    read_at: Optional[datetime] = None
    acted_on: bool = False

    # Idempotency
    idempotency_key: Optional[str] = None  # e.g., "event_123_48h_reminder"


# ============================================================================
# Approval State
# ============================================================================

class ApprovalRecord(BaseModel):
    """Record of approval request and result."""
    approval_id: UUID = Field(default_factory=uuid4)
    user_id: str
    workflow_id: Optional[UUID] = None

    action_type: str  # "order_instacart", "add_to_cart", etc.
    description: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    estimated_total: Optional[float] = None

    # Status
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    approved: Optional[bool] = None
    user_message: Optional[str] = None


# ============================================================================
# Aggregate State (for session/workflow context)
# ============================================================================

class DomusState(BaseModel):
    """
    Aggregate state for a user session.

    This is the main state object passed through LangGraph workflows.
    """
    session: UserSession

    # Current workflow
    active_workflow: Optional[WorkflowCheckpoint] = None

    # Blink connection
    blink_connection: Optional[BlinkConnectionWorkflow] = None

    # Latest inventory
    inventory: Optional[InventorySnapshot] = None

    # Pending approvals
    pending_approvals: list[ApprovalRecord] = Field(default_factory=list)

    # Chat context (last N messages for LLM context)
    chat_history: list[dict[str, Any]] = Field(default_factory=list)
    max_chat_history: int = 10

    def add_chat_message(self, role: str, content: str) -> None:
        """Add message to chat history with automatic truncation."""
        self.chat_history.append({
            "role": role,
            "content": content,
            "ts": datetime.utcnow().isoformat()
        })
        # Keep only last N messages
        if len(self.chat_history) > self.max_chat_history:
            self.chat_history = self.chat_history[-self.max_chat_history:]
