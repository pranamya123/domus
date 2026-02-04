/**
 * WebSocket Hook - Real-time event handling
 */

import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store/useStore';
import {
  DomusEvent,
  EventType,
  ScreenType,
  AgentType,
  AgentStatus,
  isUIScreenEvent,
  isAgentStatusEvent,
  isChatMessageEvent,
  isCapabilitiesEvent,
  isNotificationCreatedEvent,
  Notification,
} from '../types';
import { scheduleBakeSaleNotification } from './useCapacitor';

const WS_URL = '/ws';
const RECONNECT_DELAY = 3000;
const MAX_RECONNECTS = 5;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const token = useStore((state) => state.token);
  const setConnected = useStore((state) => state.setConnected);
  const setScreen = useStore((state) => state.setScreen);
  const setAgentStatus = useStore((state) => state.setAgentStatus);
  const addMessage = useStore((state) => state.addMessage);
  const setCapabilities = useStore((state) => state.setCapabilities);
  const addNotification = useStore((state) => state.addNotification);

  const handleEvent = useCallback((event: DomusEvent) => {
    console.log('[WS] Event received:', event.type, event.payload);

    switch (event.type) {
      case EventType.UI_SCREEN:
        if (isUIScreenEvent(event)) {
          setScreen(event.payload.screen as ScreenType);
        }
        break;

      case EventType.AGENT_STATUS:
        if (isAgentStatusEvent(event)) {
          setAgentStatus(
            event.payload.agent as AgentType,
            event.payload.status as AgentStatus
          );
        }
        break;

      case EventType.CHAT_USER_MESSAGE:
      case EventType.CHAT_ASSISTANT_MESSAGE:
        if (isChatMessageEvent(event)) {
          const payload = event.payload as {
            message_id?: string;
            content: string;
            sender: 'user' | 'domus';
          };
          addMessage({
            id: payload.message_id || event.event_id,
            content: payload.content,
            sender: payload.sender,
            timestamp: event.ts,
            status: 'sent',
          });
        }
        break;

      case EventType.HEARTBEAT:
        // Heartbeat received, connection is alive
        break;

      case EventType.ERROR:
        console.error('[WS] Error event:', event.payload);
        break;

      case EventType.CAPABILITIES_UPDATED:
        if (isCapabilitiesEvent(event)) {
          setCapabilities(event.payload);
        }
        break;

      case EventType.NOTIFICATION_CREATED:
        if (isNotificationCreatedEvent(event)) {
          // Add new notification to store for real-time bell badge update
          const notifPayload = event.payload;
          const newNotification: Notification = {
            notification_id: notifPayload.notification_id,
            title: notifPayload.title,
            body: notifPayload.body,
            sent_at: event.ts,
            read_at: null,
            notification_type: notifPayload.notification_type as 'chat' | 'proactive',
            chat_seed_content: `${notifPayload.title}\n\n${notifPayload.body}`,
            event_id: notifPayload.event_id || null,
          };
          addNotification(newNotification);
          console.log('[WS] New notification added:', newNotification.title);
        }
        break;

      default:
        console.log('[WS] Unhandled event type:', event.type);
    }
  }, [setScreen, setAgentStatus, addMessage, setCapabilities, addNotification]);
  
  const connect = useCallback(() => {
    if (!token || wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Determine WebSocket base URL
    // Priority: VITE_WS_URL > derive from VITE_API_URL > same-origin fallback
    let wsBase: string;
    if (import.meta.env.VITE_WS_URL) {
      wsBase = import.meta.env.VITE_WS_URL;
    } else if (import.meta.env.VITE_API_URL) {
      // Derive WS URL from API URL (http://host:port -> ws://host:port)
      const apiUrl = import.meta.env.VITE_API_URL;
      wsBase = apiUrl.replace(/^http/, 'ws');
    } else {
      // Fallback to same-origin (for local dev with proxy)
      wsBase = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
    }

    // Construct full WebSocket URL
    const wsUrl = `${wsBase}${WS_URL}?token=${encodeURIComponent(token)}`;
  
    console.log('[WS] Connecting to:', wsUrl);
    const ws = new WebSocket(wsUrl);
  
    ws.onopen = () => {
      console.log('[WS] Connected');
      setConnected(true);
      reconnectCountRef.current = 0;

      // Schedule bake sale notification for 3 minutes from now
      // This is Feature 2: "Bake Sale Prep, Handled"
      scheduleBakeSaleNotification(3);
    };
  
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as DomusEvent;
        handleEvent(data);
      } catch (err) {
        console.error('[WS] Failed to parse message:', err);
      }
    };
  
    ws.onclose = (event) => {
      console.log('[WS] Disconnected:', event.code, event.reason);
      setConnected(false);
      wsRef.current = null;
  
      // Attempt reconnection
      if (reconnectCountRef.current < MAX_RECONNECTS && token) {
        reconnectCountRef.current++;
        console.log(
          `[WS] Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectCountRef.current})`
        );
        reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_DELAY);
      }
    };
  
    ws.onerror = (error) => {
      console.error('[WS] Error:', error);
    };
  
    wsRef.current = ws;
  }, [token, handleEvent, setConnected]);
  
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, [setConnected]);

  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'chat',
        content,
      }));
      return true;
    }
    return false;
  }, []);

  // Auto-connect when token is available
  useEffect(() => {
    if (token) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [token, connect, disconnect]);

  return {
    isConnected: useStore((state) => state.isConnected),
    sendMessage,
    connect,
    disconnect,
  };
}
