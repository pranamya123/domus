/**
 * Domus Frontend Types
 *
 * Must stay in sync with shared/types/events.ts
 */

// ============================================================================
// Enums
// ============================================================================

export enum EventType {
  UI_SCREEN = "ui.screen",
  AGENT_STATUS = "agent.status",
  WORKFLOW_STEP = "workflow.step",
  WORKFLOW_STARTED = "workflow.started",
  WORKFLOW_COMPLETED = "workflow.completed",
  WORKFLOW_FAILED = "workflow.failed",
  APPROVAL_REQUEST = "approval.request",
  APPROVAL_RESULT = "approval.result",
  NOTIFICATION_SENT = "notification.sent",
  NOTIFICATION_CREATED = "notification.created",  // New proactive notification
  CHAT_USER_MESSAGE = "chat.user_message",
  CHAT_ASSISTANT_MESSAGE = "chat.assistant_message",
  HEARTBEAT = "system.heartbeat",
  ERROR = "error",
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
// Event Types
// ============================================================================

export interface DomusEvent {
  event_id: string;
  type: EventType;
  ts: string;
  workflow_id?: string;
  sequence: number;
  payload: Record<string, unknown>;
}

export interface UIScreenPayload {
  screen: ScreenType;
  data?: Record<string, unknown>;
}

export interface AgentStatusPayload {
  agent: AgentType;
  status: AgentStatus;
  message?: string;
}

export interface ChatMessagePayload {
  message_id: string;
  content: string;
  sender: "user" | "domus";
  metadata?: Record<string, unknown>;
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
// Auth Types
// ============================================================================

export interface LoginResponse {
  token: string;
  user_id: string;
  user_name: string;
  user_email: string;
  session_id: string;
  expires_at: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  picture?: string;
}

// ============================================================================
// Chat Types
// ============================================================================

export interface ChatMessage {
  id: string;
  content: string;
  sender: "user" | "domus";
  timestamp: string;
  status?: "sending" | "sent" | "error";
  fromNotification?: boolean;  // True if this message originated from a notification
}

// ============================================================================
// Notification Types
// ============================================================================

export interface Notification {
  notification_id: string;
  title: string;
  body: string;
  sent_at: string;
  read_at: string | null;
  notification_type: "chat" | "proactive";
  chat_seed_content: string | null;
  event_id: string | null;
}

export interface NotificationCreatedPayload {
  notification_id: string;
  title: string;
  body: string;
  notification_type: "chat" | "proactive";
  event_id?: string;
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

export function isChatMessageEvent(event: DomusEvent): boolean {
  return event.type === EventType.CHAT_USER_MESSAGE || event.type === EventType.CHAT_ASSISTANT_MESSAGE;
}

export function isErrorEvent(event: DomusEvent): event is DomusEvent & { payload: ErrorPayload } {
  return event.type === EventType.ERROR;
}

export function isCapabilitiesEvent(event: DomusEvent): event is DomusEvent & { payload: CapabilitiesPayload } {
  return event.type === EventType.CAPABILITIES_UPDATED;
}

export function isNotificationCreatedEvent(event: DomusEvent): event is DomusEvent & { payload: NotificationCreatedPayload } {
  return event.type === EventType.NOTIFICATION_CREATED;
}
