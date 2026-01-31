/**
 * Domus Event Protocol - TypeScript Types
 *
 * These types MUST stay in sync with shared/schemas/events.py
 */

// ============================================================================
// Enums
// ============================================================================

export enum EventType {
  // UI Navigation
  UI_SCREEN = "ui.screen",

  // Agent lifecycle
  AGENT_STATUS = "agent.status",

  // Workflow
  WORKFLOW_STEP = "workflow.step",
  WORKFLOW_STARTED = "workflow.started",
  WORKFLOW_COMPLETED = "workflow.completed",
  WORKFLOW_FAILED = "workflow.failed",

  // Approval
  APPROVAL_REQUEST = "approval.request",
  APPROVAL_RESULT = "approval.result",

  // Notifications
  NOTIFICATION_SENT = "notification.sent",

  // Chat
  CHAT_USER_MESSAGE = "chat.user_message",
  CHAT_ASSISTANT_MESSAGE = "chat.assistant_message",

  // System
  HEARTBEAT = "system.heartbeat",
  ERROR = "error",

  // Capabilities
  CAPABILITIES_UPDATED = "capabilities.updated",
}

export enum AgentStatus {
  ACTIVATING = "activating",
  ACTIVATED = "activated",
  DEACTIVATED = "deactivated",
  ERROR = "error",
}

export enum AgentType {
  FRIDGE = "fridge",
  CALENDAR = "calendar",
  SERVICES = "services",
  IDENTITY = "identity",
  NOTIFICATION = "notification",
}

export enum ScreenType {
  SPLASH = "splash",
  LANDING = "landing",
  LOGIN = "login",
  CHAT = "chat",
  CONNECT_FRIDGE_SENSE = "connect_fridge_sense",
  BLINK_2FA = "blink_2fa",
  FRIDGE_SENSE_SUCCESS = "fridge_sense_success",
  ACTIVITY_CENTER = "activity_center",
  MENU = "menu",
}

export enum BlinkConnectionState {
  NOT_STARTED = "not_started",
  CONNECT_STARTED = "blink_connect_started",
  OAUTH_RETURNED = "oauth_returned",
  AWAITING_2FA = "awaiting_2fa",
  VERIFIED = "verified",
  CONNECTED = "connected",
  FAILED = "failed",
}

export enum WorkflowState {
  ACTIVE = "active",
  ACTION_REQUIRED = "action_required",
  COMPLETED = "completed",
  PROCESSING = "processing",
  PROACTIVE = "proactive",
  INTERRUPTED = "interrupted",
}

// ============================================================================
// Event Envelope
// ============================================================================

export interface DomusEvent {
  event_id: string;
  type: EventType;
  ts: string; // ISO datetime
  workflow_id?: string;
  sequence: number;
  payload: Record<string, unknown>;
}

// ============================================================================
// Typed Payloads
// ============================================================================

export interface UIScreenPayload {
  screen: ScreenType;
  data?: Record<string, unknown>;
}

export interface AgentStatusPayload {
  agent: AgentType;
  status: AgentStatus;
  message?: string;
}

export interface WorkflowStepPayload {
  step_name: string;
  step_index: number;
  total_steps: number;
  state: WorkflowState;
  message?: string;
}

export interface ApprovalRequestPayload {
  approval_id: string;
  action_type: string;
  description: string;
  items?: Array<Record<string, unknown>>;
  estimated_total?: number;
  expires_at?: string;
}

export interface ApprovalResultPayload {
  approval_id: string;
  approved: boolean;
  user_message?: string;
}

export interface ChatMessagePayload {
  message_id: string;
  content: string;
  sender: "user" | "domus";
  metadata?: Record<string, unknown>;
}

export interface NotificationPayload {
  notification_id: string;
  title: string;
  body: string;
  action_url?: string;
  has_actions: boolean;
}

export interface ErrorPayload {
  code: string;
  message: string;
  recoverable: boolean;
  retry_after?: number;
}

export interface CapabilitiesPayload {
  gmail_connected: boolean;
  blink_connected: boolean;
  fridge_sense_available: boolean;
  calendar_connected: boolean;
  instacart_connected: boolean;
}

// ============================================================================
// Type Guards
// ============================================================================

export function isUIScreenEvent(event: DomusEvent): event is DomusEvent & { payload: UIScreenPayload } {
  return event.type === EventType.UI_SCREEN;
}

export function isAgentStatusEvent(event: DomusEvent): event is DomusEvent & { payload: AgentStatusPayload } {
  return event.type === EventType.AGENT_STATUS;
}

export function isChatMessageEvent(event: DomusEvent): event is DomusEvent & { payload: ChatMessagePayload } {
  return event.type === EventType.CHAT_USER_MESSAGE || event.type === EventType.CHAT_ASSISTANT_MESSAGE;
}

export function isApprovalRequestEvent(event: DomusEvent): event is DomusEvent & { payload: ApprovalRequestPayload } {
  return event.type === EventType.APPROVAL_REQUEST;
}

export function isErrorEvent(event: DomusEvent): event is DomusEvent & { payload: ErrorPayload } {
  return event.type === EventType.ERROR;
}
