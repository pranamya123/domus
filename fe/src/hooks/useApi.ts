/**
 * API Hook - REST API calls
 */

import { useCallback } from 'react';
import { useStore } from '../store/useStore';
import { LoginResponse, User, CapabilitiesPayload } from '../types';

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
    throw new Error(error.detail || `HTTP ${response.status}`);
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

  return {
    login,
    logout: doLogout,
    fetchCurrentUser,
    healthCheck,
    blinkLogin,
    blinkVerify,
  };
}
