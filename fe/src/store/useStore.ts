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
      capabilities: initialCapabilities,
      isConnected: false,
    });
  },
}));
