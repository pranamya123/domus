/**
 * Zustand Store - Global Application State
 */

import { create } from 'zustand';
import {
  ScreenType,
  AgentStatus,
  AgentType,
  ChatMessage,
  User,
  CapabilitiesPayload,
  Notification,
} from '../types';

interface AppState {
  // Auth
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;

  // Navigation
  currentScreen: ScreenType;

  // Agent status
  agentStatus: Record<AgentType, AgentStatus>;
  activeAgent: AgentType | null;

  // Chat
  messages: ChatMessage[];

  // Notifications
  notifications: Notification[];
  unreadCount: number;
  notificationPanelOpen: boolean;

  // Capabilities
  capabilities: CapabilitiesPayload;

  // WebSocket
  isConnected: boolean;

  // Loading states
  isLoading: boolean;

  // Actions
  setToken: (token: string | null) => void;
  setUser: (user: User | null) => void;
  setScreen: (screen: ScreenType) => void;
  setAgentStatus: (agent: AgentType, status: AgentStatus) => void;
  setActiveAgent: (agent: AgentType | null) => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  setCapabilities: (capabilities: CapabilitiesPayload) => void;
  setConnected: (connected: boolean) => void;
  setLoading: (loading: boolean) => void;
  logout: () => void;

  // Notification actions
  setNotifications: (notifications: Notification[]) => void;
  addNotification: (notification: Notification) => void;
  setUnreadCount: (count: number) => void;
  markNotificationRead: (notificationId: string) => void;
  setNotificationPanelOpen: (open: boolean) => void;

  // Pending order card from iOS notification tap
  pendingOrderCard: { id: string; items: string[] } | null;
  setPendingOrderCard: (card: { id: string; items: string[] } | null) => void;
}

const initialAgentStatus: Record<AgentType, AgentStatus> = {
  [AgentType.FRIDGE]: AgentStatus.DEACTIVATED,
  [AgentType.CALENDAR]: AgentStatus.DEACTIVATED,
  [AgentType.SERVICES]: AgentStatus.DEACTIVATED,
  [AgentType.IDENTITY]: AgentStatus.DEACTIVATED,
  [AgentType.NOTIFICATION]: AgentStatus.DEACTIVATED,
};

const initialCapabilities: CapabilitiesPayload = {
  gmail_connected: false,
  blink_connected: false,
  fridge_sense_available: false,
  calendar_connected: false,
  instacart_connected: false,
};

export const useStore = create<AppState>((set) => ({
  // Initial state
  token: localStorage.getItem('domus_token'),
  user: null,
  isAuthenticated: !!localStorage.getItem('domus_token'),
  currentScreen: ScreenType.SPLASH,
  agentStatus: initialAgentStatus,
  activeAgent: null,
  messages: [],
  notifications: [],
  unreadCount: 0,
  notificationPanelOpen: false,
  pendingOrderCard: null,
  capabilities: initialCapabilities,
  isConnected: false,
  isLoading: false,

  // Actions
  setToken: (token) => {
    if (token) {
      localStorage.setItem('domus_token', token);
    } else {
      localStorage.removeItem('domus_token');
    }
    set({ token, isAuthenticated: !!token });
  },

  setUser: (user) => set({ user }),

  setScreen: (screen) => set({ currentScreen: screen }),

  setAgentStatus: (agent, status) =>
    set((state) => ({
      agentStatus: { ...state.agentStatus, [agent]: status },
    })),

  setActiveAgent: (agent) => set({ activeAgent: agent }),

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  updateMessage: (id, updates) =>
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    })),

  setCapabilities: (capabilities) => set({ capabilities }),

  setConnected: (connected) => set({ isConnected: connected }),

  setLoading: (loading) => set({ isLoading: loading }),

  logout: () => {
    localStorage.removeItem('domus_token');
    set({
      token: null,
      user: null,
      isAuthenticated: false,
      currentScreen: ScreenType.LANDING,
      agentStatus: initialAgentStatus,
      activeAgent: null,
      messages: [],
      notifications: [],
      unreadCount: 0,
      notificationPanelOpen: false,
      capabilities: initialCapabilities,
      isConnected: false,
    });
  },

  // Notification actions
  setNotifications: (notifications) => {
    const unreadCount = notifications.filter((n) => n.read_at === null).length;
    set({ notifications, unreadCount });
  },

  addNotification: (notification) =>
    set((state) => {
      const exists = state.notifications.some(
        (n) => n.notification_id === notification.notification_id
      );
      if (exists) return state;
      return {
        notifications: [notification, ...state.notifications],
        unreadCount: notification.read_at === null ? state.unreadCount + 1 : state.unreadCount,
      };
    }),

  setUnreadCount: (count) => set({ unreadCount: count }),

  markNotificationRead: (notificationId) =>
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.notification_id === notificationId
          ? { ...n, read_at: new Date().toISOString() }
          : n
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    })),

  setNotificationPanelOpen: (open) => set({ notificationPanelOpen: open }),

  setPendingOrderCard: (card) => set({ pendingOrderCard: card }),
}));
