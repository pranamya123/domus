"""
Redis Storage Implementation

Implements StateStore and EventStore interfaces using Redis.
Designed for swap to Postgres later via repository pattern.
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import AsyncIterator, Optional
from uuid import UUID

import redis.asyncio as redis
from redis.asyncio.client import PubSub

from shared.schemas.state import (
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
from shared.schemas.events import DomusEvent
from shared.schemas.storage import StateStore, EventStore, DomusStorage

from ..core.config import settings


# ============================================================================
# Redis Key Prefixes (namespacing)
# ============================================================================

class RedisKeys:
    """Redis key patterns for different data types."""

    # Sessions
    SESSION = "session:{session_id}"
    SESSION_BY_TOKEN = "session:token:{token}"

    # Users
    USER = "user:{user_id}"
    USER_BY_EMAIL = "user:email:{email}"

    # Workflows
    WORKFLOW = "workflow:{workflow_id}"
    USER_WORKFLOWS = "user:{user_id}:workflows"
    BLINK_WORKFLOW = "user:{user_id}:blink"

    # Inventory
    INVENTORY = "inventory:{user_id}:latest"
    INVENTORY_HISTORY = "inventory:{user_id}:history"

    # Activity
    ACTIVITY = "activity:{activity_id}"
    USER_ACTIVITIES = "user:{user_id}:activities"

    # Notifications
    NOTIFICATION = "notification:{notification_id}"
    USER_NOTIFICATIONS = "user:{user_id}:notifications"
    IDEMPOTENCY = "idempotency:{key}"

    # Approvals
    APPROVAL = "approval:{approval_id}"
    USER_APPROVALS = "user:{user_id}:approvals"

    # State aggregate
    DOMUS_STATE = "state:{session_id}"

    # Events
    EVENT_STREAM = "events:user:{user_id}"
    WORKFLOW_STREAM = "events:workflow:{workflow_id}"
    WORKFLOW_SEQUENCE = "sequence:workflow:{workflow_id}"

    # Pub/Sub
    USER_CHANNEL = "channel:user:{user_id}"


def _serialize(obj) -> str:
    """Serialize Pydantic model to JSON string."""
    if hasattr(obj, 'model_dump_json'):
        return obj.model_dump_json()
    return json.dumps(obj, default=str)


def _deserialize(data: str, model_class):
    """Deserialize JSON string to Pydantic model."""
    if data is None:
        return None
    return model_class.model_validate_json(data)


# ============================================================================
# Redis State Store Implementation
# ============================================================================

class RedisStateStore(StateStore):
    """Redis implementation of StateStore interface."""

    def __init__(self, client: redis.Redis):
        self._client = client

    # ---- Session Management ----

    async def create_session(self, session: UserSession) -> None:
        """Store a new session."""
        key = RedisKeys.SESSION.format(session_id=session.session_id)
        ttl = int((session.expires_at - datetime.utcnow()).total_seconds())

        pipe = self._client.pipeline()
        pipe.setex(key, ttl, _serialize(session))
        await pipe.execute()

    async def get_session(self, session_id: UUID) -> Optional[UserSession]:
        """Retrieve session by ID."""
        key = RedisKeys.SESSION.format(session_id=session_id)
        data = await self._client.get(key)
        return _deserialize(data, UserSession) if data else None

    async def get_session_by_token(self, token: str) -> Optional[UserSession]:
        """Retrieve session by auth token."""
        # Token lookup key stores session_id
        token_key = RedisKeys.SESSION_BY_TOKEN.format(token=token)
        session_id = await self._client.get(token_key)
        if not session_id:
            return None
        return await self.get_session(UUID(session_id.decode()))

    async def delete_session(self, session_id: UUID) -> None:
        """Delete/invalidate a session."""
        key = RedisKeys.SESSION.format(session_id=session_id)
        await self._client.delete(key)

    async def extend_session(self, session_id: UUID, duration: timedelta) -> None:
        """Extend session expiry."""
        key = RedisKeys.SESSION.format(session_id=session_id)
        session = await self.get_session(session_id)
        if session:
            session.expires_at = datetime.utcnow() + duration
            ttl = int(duration.total_seconds())
            await self._client.setex(key, ttl, _serialize(session))

    # ---- User Profile ----

    async def upsert_user(self, user: UserProfile) -> None:
        """Create or update user profile."""
        key = RedisKeys.USER.format(user_id=user.user_id)
        email_key = RedisKeys.USER_BY_EMAIL.format(email=user.email)

        pipe = self._client.pipeline()
        pipe.set(key, _serialize(user))
        pipe.set(email_key, user.user_id)
        await pipe.execute()

    async def get_user(self, user_id: str) -> Optional[UserProfile]:
        """Get user by ID."""
        key = RedisKeys.USER.format(user_id=user_id)
        data = await self._client.get(key)
        return _deserialize(data, UserProfile) if data else None

    async def get_user_by_email(self, email: str) -> Optional[UserProfile]:
        """Get user by email."""
        email_key = RedisKeys.USER_BY_EMAIL.format(email=email)
        user_id = await self._client.get(email_key)
        if not user_id:
            return None
        return await self.get_user(user_id.decode())

    # ---- Workflow Checkpoints ----

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Save workflow checkpoint (for LangGraph durability)."""
        key = RedisKeys.WORKFLOW.format(workflow_id=checkpoint.workflow_id)
        user_key = RedisKeys.USER_WORKFLOWS.format(user_id=checkpoint.user_id)

        pipe = self._client.pipeline()
        pipe.set(key, _serialize(checkpoint))
        pipe.sadd(user_key, str(checkpoint.workflow_id))
        await pipe.execute()

    async def get_checkpoint(self, workflow_id: UUID) -> Optional[WorkflowCheckpoint]:
        """Get latest checkpoint for workflow."""
        key = RedisKeys.WORKFLOW.format(workflow_id=workflow_id)
        data = await self._client.get(key)
        return _deserialize(data, WorkflowCheckpoint) if data else None

    async def get_active_workflows(self, user_id: str) -> list[WorkflowCheckpoint]:
        """Get all active workflows for user."""
        user_key = RedisKeys.USER_WORKFLOWS.format(user_id=user_id)
        workflow_ids = await self._client.smembers(user_key)

        workflows = []
        for wf_id in workflow_ids:
            checkpoint = await self.get_checkpoint(UUID(wf_id.decode()))
            if checkpoint and checkpoint.status.value in ["active", "action_required"]:
                workflows.append(checkpoint)
        return workflows

    # ---- Blink Connection ----

    async def save_blink_workflow(self, workflow: BlinkConnectionWorkflow) -> None:
        """Save Blink connection workflow state."""
        key = RedisKeys.BLINK_WORKFLOW.format(user_id=workflow.user_id)
        await self._client.set(key, _serialize(workflow))

    async def get_blink_workflow(
        self, user_id: str
    ) -> Optional[BlinkConnectionWorkflow]:
        """Get current Blink workflow for user."""
        key = RedisKeys.BLINK_WORKFLOW.format(user_id=user_id)
        data = await self._client.get(key)
        return _deserialize(data, BlinkConnectionWorkflow) if data else None

    # ---- Inventory ----

    async def save_inventory(self, inventory: InventorySnapshot) -> None:
        """Save inventory snapshot."""
        latest_key = RedisKeys.INVENTORY.format(user_id=inventory.user_id)
        history_key = RedisKeys.INVENTORY_HISTORY.format(user_id=inventory.user_id)

        pipe = self._client.pipeline()
        pipe.set(latest_key, _serialize(inventory))
        pipe.lpush(history_key, _serialize(inventory))
        pipe.ltrim(history_key, 0, 99)  # Keep last 100 snapshots
        await pipe.execute()

    async def get_latest_inventory(self, user_id: str) -> Optional[InventorySnapshot]:
        """Get most recent inventory for user."""
        key = RedisKeys.INVENTORY.format(user_id=user_id)
        data = await self._client.get(key)
        return _deserialize(data, InventorySnapshot) if data else None

    async def get_inventory_history(
        self, user_id: str, limit: int = 10
    ) -> list[InventorySnapshot]:
        """Get inventory history for temporal analysis."""
        key = RedisKeys.INVENTORY_HISTORY.format(user_id=user_id)
        items = await self._client.lrange(key, 0, limit - 1)
        return [_deserialize(item, InventorySnapshot) for item in items]

    # ---- Activity Log ----

    async def add_activity(self, activity: ActivityEntry) -> None:
        """Add activity entry."""
        key = RedisKeys.ACTIVITY.format(activity_id=activity.activity_id)
        user_key = RedisKeys.USER_ACTIVITIES.format(user_id=activity.user_id)

        pipe = self._client.pipeline()
        pipe.set(key, _serialize(activity))
        pipe.lpush(user_key, str(activity.activity_id))
        pipe.ltrim(user_key, 0, 199)  # Keep last 200 activities
        await pipe.execute()

    async def get_activities(
        self, user_id: str, limit: int = 50
    ) -> list[ActivityEntry]:
        """Get recent activities for user."""
        user_key = RedisKeys.USER_ACTIVITIES.format(user_id=user_id)
        activity_ids = await self._client.lrange(user_key, 0, limit - 1)

        activities = []
        for aid in activity_ids:
            key = RedisKeys.ACTIVITY.format(activity_id=aid.decode())
            data = await self._client.get(key)
            if data:
                activities.append(_deserialize(data, ActivityEntry))
        return activities

    async def update_activity(
        self, activity_id: UUID, updates: dict
    ) -> Optional[ActivityEntry]:
        """Update activity entry."""
        key = RedisKeys.ACTIVITY.format(activity_id=activity_id)
        data = await self._client.get(key)
        if not data:
            return None

        activity = _deserialize(data, ActivityEntry)
        for k, v in updates.items():
            if hasattr(activity, k):
                setattr(activity, k, v)
        activity.updated_at = datetime.utcnow()

        await self._client.set(key, _serialize(activity))
        return activity

    # ---- Notifications ----

    async def save_notification(self, notification: NotificationRecord) -> None:
        """Save notification record."""
        key = RedisKeys.NOTIFICATION.format(notification_id=notification.notification_id)
        user_key = RedisKeys.USER_NOTIFICATIONS.format(user_id=notification.user_id)

        pipe = self._client.pipeline()
        pipe.set(key, _serialize(notification))
        pipe.lpush(user_key, str(notification.notification_id))
        pipe.ltrim(user_key, 0, 99)
        await pipe.execute()

    async def get_notifications(
        self, user_id: str, limit: int = 50
    ) -> list[NotificationRecord]:
        """Get notification history."""
        user_key = RedisKeys.USER_NOTIFICATIONS.format(user_id=user_id)
        notification_ids = await self._client.lrange(user_key, 0, limit - 1)

        notifications = []
        for nid in notification_ids:
            key = RedisKeys.NOTIFICATION.format(notification_id=nid.decode())
            data = await self._client.get(key)
            if data:
                notifications.append(_deserialize(data, NotificationRecord))
        return notifications

    async def check_idempotency(self, key: str) -> bool:
        """Check if idempotency key exists (for cooldowns)."""
        idem_key = RedisKeys.IDEMPOTENCY.format(key=key)
        return await self._client.exists(idem_key) > 0

    async def set_idempotency(self, key: str, ttl_seconds: int) -> None:
        """Set idempotency key with TTL."""
        idem_key = RedisKeys.IDEMPOTENCY.format(key=key)
        await self._client.setex(idem_key, ttl_seconds, "1")

    # ---- Approvals ----

    async def save_approval(self, approval: ApprovalRecord) -> None:
        """Save approval request."""
        key = RedisKeys.APPROVAL.format(approval_id=approval.approval_id)
        user_key = RedisKeys.USER_APPROVALS.format(user_id=approval.user_id)

        pipe = self._client.pipeline()
        pipe.set(key, _serialize(approval))
        pipe.sadd(user_key, str(approval.approval_id))
        await pipe.execute()

    async def get_pending_approvals(self, user_id: str) -> list[ApprovalRecord]:
        """Get pending approvals for user."""
        user_key = RedisKeys.USER_APPROVALS.format(user_id=user_id)
        approval_ids = await self._client.smembers(user_key)

        approvals = []
        for aid in approval_ids:
            key = RedisKeys.APPROVAL.format(approval_id=aid.decode())
            data = await self._client.get(key)
            if data:
                approval = _deserialize(data, ApprovalRecord)
                if approval.approved is None:  # Still pending
                    approvals.append(approval)
        return approvals

    async def update_approval(
        self, approval_id: UUID, approved: bool, user_message: Optional[str] = None
    ) -> Optional[ApprovalRecord]:
        """Update approval with result."""
        key = RedisKeys.APPROVAL.format(approval_id=approval_id)
        data = await self._client.get(key)
        if not data:
            return None

        approval = _deserialize(data, ApprovalRecord)
        approval.approved = approved
        approval.user_message = user_message
        approval.responded_at = datetime.utcnow()

        await self._client.set(key, _serialize(approval))
        return approval

    # ---- Aggregate State ----

    async def get_domus_state(self, session_id: UUID) -> Optional[DomusState]:
        """Get full aggregate state for session."""
        key = RedisKeys.DOMUS_STATE.format(session_id=session_id)
        data = await self._client.get(key)
        return _deserialize(data, DomusState) if data else None

    async def save_domus_state(self, state: DomusState) -> None:
        """Save aggregate state."""
        key = RedisKeys.DOMUS_STATE.format(session_id=state.session.session_id)
        ttl = int((state.session.expires_at - datetime.utcnow()).total_seconds())
        await self._client.setex(key, max(ttl, 1), _serialize(state))


# ============================================================================
# Redis Event Store Implementation
# ============================================================================

class RedisEventStore(EventStore):
    """Redis implementation of EventStore using Streams and Pub/Sub."""

    def __init__(self, client: redis.Redis):
        self._client = client

    async def publish(self, event: DomusEvent, user_id: str) -> None:
        """Publish event to user's event stream."""
        stream_key = RedisKeys.EVENT_STREAM.format(user_id=user_id)
        channel_key = RedisKeys.USER_CHANNEL.format(user_id=user_id)

        # Add to stream for persistence
        await self._client.xadd(
            stream_key,
            {"event": _serialize(event)},
            maxlen=1000  # Keep last 1000 events
        )

        # Publish to channel for real-time delivery
        await self._client.publish(channel_key, _serialize(event))

    async def publish_to_workflow(
        self, event: DomusEvent, workflow_id: UUID
    ) -> None:
        """Publish event to specific workflow stream."""
        stream_key = RedisKeys.WORKFLOW_STREAM.format(workflow_id=workflow_id)

        # Get and increment sequence
        seq_key = RedisKeys.WORKFLOW_SEQUENCE.format(workflow_id=workflow_id)
        sequence = await self._client.incr(seq_key)
        event.sequence = sequence

        await self._client.xadd(
            stream_key,
            {"event": _serialize(event)},
            maxlen=500
        )

    async def get_events(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> list[DomusEvent]:
        """Get events for user since timestamp."""
        stream_key = RedisKeys.EVENT_STREAM.format(user_id=user_id)

        # Convert datetime to Redis stream ID format
        start = "-" if since is None else str(int(since.timestamp() * 1000))

        messages = await self._client.xrange(stream_key, min=start, count=limit)

        events = []
        for msg_id, fields in messages:
            if b"event" in fields:
                events.append(_deserialize(fields[b"event"], DomusEvent))
        return events

    async def get_workflow_events(
        self, workflow_id: UUID, limit: int = 100
    ) -> list[DomusEvent]:
        """Get events for specific workflow."""
        stream_key = RedisKeys.WORKFLOW_STREAM.format(workflow_id=workflow_id)
        messages = await self._client.xrange(stream_key, count=limit)

        events = []
        for msg_id, fields in messages:
            if b"event" in fields:
                events.append(_deserialize(fields[b"event"], DomusEvent))
        return events

    async def subscribe(
        self, user_id: str, last_event_id: Optional[str] = None
    ) -> AsyncIterator[DomusEvent]:
        """
        Subscribe to user's event stream.

        Yields events as they are published.
        Used for WebSocket/SSE connections.
        """
        channel_key = RedisKeys.USER_CHANNEL.format(user_id=user_id)

        pubsub: PubSub = self._client.pubsub()
        await pubsub.subscribe(channel_key)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    event = _deserialize(message["data"], DomusEvent)
                    yield event
        finally:
            await pubsub.unsubscribe(channel_key)
            await pubsub.close()

    async def get_last_sequence(self, workflow_id: UUID) -> int:
        """Get last sequence number for workflow (for monotonic ordering)."""
        seq_key = RedisKeys.WORKFLOW_SEQUENCE.format(workflow_id=workflow_id)
        seq = await self._client.get(seq_key)
        return int(seq) if seq else 0


# ============================================================================
# Combined Storage Implementation
# ============================================================================

class RedisDomusStorage(DomusStorage):
    """Combined storage interface providing both state and event stores."""

    def __init__(self, redis_url: str = None):
        self._redis_url = redis_url or settings.redis_url
        self._client: Optional[redis.Redis] = None
        self._state_store: Optional[RedisStateStore] = None
        self._event_store: Optional[RedisEventStore] = None

    async def connect(self) -> None:
        """Initialize Redis connection."""
        self._client = redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=False
        )
        self._state_store = RedisStateStore(self._client)
        self._event_store = RedisEventStore(self._client)

    @property
    def state(self) -> StateStore:
        """Get state store instance."""
        if self._state_store is None:
            raise RuntimeError("Storage not connected. Call connect() first.")
        return self._state_store

    @property
    def events(self) -> EventStore:
        """Get event store instance."""
        if self._event_store is None:
            raise RuntimeError("Storage not connected. Call connect() first.")
        return self._event_store

    async def health_check(self) -> bool:
        """Check storage connectivity."""
        try:
            await self._client.ping()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close storage connections."""
        if self._client:
            await self._client.close()
