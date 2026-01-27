/**
 * WebSocket Provider
 * Manages WebSocket connections for real-time updates
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  ReactNode,
} from 'react'
import { api } from '../services/api'
import { useAuth } from './AuthProvider'
import type { Notification, ChatMessage } from '../types'

interface SocketContextType {
  isConnected: boolean
  sendChatMessage: (message: string) => void
  onChatResponse: (callback: (response: { response: string }) => void) => void
  onNotification: (callback: (notification: Notification) => void) => void
}

const SocketContext = createContext<SocketContextType | undefined>(undefined)

export function SocketProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const [isConnected, setIsConnected] = useState(false)

  const chatSocketRef = useRef<WebSocket | null>(null)
  const notificationSocketRef = useRef<WebSocket | null>(null)

  const chatCallbacksRef = useRef<Set<(response: { response: string }) => void>>(new Set())
  const notificationCallbacksRef = useRef<Set<(notification: Notification) => void>>(new Set())

  // Connect to chat WebSocket
  const connectChatSocket = useCallback(() => {
    const token = api.getToken()
    if (!token) return

    const wsUrl = `ws://${window.location.host}/api/chat/ws/${token}`

    try {
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('Chat WebSocket connected')
        setIsConnected(true)
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'response') {
          chatCallbacksRef.current.forEach((callback) => callback(data))
        }
      }

      ws.onclose = () => {
        console.log('Chat WebSocket disconnected')
        setIsConnected(false)
        // Reconnect after delay
        setTimeout(connectChatSocket, 3000)
      }

      ws.onerror = (error) => {
        console.error('Chat WebSocket error:', error)
      }

      chatSocketRef.current = ws
    } catch (error) {
      console.error('Failed to connect chat WebSocket:', error)
    }
  }, [])

  // Connect to notification WebSocket
  const connectNotificationSocket = useCallback(() => {
    const token = api.getToken()
    if (!token) return

    const wsUrl = `ws://${window.location.host}/api/notifications/ws/${token}`

    try {
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('Notification WebSocket connected')
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'notification') {
          notificationCallbacksRef.current.forEach((callback) => callback(data.notification))
        }
      }

      ws.onclose = () => {
        console.log('Notification WebSocket disconnected')
        // Reconnect after delay
        setTimeout(connectNotificationSocket, 3000)
      }

      ws.onerror = (error) => {
        console.error('Notification WebSocket error:', error)
      }

      notificationSocketRef.current = ws
    } catch (error) {
      console.error('Failed to connect notification WebSocket:', error)
    }
  }, [])

  // Connect when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      connectChatSocket()
      connectNotificationSocket()
    }

    return () => {
      chatSocketRef.current?.close()
      notificationSocketRef.current?.close()
    }
  }, [isAuthenticated, connectChatSocket, connectNotificationSocket])

  const sendChatMessage = useCallback((message: string) => {
    if (chatSocketRef.current?.readyState === WebSocket.OPEN) {
      chatSocketRef.current.send(JSON.stringify({ message }))
    }
  }, [])

  const onChatResponse = useCallback((callback: (response: { response: string }) => void) => {
    chatCallbacksRef.current.add(callback)
    return () => {
      chatCallbacksRef.current.delete(callback)
    }
  }, [])

  const onNotification = useCallback((callback: (notification: Notification) => void) => {
    notificationCallbacksRef.current.add(callback)
    return () => {
      notificationCallbacksRef.current.delete(callback)
    }
  }, [])

  return (
    <SocketContext.Provider
      value={{
        isConnected,
        sendChatMessage,
        onChatResponse,
        onNotification,
      }}
    >
      {children}
    </SocketContext.Provider>
  )
}

export function useSocket() {
  const context = useContext(SocketContext)
  if (context === undefined) {
    throw new Error('useSocket must be used within a SocketProvider')
  }
  return context
}
