/**
 * Type definitions for Domus frontend
 */

// User types
export interface User {
  id: string
  email: string
  name: string
  picture_url?: string
  household_id?: string
  created_at: string
}

export interface AuthToken {
  access_token: string
  token_type: string
  expires_in: number
}

// Application state machine (per spec)
export type AppState =
  | 'DISCONNECTED'
  | 'CONNECTED_IDLE'
  | 'CONNECTED_SCANNING'
  | 'PROCESSING'
  | 'ERROR'

// Valid state transitions for FSM validation
export const ValidStateTransitions: Record<AppState, AppState[]> = {
  'DISCONNECTED': ['CONNECTED_IDLE', 'ERROR'],
  'CONNECTED_IDLE': ['CONNECTED_SCANNING', 'PROCESSING', 'DISCONNECTED', 'ERROR'],
  'CONNECTED_SCANNING': ['PROCESSING', 'CONNECTED_IDLE', 'ERROR'],
  'PROCESSING': ['CONNECTED_IDLE', 'ERROR'],
  'ERROR': ['CONNECTED_IDLE', 'DISCONNECTED'],
}

// Hardware overlay state for UI rendering
export interface OverlayState {
  hardwareLinked: boolean
  hardwareStatus: 'online' | 'offline' | 'unknown'
  lastHardwareSeen?: string
  cameraArmed?: boolean
}

// Chat types
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export interface ChatResponse {
  response: string
  status: string
  inventory_count?: number
  debug_state?: {  // TODO: Remove - debugging only
    status: string
    inventory: Array<{
      name: string
      category: string
      quantity: number
    }>
    item_count: number
    last_updated?: string
    latest_image_url?: string  // TODO: Remove - debugging only
  }
}

// Inventory types
export interface InventoryItem {
  id: string
  name: string
  category: string
  quantity: number
  unit?: string
  expiration_date?: string
  freshness_status: 'fresh' | 'expiring_soon' | 'expired' | 'unknown'
  confidence: number
  location_in_fridge?: string
  first_detected_at: string
  last_seen_at: string
}

export interface Inventory {
  items: InventoryItem[]
  total_count: number
  last_updated?: string
  confidence: number
}

// Notification types
export interface Notification {
  id: string
  notification_type: string
  severity: 'low' | 'medium' | 'high' | 'urgent'
  title: string
  message: string
  is_read: boolean
  created_at: string
  read_at?: string
}

// Device types
export interface Device {
  device_id: string
  device_type: string
  status: 'online' | 'offline' | 'unknown'
  last_seen?: string
  is_simulated: boolean
}

// Upload types
export interface UploadResponse {
  status: string
  message: string
  image_id?: string
  inventory_count?: number
  items_detected?: string[]
  validation_passed: boolean
}

// API Error
export interface ApiError {
  detail: string
  status_code?: number
}
