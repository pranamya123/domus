"""
Domus Shared Schemas

Contract-first types shared between backend, frontend, and MCP servers.
"""

from .events import (
    # Enums
    EventType,
    AgentStatus,
    AgentType,
    ScreenType,
    BlinkConnectionState,
    WorkflowState,
    # Event envelope
    DomusEvent,
    # Typed payloads
    UIScreenPayload,
    AgentStatusPayload,
    WorkflowStepPayload,
    ApprovalRequestPayload,
    ApprovalResultPayload,
    ChatMessagePayload,
    NotificationPayload,
    ErrorPayload,
    CapabilitiesPayload,
    # Factory functions
    create_ui_screen_event,
    create_agent_status_event,
    create_chat_message_event,
    create_error_event,
    create_heartbeat_event,
)

from .state import (
    # User & Session
    UserSession,
    UserProfile,
    # Workflow
    WorkflowCheckpoint,
    BlinkConnectionWorkflow,
    # Inventory
    InventoryItem,
    InventorySnapshot,
    # Activity & Notifications
    ActivityEntry,
    NotificationRecord,
    ApprovalRecord,
    # Aggregate
    DomusState,
)

from .storage import (
    StateStore,
    EventStore,
    DomusStorage,
)

__all__ = [
    # Events
    "EventType",
    "AgentStatus",
    "AgentType",
    "ScreenType",
    "BlinkConnectionState",
    "WorkflowState",
    "DomusEvent",
    "UIScreenPayload",
    "AgentStatusPayload",
    "WorkflowStepPayload",
    "ApprovalRequestPayload",
    "ApprovalResultPayload",
    "ChatMessagePayload",
    "NotificationPayload",
    "ErrorPayload",
    "CapabilitiesPayload",
    "create_ui_screen_event",
    "create_agent_status_event",
    "create_chat_message_event",
    "create_error_event",
    "create_heartbeat_event",
    # State
    "UserSession",
    "UserProfile",
    "WorkflowCheckpoint",
    "BlinkConnectionWorkflow",
    "InventoryItem",
    "InventorySnapshot",
    "ActivityEntry",
    "NotificationRecord",
    "ApprovalRecord",
    "DomusState",
    # Storage
    "StateStore",
    "EventStore",
    "DomusStorage",
]
