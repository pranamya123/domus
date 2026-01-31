"""
In-Memory Storage Implementation

Simple in-memory storage for Phase 1 testing without Redis.
"""

import asyncio
from datetime import datetime, timedelta
from typing import AsyncIterator, Optional
from uuid import UUID

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


class MemoryStateStore(StateStore):
    """In-memory implementation of StateStore."""

    def __init__(self):
        self._sessions: dict[str, UserSession] = {}
        self._users: dict[str, UserProfile] = {}
        self._users_by_email: dict[str, str] = {}
        self._workflows: dict[str, WorkflowCheckpoint] = {}
        self._user_workflows: dict[str, set] = {}
        self._blink_workflows: dict[str, BlinkConnectionWorkflow] = {}
        self._inventory: dict[str, InventorySnapshot] = {}
        self._inventory_history: dict[str, list] = {}
        self._activities: dict[str, ActivityEntry] = {}
        self._user_activities: dict[str, list] = {}
        self._notifications: dict[str, NotificationRecord] = {}
        self._user_notifications: dict[str, list] = {}
        self._idempotency: dict[str, datetime] = {}
        self._approvals: dict[str, ApprovalRecord] = {}
        self._user_approvals: dict[str, set] = {}
        self._domus_state: dict[str, DomusState] = {}

    async def create_session(self, session: UserSession) -> None:
        self._sessions[str(session.session_id)] = session

    async def get_session(self, session_id: UUID) -> Optional[UserSession]:
        return self._sessions.get(str(session_id))

    async def get_session_by_token(self, token: str) -> Optional[UserSession]:
        # In memory store, we don't track by token separately
        return None

    async def delete_session(self, session_id: UUID) -> None:
        self._sessions.pop(str(session_id), None)

    async def extend_session(self, session_id: UUID, duration: timedelta) -> None:
        session = self._sessions.get(str(session_id))
        if session:
            session.expires_at = datetime.utcnow() + duration

    async def upsert_user(self, user: UserProfile) -> None:
        self._users[user.user_id] = user
        self._users_by_email[user.email] = user.user_id

    async def get_user(self, user_id: str) -> Optional[UserProfile]:
        return self._users.get(user_id)

    async def get_user_by_email(self, email: str) -> Optional[UserProfile]:
        user_id = self._users_by_email.get(email)
        return self._users.get(user_id) if user_id else None

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        self._workflows[str(checkpoint.workflow_id)] = checkpoint
        if checkpoint.user_id not in self._user_workflows:
            self._user_workflows[checkpoint.user_id] = set()
        self._user_workflows[checkpoint.user_id].add(str(checkpoint.workflow_id))

    async def get_checkpoint(self, workflow_id: UUID) -> Optional[WorkflowCheckpoint]:
        return self._workflows.get(str(workflow_id))

    async def get_active_workflows(self, user_id: str) -> list[WorkflowCheckpoint]:
        wf_ids = self._user_workflows.get(user_id, set())
        workflows = []
        for wf_id in wf_ids:
            wf = self._workflows.get(wf_id)
            if wf and wf.status.value in ["active", "action_required"]:
                workflows.append(wf)
        return workflows

    async def save_blink_workflow(self, workflow: BlinkConnectionWorkflow) -> None:
        self._blink_workflows[workflow.user_id] = workflow

    async def get_blink_workflow(self, user_id: str) -> Optional[BlinkConnectionWorkflow]:
        return self._blink_workflows.get(user_id)

    async def save_inventory(self, inventory: InventorySnapshot) -> None:
        self._inventory[inventory.user_id] = inventory
        if inventory.user_id not in self._inventory_history:
            self._inventory_history[inventory.user_id] = []
        self._inventory_history[inventory.user_id].insert(0, inventory)
        self._inventory_history[inventory.user_id] = self._inventory_history[inventory.user_id][:100]

    async def get_latest_inventory(self, user_id: str) -> Optional[InventorySnapshot]:
        return self._inventory.get(user_id)

    async def get_inventory_history(self, user_id: str, limit: int = 10) -> list[InventorySnapshot]:
        return self._inventory_history.get(user_id, [])[:limit]

    async def add_activity(self, activity: ActivityEntry) -> None:
        self._activities[str(activity.activity_id)] = activity
        if activity.user_id not in self._user_activities:
            self._user_activities[activity.user_id] = []
        self._user_activities[activity.user_id].insert(0, str(activity.activity_id))

    async def get_activities(self, user_id: str, limit: int = 50) -> list[ActivityEntry]:
        activity_ids = self._user_activities.get(user_id, [])[:limit]
        return [self._activities[aid] for aid in activity_ids if aid in self._activities]

    async def update_activity(self, activity_id: UUID, updates: dict) -> Optional[ActivityEntry]:
        activity = self._activities.get(str(activity_id))
        if activity:
            for k, v in updates.items():
                if hasattr(activity, k):
                    setattr(activity, k, v)
            activity.updated_at = datetime.utcnow()
        return activity

    async def save_notification(self, notification: NotificationRecord) -> None:
        self._notifications[str(notification.notification_id)] = notification
        if notification.user_id not in self._user_notifications:
            self._user_notifications[notification.user_id] = []
        self._user_notifications[notification.user_id].insert(0, str(notification.notification_id))

    async def get_notifications(self, user_id: str, limit: int = 50) -> list[NotificationRecord]:
        nids = self._user_notifications.get(user_id, [])[:limit]
        return [self._notifications[nid] for nid in nids if nid in self._notifications]

    async def check_idempotency(self, key: str) -> bool:
        exp = self._idempotency.get(key)
        if exp and exp > datetime.utcnow():
            return True
        return False

    async def set_idempotency(self, key: str, ttl_seconds: int) -> None:
        self._idempotency[key] = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    async def save_approval(self, approval: ApprovalRecord) -> None:
        self._approvals[str(approval.approval_id)] = approval
        if approval.user_id not in self._user_approvals:
            self._user_approvals[approval.user_id] = set()
        self._user_approvals[approval.user_id].add(str(approval.approval_id))

    async def get_pending_approvals(self, user_id: str) -> list[ApprovalRecord]:
        aids = self._user_approvals.get(user_id, set())
        approvals = []
        for aid in aids:
            a = self._approvals.get(aid)
            if a and a.approved is None:
                approvals.append(a)
        return approvals

    async def update_approval(self, approval_id: UUID, approved: bool, user_message: Optional[str] = None) -> Optional[ApprovalRecord]:
        approval = self._approvals.get(str(approval_id))
        if approval:
            approval.approved = approved
            approval.user_message = user_message
            approval.responded_at = datetime.utcnow()
        return approval

    async def get_domus_state(self, session_id: UUID) -> Optional[DomusState]:
        return self._domus_state.get(str(session_id))

    async def save_domus_state(self, state: DomusState) -> None:
        self._domus_state[str(state.session.session_id)] = state


class MemoryEventStore(EventStore):
    """In-memory implementation of EventStore."""

    def __init__(self):
        self._events: dict[str, list] = {}  # user_id -> events
        self._workflow_events: dict[str, list] = {}
        self._sequences: dict[str, int] = {}
        self._subscribers: dict[str, list] = {}  # user_id -> queues

    async def publish(self, event: DomusEvent, user_id: str) -> None:
        if user_id not in self._events:
            self._events[user_id] = []
        self._events[user_id].append(event)

        # Notify subscribers
        for queue in self._subscribers.get(user_id, []):
            await queue.put(event)

    async def publish_to_workflow(self, event: DomusEvent, workflow_id: UUID) -> None:
        key = str(workflow_id)
        if key not in self._workflow_events:
            self._workflow_events[key] = []
        self._sequences[key] = self._sequences.get(key, 0) + 1
        event.sequence = self._sequences[key]
        self._workflow_events[key].append(event)

    async def get_events(self, user_id: str, since: Optional[datetime] = None, limit: int = 100) -> list[DomusEvent]:
        events = self._events.get(user_id, [])
        if since:
            events = [e for e in events if e.ts > since]
        return events[-limit:]

    async def get_workflow_events(self, workflow_id: UUID, limit: int = 100) -> list[DomusEvent]:
        return self._workflow_events.get(str(workflow_id), [])[-limit:]

    async def subscribe(self, user_id: str, last_event_id: Optional[str] = None) -> AsyncIterator[DomusEvent]:
        queue: asyncio.Queue = asyncio.Queue()
        if user_id not in self._subscribers:
            self._subscribers[user_id] = []
        self._subscribers[user_id].append(queue)

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers[user_id].remove(queue)

    async def get_last_sequence(self, workflow_id: UUID) -> int:
        return self._sequences.get(str(workflow_id), 0)


class MemoryDomusStorage(DomusStorage):
    """In-memory storage implementation."""

    def __init__(self):
        self._state_store = MemoryStateStore()
        self._event_store = MemoryEventStore()

    async def connect(self) -> None:
        """No connection needed for memory storage."""
        pass

    @property
    def state(self) -> StateStore:
        return self._state_store

    @property
    def events(self) -> EventStore:
        return self._event_store

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass
