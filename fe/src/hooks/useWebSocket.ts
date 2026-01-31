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
} from '../types';

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

      default:
        console.log('[WS] Unhandled event type:', event.type);
    }
  }, [setScreen, setAgentStatus, addMessage, setCapabilities]);
  
  const connect = useCallback(() => {
    if (!token || wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }
  
    // Prefer explicit WS base URL from Vite env (e.g. ws://localhost:8000)
    // Fallback to same-origin (useful if you proxy /ws via Vite in dev)
    const wsBase =
      import.meta.env.VITE_WS_URL ??
      `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
  
    // Construct full WebSocket URL
    const wsUrl = `${wsBase}${WS_URL}?token=${encodeURIComponent(token)}`;
  
    console.log('[WS] Connecting to:', wsUrl);
    const ws = new WebSocket(wsUrl);
  
    ws.onopen = () => {
      console.log('[WS] Connected');
      setConnected(true);
      reconnectCountRef.current = 0;
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
