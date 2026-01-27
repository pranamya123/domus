/**
 * Global state store using Zustand
 * Implements the Frontend State Model per spec
 */

import { create } from 'zustand'
import type { AppState, ChatMessage, Notification, InventoryItem, Device, OverlayState } from '../types'
import { ValidStateTransitions } from '../types'

interface StoreState {
  // Application state machine
  appState: AppState
  setAppState: (state: AppState) => void
  previousAppState: AppState | null

  // Hardware overlay state
  overlayState: OverlayState
  setOverlayState: (overlay: Partial<OverlayState>) => void

  // Hardware linked state (derived overlay)
  isHardwareLinked: boolean
  setHardwareLinked: (linked: boolean) => void

  // Chat state
  chatMessages: ChatMessage[]
  addChatMessage: (message: ChatMessage) => void
  clearChatMessages: () => void

  // Inventory state
  inventory: InventoryItem[]
  setInventory: (items: InventoryItem[]) => void
  lastInventoryUpdate: string | null

  // Notification state
  notifications: Notification[]
  unreadCount: number
  setNotifications: (notifications: Notification[]) => void
  addNotification: (notification: Notification) => void
  markNotificationRead: (id: string) => void
  markAllRead: () => void

  // Device state
  device: Device | null
  setDevice: (device: Device | null) => void

  // Blink camera state
  blinkConnected: boolean
  blinkMonitoring: boolean
  setBlinkStatus: (connected: boolean, monitoring: boolean) => void

  // Error state
  error: string | null
  setError: (error: string | null) => void
  clearError: () => void
}

export const useStore = create<StoreState>((set) => ({
  // Application state - starts disconnected
  appState: 'DISCONNECTED',
  previousAppState: null,
  setAppState: (newState) =>
    set((state) => {
      const validTransitions = ValidStateTransitions[state.appState]
      if (!validTransitions?.includes(newState)) {
        console.warn(
          `Invalid state transition: ${state.appState} -> ${newState}. ` +
          `Valid transitions: ${validTransitions?.join(', ') || 'none'}`
        )
        return state // Reject invalid transition
      }
      return {
        previousAppState: state.appState,
        appState: newState
      }
    }),

  // Hardware overlay state
  overlayState: {
    hardwareLinked: false,
    hardwareStatus: 'unknown',
    lastHardwareSeen: undefined,
    cameraArmed: false,
  },
  setOverlayState: (overlay) =>
    set((state) => ({
      overlayState: { ...state.overlayState, ...overlay },
      isHardwareLinked: overlay.hardwareLinked ?? state.overlayState.hardwareLinked,
    })),

  // Hardware linked (derived from device status)
  isHardwareLinked: false,
  setHardwareLinked: (linked) =>
    set((state) => ({
      isHardwareLinked: linked,
      overlayState: { ...state.overlayState, hardwareLinked: linked },
    })),

  // Chat
  chatMessages: [],
  addChatMessage: (message) =>
    set((state) => ({
      chatMessages: [...state.chatMessages, message],
    })),
  clearChatMessages: () => set({ chatMessages: [] }),

  // Inventory
  inventory: [],
  setInventory: (items) =>
    set({
      inventory: items,
      lastInventoryUpdate: new Date().toISOString(),
    }),
  lastInventoryUpdate: null,

  // Notifications
  notifications: [],
  unreadCount: 0,
  setNotifications: (notifications) =>
    set({
      notifications,
      unreadCount: notifications.filter((n) => !n.is_read).length,
    }),
  addNotification: (notification) =>
    set((state) => ({
      notifications: [notification, ...state.notifications],
      unreadCount: state.unreadCount + 1,
    })),
  markNotificationRead: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, is_read: true } : n
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    })),
  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, is_read: true })),
      unreadCount: 0,
    })),

  // Device
  device: null,
  setDevice: (device) =>
    set((state) => ({
      device,
      isHardwareLinked: device?.status === 'online',
      overlayState: {
        ...state.overlayState,
        hardwareLinked: device?.status === 'online',
        hardwareStatus: device?.status ?? 'unknown',
        lastHardwareSeen: device?.last_seen,
      },
    })),

  // Blink camera state
  blinkConnected: false,
  blinkMonitoring: false,
  setBlinkStatus: (connected, monitoring) =>
    set((state) => ({
      blinkConnected: connected,
      blinkMonitoring: monitoring,
      isHardwareLinked: connected || state.device?.status === 'online',
      overlayState: {
        ...state.overlayState,
        hardwareLinked: connected || state.overlayState.hardwareLinked,
        hardwareStatus: connected ? 'online' : state.overlayState.hardwareStatus,
      },
    })),

  // Error handling
  error: null,
  setError: (error) =>
    set((state) => {
      if (error) {
        // Transition to ERROR state
        const validTransitions = ValidStateTransitions[state.appState]
        if (!validTransitions?.includes('ERROR')) {
          console.warn(`Cannot transition to ERROR from ${state.appState}`)
          return { error }
        }
        return { error, previousAppState: state.appState, appState: 'ERROR' }
      }
      // Clear error - go to CONNECTED_IDLE if valid
      const validTransitions = ValidStateTransitions[state.appState]
      if (validTransitions?.includes('CONNECTED_IDLE')) {
        return { error: null, previousAppState: state.appState, appState: 'CONNECTED_IDLE' }
      }
      return { error: null }
    }),
  clearError: () =>
    set((state) => {
      const validTransitions = ValidStateTransitions[state.appState]
      if (validTransitions?.includes('CONNECTED_IDLE')) {
        return { error: null, previousAppState: state.appState, appState: 'CONNECTED_IDLE' }
      }
      return { error: null }
    }),
}))
