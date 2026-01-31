"""
Storage Interfaces (Repository Pattern)

Abstract interfaces for state and event storage.
Implementations can be swapped (Redis → Postgres) without changing business logic.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import AsyncIterator, Optional
from uuid import UUID

from .state import (
    UserSession,
    UserProfile,
    WorkflowCheckpoint,
    BlinkConnectionWorkflow,
    InventorySnapshot,
    ActivityEntry,
    NotificationRecord,
    ApprovalRecord,
    DomusState,
)
from .events import DomusEvent


# ============================================================================
# State Store Interface
# ============================================================================

class StateStore(ABC):
    """
    Abstract interface for state persistence.

    Implementations:
    - RedisStateStore (MVP)
    - PostgresStateStore (future)
    """

    # ---- Session Management ----

    @abstractmethod
    async def create_session(self, session: UserSession) -> None:
        """Store a new session."""
        pass

    @abstractmethod
    async def get_session(self, session_id: UUID) -> Optional[UserSession]:
        """Retrieve session by ID."""
        pass

    @abstractmethod
    async def get_session_by_token(self, token: str) -> Optional[UserSession]:
        """Retrieve session by auth token."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: UUID) -> None:
        """Delete/invalidate a session."""
        pass

    @abstractmethod
    async def extend_session(self, session_id: UUID, duration: timedelta) -> None:
        """Extend session expiry."""
        pass

    # ---- User Profile ----

    @abstractmethod
    async def upsert_user(self, user: UserProfile) -> None:
        """Create or update user profile."""
        pass

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[UserProfile]:
        """Get user by ID."""
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[UserProfile]:
        """Get user by email."""
        pass

    # ---- Workflow Checkpoints ----

    @abstractmethod
    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Save workflow checkpoint (for LangGraph durability)."""
        pass

    @abstractmethod
    async def get_checkpoint(self, workflow_id: UUID) -> Optional[WorkflowCheckpoint]:
        """Get latest checkpoint for workflow."""
        pass

    @abstractmethod
    async def get_active_workflows(self, user_id: str) -> list[WorkflowCheckpoint]:
        """Get all active workflows for user."""
        pass

    # ---- Blink Connection ----

    @abstractmethod
    async def save_blink_workflow(self, workflow: BlinkConnectionWorkflow) -> None:
        """Save Blink connection workflow state."""
        pass

    @abstractmethod
    async def get_blink_workflow(
        self, user_id: str
    ) -> Optional[BlinkConnectionWorkflow]:
        """Get current Blink workflow for user."""
        pass

    # ---- Inventory ----

    @abstractmethod
    async def save_inventory(self, inventory: InventorySnapshot) -> None:
        """Save inventory snapshot."""
        pass

    @abstractmethod
    async def get_latest_inventory(self, user_id: str) -> Optional[InventorySnapshot]:
        """Get most recent inventory for user."""
        pass

    @abstractmethod
    async def get_inventory_history(
        self, user_id: str, limit: int = 10
    ) -> list[InventorySnapshot]:
        """Get inventory history for temporal analysis."""
        pass

    # ---- Activity Log ----

    @abstractmethod
    async def add_activity(self, activity: ActivityEntry) -> None:
        """Add activity entry."""
        pass

    @abstractmethod
    async def get_activities(
        self, user_id: str, limit: int = 50
    ) -> list[ActivityEntry]:
        """Get recent activities for user."""
        pass

    @abstractmethod
    async def update_activity(
        self, activity_id: UUID, updates: dict
    ) -> Optional[ActivityEntry]:
        """Update activity entry."""
        pass

    # ---- Notifications ----

    @abstractmethod
    async def save_notification(self, notification: NotificationRecord) -> None:
        """Save notification record."""
        pass

    @abstractmethod
    async def get_notifications(
        self, user_id: str, limit: int = 50
    ) -> list[NotificationRecord]:
        """Get notification history."""
        pass

    @abstractmethod
    async def check_idempotency(self, key: str) -> bool:
        """Check if idempotency key exists (for cooldowns)."""
        pass

    @abstractmethod
    async def set_idempotency(self, key: str, ttl_seconds: int) -> None:
        """Set idempotency key with TTL."""
        pass

    # ---- Approvals ----

    @abstractmethod
    async def save_approval(self, approval: ApprovalRecord) -> None:
        """Save approval request."""
        pass

    @abstractmethod
    async def get_pending_approvals(self, user_id: str) -> list[ApprovalRecord]:
        """Get pending approvals for user."""
        pass

    @abstractmethod
    async def update_approval(
        self, approval_id: UUID, approved: bool, user_message: Optional[str] = None
    ) -> Optional[ApprovalRecord]:
        """Update approval with result."""
        pass

    # ---- Aggregate State ----

    @abstractmethod
    async def get_domus_state(self, session_id: UUID) -> Optional[DomusState]:
        """Get full aggregate state for session."""
        pass

    @abstractmethod
    async def save_domus_state(self, state: DomusState) -> None:
        """Save aggregate state."""
        pass


# ============================================================================
# Event Store Interface
# ============================================================================

class EventStore(ABC):
    """
    Abstract interface for event persistence and streaming.

    Events are the source of truth for state changes.
    Implementations:
    - RedisEventStore (MVP, using Redis Streams)
    - PostgresEventStore (future)
    """

    @abstractmethod
    async def publish(self, event: DomusEvent, user_id: str) -> None:
        """
        Publish event to user's event stream.

        This is the primary way to send events to the frontend.
        """
        pass

    @abstractmethod
    async def publish_to_workflow(
        self, event: DomusEvent, workflow_id: UUID
    ) -> None:
        """Publish event to specific workflow stream."""
        pass

    @abstractmethod
    async def get_events(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> list[DomusEvent]:
        """Get events for user since timestamp."""
        pass

    @abstractmethod
    async def get_workflow_events(
        self, workflow_id: UUID, limit: int = 100
    ) -> list[DomusEvent]:
        """Get events for specific workflow."""
        pass

    @abstractmethod
    async def subscribe(
        self, user_id: str, last_event_id: Optional[str] = None
    ) -> AsyncIterator[DomusEvent]:
        """
        Subscribe to user's event stream.

        Yields events as they are published.
        Used for WebSocket/SSE connections.
        """
        pass

    @abstractmethod
    async def get_last_sequence(self, workflow_id: UUID) -> int:
        """Get last sequence number for workflow (for monotonic ordering)."""
        pass


# ============================================================================
# Combined Storage Interface
# ============================================================================

class DomusStorage(ABC):
    """Combined storage interface providing both state and event stores."""

    @property
    @abstractmethod
    def state(self) -> StateStore:
        """Get state store instance."""
        pass

    @property
    @abstractmethod
    def events(self) -> EventStore:
        """Get event store instance."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check storage connectivity."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close storage connections."""
        pass
