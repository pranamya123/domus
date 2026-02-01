/**
 * API Hook - REST API calls
 */

import { useCallback } from 'react';
import { useStore } from '../store/useStore';
import { LoginResponse, User, CapabilitiesPayload, Notification } from '../types';

const API_BASE = import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api` : 'http://localhost:8000/api';

interface ApiError {
  detail: string;
}

interface BlinkLoginResponse {
  requires_2fa: boolean;
  message: string;
  capabilities: CapabilitiesPayload;
}

interface BlinkVerifyResponse {
  success: boolean;
  message: string;
  capabilities: CapabilitiesPayload;
}

interface MediaStatus {
  thumbnail: { available: boolean; size_bytes: number; modified_at: string } | null;
  video: { available: boolean; size_bytes: number; modified_at: string } | null;
}

interface NotificationsListResponse {
  notifications: Notification[];
  unread_count: number;
}

interface NotificationResolveResponse {
  notification_id: string;
  chat_seed_content: string;
  marked_read: boolean;
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: 'Unknown error' }));
    // Include status code in error message for proper error handling
    const statusPrefix = response.status === 401 ? '401 Unauthorized: ' : `HTTP ${response.status}: `;
    throw new Error(statusPrefix + (error.detail || 'Request failed'));
  }

  return response.json();
}

export function useApi() {
  const token = useStore((state) => state.token);
  const setToken = useStore((state) => state.setToken);
  const setUser = useStore((state) => state.setUser);
  const setCapabilities = useStore((state) => state.setCapabilities);
  const setLoading = useStore((state) => state.setLoading);
  const logout = useStore((state) => state.logout);
  const setNotifications = useStore((state) => state.setNotifications);
  const setUnreadCount = useStore((state) => state.setUnreadCount);
  const markNotificationRead = useStore((state) => state.markNotificationRead);

  const login = useCallback(async (email: string): Promise<LoginResponse> => {
    setLoading(true);
    try {
      const response = await fetchApi<LoginResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email }),
      });

      setToken(response.token);
      setUser({
        id: response.user_id,
        name: response.user_name,
        email: response.user_email,
      });

      return response;
    } finally {
      setLoading(false);
    }
  }, [setToken, setUser, setLoading]);

  const fetchCurrentUser = useCallback(async (): Promise<User> => {
    const response = await fetchApi<{
      user_id: string;
      name: string;
      email: string;
      picture?: string;
      capabilities: {
        gmail_connected: boolean;
        blink_connected: boolean;
        fridge_sense_available: boolean;
        calendar_connected: boolean;
        instacart_connected: boolean;
      };
    }>('/me', {}, token);

    const user: User = {
      id: response.user_id,
      name: response.name,
      email: response.email,
      picture: response.picture,
    };

    setUser(user);
    setCapabilities(response.capabilities);

    return user;
  }, [token, setUser, setCapabilities]);

  const doLogout = useCallback(async () => {
    try {
      await fetchApi('/auth/logout', { method: 'POST' }, token);
    } catch (err) {
      // Ignore logout errors
    }
    logout();
  }, [token, logout]);

  const healthCheck = useCallback(async (): Promise<boolean> => {
    try {
      const response = await fetchApi<{ status: string }>('/health');
      return response.status === 'healthy';
    } catch {
      return false;
    }
  }, []);

  const blinkLogin = useCallback(async (email: string, password: string): Promise<BlinkLoginResponse> => {
    const response = await fetchApi<BlinkLoginResponse>('/blink/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }, token);

    setCapabilities(response.capabilities);
    return response;
  }, [token, setCapabilities]);

  const blinkVerify = useCallback(async (pin: string): Promise<BlinkVerifyResponse> => {
    const response = await fetchApi<BlinkVerifyResponse>('/blink/verify', {
      method: 'POST',
      body: JSON.stringify({ pin }),
    }, token);

    setCapabilities(response.capabilities);
    return response;
  }, [token, setCapabilities]);

  const getMediaStatus = useCallback(async (): Promise<MediaStatus> => {
    return fetchApi<MediaStatus>('/media/status', {}, token);
  }, [token]);

  const getMediaThumbnailUrl = useCallback((): string => {
    return `${API_BASE}/media/thumbnail`;
  }, []);

  const getMediaVideoUrl = useCallback((): string => {
    return `${API_BASE}/media/video`;
  }, []);

  // Notification API methods
  const fetchNotifications = useCallback(async (): Promise<NotificationsListResponse> => {
    const response = await fetchApi<NotificationsListResponse>('/notifications', {}, token);
    setNotifications(response.notifications);
    setUnreadCount(response.unread_count);
    return response;
  }, [token, setNotifications, setUnreadCount]);

  const fetchUnreadCount = useCallback(async (): Promise<number> => {
    const response = await fetchApi<{ unread_count: number }>('/notifications/unread-count', {}, token);
    setUnreadCount(response.unread_count);
    return response.unread_count;
  }, [token, setUnreadCount]);

  const resolveNotificationToChat = useCallback(async (notificationId: string): Promise<NotificationResolveResponse> => {
    const response = await fetchApi<NotificationResolveResponse>(
      `/notifications/${notificationId}/resolve`,
      { method: 'POST' },
      token
    );
    markNotificationRead(notificationId);
    return response;
  }, [token, markNotificationRead]);

  // Test endpoint to create a sample proactive notification
  const createTestNotification = useCallback(async (): Promise<{ notification_id: string; title: string; body: string }> => {
    const response = await fetchApi<{ notification_id: string; title: string; body: string }>(
      '/notifications/test',
      { method: 'POST' },
      token
    );
    return response;
  }, [token]);

  // Push notification API methods
  const registerDeviceToken = useCallback(async (deviceToken: string): Promise<{ message: string; configured: boolean }> => {
    return fetchApi<{ message: string; configured: boolean }>(
      '/push/device-token',
      { method: 'POST', body: JSON.stringify({ token: deviceToken }) },
      token
    );
  }, [token]);

  const getPushStatus = useCallback(async (): Promise<{ configured: boolean; has_server_key: boolean; has_device_token: boolean }> => {
    return fetchApi<{ configured: boolean; has_server_key: boolean; has_device_token: boolean }>(
      '/push/status',
      {},
      token
    );
  }, [token]);

  const sendTestPush = useCallback(async (): Promise<{ push_sent: boolean; push_error: string | null }> => {
    return fetchApi<{ push_sent: boolean; push_error: string | null }>(
      '/push/test',
      { method: 'POST' },
      token
    );
  }, [token]);

  return {
    login,
    logout: doLogout,
    fetchCurrentUser,
    healthCheck,
    blinkLogin,
    blinkVerify,
    getMediaStatus,
    getMediaThumbnailUrl,
    getMediaVideoUrl,
    fetchNotifications,
    fetchUnreadCount,
    resolveNotificationToChat,
    createTestNotification,
    registerDeviceToken,
    getPushStatus,
    sendTestPush,
    token,
  };
}
