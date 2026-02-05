/**
 * Geofencing Hook for Domus
 *
 * Manages location-based grocery store detection and notifications.
 *
 * Demo Implementation:
 * - Fetches geofences from backend on init
 * - Watches location when app is foregrounded
 * - Detects when user enters a geofence (within radius)
 * - Sends POST /location/entered to trigger notification
 *
 * Production Note:
 * For true background geofencing, native iOS code using
 * CLLocationManager.startMonitoring(for: CLCircularRegion) is required.
 * This demo implementation works when the app is in the foreground.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { Geolocation, Position } from '@capacitor/geolocation';

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : 'http://localhost:8000/api';

// Geofence from backend
interface Geofence {
  place_id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius: number; // meters
}

// =============================================================================
// Persistent Trigger State (survives app reload)
// =============================================================================

const STORAGE_KEY = 'domus_geofence_triggers';
const DEBOUNCE_MINUTES = 10; // Minimum minutes between triggers for same store

interface TriggerRecord {
  timestamp: number; // Unix ms
}

/**
 * Load triggered geofences from localStorage.
 */
function loadTriggeredState(): Record<string, TriggerRecord> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch (e) {
    console.warn('[Geofence] Failed to load trigger state:', e);
  }
  return {};
}

/**
 * Save triggered geofences to localStorage.
 */
function saveTriggeredState(state: Record<string, TriggerRecord>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.warn('[Geofence] Failed to save trigger state:', e);
  }
}

/**
 * Check if a geofence was recently triggered (within debounce window).
 */
function wasRecentlyTriggered(placeId: string): boolean {
  const state = loadTriggeredState();
  const record = state[placeId];

  if (!record) return false;

  const now = Date.now();
  const elapsed = now - record.timestamp;
  const debounceMs = DEBOUNCE_MINUTES * 60 * 1000;

  return elapsed < debounceMs;
}

/**
 * Mark a geofence as triggered (persists to localStorage).
 */
function markTriggered(placeId: string): void {
  const state = loadTriggeredState();
  state[placeId] = { timestamp: Date.now() };

  // Clean up old entries (older than 24h)
  const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
  for (const key of Object.keys(state)) {
    if (state[key].timestamp < dayAgo) {
      delete state[key];
    }
  }

  saveTriggeredState(state);
}

/**
 * Calculate distance between two coordinates using Haversine formula.
 * Returns distance in meters.
 */
function calculateDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const R = 6371000; // Earth's radius in meters
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Get stored auth token from localStorage.
 */
function getToken(): string | null {
  return localStorage.getItem('domus_token');
}

/**
 * Fetch geofences from backend.
 */
async function fetchGeofences(): Promise<Geofence[]> {
  const token = getToken();
  if (!token) {
    console.log('[Geofence] No auth token, skipping geofence fetch');
    return [];
  }

  try {
    const response = await fetch(`${API_BASE}/location/geofences`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log('[Geofence] Fetched geofences:', data.geofences?.length || 0);
    return data.geofences || [];
  } catch (error) {
    console.error('[Geofence] Failed to fetch geofences:', error);
    return [];
  }
}

/**
 * Send geofence entry event to backend.
 */
async function sendGeofenceEntry(
  placeId: string,
  latitude: number,
  longitude: number
): Promise<boolean> {
  const token = getToken();
  if (!token) {
    console.log('[Geofence] No auth token, skipping entry report');
    return false;
  }

  try {
    const response = await fetch(`${API_BASE}/location/entered`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        place_id: placeId,
        timestamp: new Date().toISOString(),
        latitude,
        longitude,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log('[Geofence] Entry response:', data);
    return data.triggered || false;
  } catch (error) {
    console.error('[Geofence] Failed to send entry:', error);
    return false;
  }
}

interface UseGeofenceOptions {
  /** Enable geofencing (default: true on native) */
  enabled?: boolean;
  /** Location update interval in ms (default: 30000 = 30s) */
  updateInterval?: number;
  /** Callback when entering a geofence */
  onGeofenceEnter?: (geofence: Geofence) => void;
}

interface UseGeofenceResult {
  /** Whether geofencing is active */
  isActive: boolean;
  /** Current location (if available) */
  currentLocation: { latitude: number; longitude: number } | null;
  /** List of registered geofences */
  geofences: Geofence[];
  /** Manually check current location against geofences */
  checkNow: () => Promise<void>;
  /** Start location watching */
  start: () => Promise<void>;
  /** Stop location watching */
  stop: () => void;
}

/**
 * Hook for managing geofence detection.
 *
 * Usage:
 * ```tsx
 * const { isActive, geofences } = useGeofence({
 *   onGeofenceEnter: (geofence) => {
 *     console.log('Entered:', geofence.name);
 *   }
 * });
 * ```
 */
export function useGeofence(options: UseGeofenceOptions = {}): UseGeofenceResult {
  const {
    enabled = true,
    updateInterval = 30000, // 30 seconds
    onGeofenceEnter,
  } = options;

  const [isActive, setIsActive] = useState(false);
  const [currentLocation, setCurrentLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [geofences, setGeofences] = useState<Geofence[]>([]);

  const watchIdRef = useRef<string | null>(null);
  const geofencesRef = useRef<Geofence[]>([]);
  const isNative = Capacitor.isNativePlatform();

  // Keep geofences ref in sync
  useEffect(() => {
    geofencesRef.current = geofences;
  }, [geofences]);

  /**
   * Check if current position is inside any geofence.
   */
  const checkGeofences = useCallback(
    async (position: Position) => {
      const { latitude, longitude } = position.coords;
      setCurrentLocation({ latitude, longitude });

      const fences = geofencesRef.current;
      if (fences.length === 0) return;

      for (const fence of fences) {
        const distance = calculateDistance(
          latitude,
          longitude,
          fence.latitude,
          fence.longitude
        );

        // Check if inside geofence radius
        if (distance <= fence.radius) {
          // Check debounce (persisted to localStorage, survives app reload)
          if (wasRecentlyTriggered(fence.place_id)) {
            console.log(
              `[Geofence] Debounced (within ${DEBOUNCE_MINUTES}min):`,
              fence.name
            );
            continue;
          }

          console.log(
            `[Geofence] ENTERED: ${fence.name} (${distance.toFixed(0)}m away)`
          );

          // Mark as triggered BEFORE sending (prevents race conditions)
          markTriggered(fence.place_id);

          // Send to backend
          const notificationSent = await sendGeofenceEntry(
            fence.place_id,
            latitude,
            longitude
          );

          // Call callback
          if (onGeofenceEnter) {
            onGeofenceEnter(fence);
          }

          if (notificationSent) {
            console.log('[Geofence] Notification triggered for:', fence.name);
          }
        }
      }
    },
    [onGeofenceEnter]
  );

  /**
   * Start watching location.
   */
  const start = useCallback(async () => {
    if (!isNative || !enabled) {
      console.log('[Geofence] Not starting (native:', isNative, 'enabled:', enabled, ')');
      return;
    }

    try {
      // Request permission
      const permStatus = await Geolocation.checkPermissions();
      if (permStatus.location !== 'granted') {
        const reqStatus = await Geolocation.requestPermissions();
        if (reqStatus.location !== 'granted') {
          console.log('[Geofence] Location permission denied');
          return;
        }
      }

      // Fetch geofences from backend
      const fences = await fetchGeofences();
      setGeofences(fences);

      if (fences.length === 0) {
        console.log('[Geofence] No geofences to monitor');
        return;
      }

      // Start watching position
      // Note: If location permission is denied, this will fail silently
      // The 7-minute demo timer still works without location
      let watchId: string;
      try {
        watchId = await Geolocation.watchPosition(
          {
            enableHighAccuracy: false, // Use low accuracy to reduce errors
            timeout: 15000,
            maximumAge: updateInterval,
          },
          (position, err) => {
            if (err) {
              // Only log once, don't spam
              const errMsg = err?.message || JSON.stringify(err);
              if (errMsg.includes('kCLErrorDomain')) {
                // Location services denied - stop watching silently
                console.log('[Geofence] Location denied, using demo timer instead');
                stop();
                return;
              }
              console.warn('[Geofence] Watch error:', errMsg);
              return;
            }
            if (position) {
              checkGeofences(position);
            }
          }
        );
        watchIdRef.current = watchId;
        setIsActive(true);
        console.log('[Geofence] Started watching with', fences.length, 'geofences');

        // Also do an immediate check (but don't fail if it errors)
        try {
          const currentPos = await Geolocation.getCurrentPosition();
          checkGeofences(currentPos);
        } catch (posErr) {
          console.log('[Geofence] Initial position check skipped');
        }
      } catch (watchErr) {
        console.log('[Geofence] Could not start watch, demo timer still works');
        return;
      }
    } catch (error) {
      console.error('[Geofence] Failed to start:', error);
    }
  }, [isNative, enabled, updateInterval, checkGeofences]);

  /**
   * Stop watching location.
   */
  const stop = useCallback(() => {
    if (watchIdRef.current) {
      Geolocation.clearWatch({ id: watchIdRef.current });
      watchIdRef.current = null;
      setIsActive(false);
      console.log('[Geofence] Stopped watching');
    }
  }, []);

  /**
   * Manually check current location.
   */
  const checkNow = useCallback(async () => {
    if (!isNative) return;

    try {
      const position = await Geolocation.getCurrentPosition();
      await checkGeofences(position);
    } catch (error) {
      console.error('[Geofence] Check failed:', error);
    }
  }, [isNative, checkGeofences]);

  // Auto-start on mount if enabled
  useEffect(() => {
    if (enabled && isNative) {
      // Delay start to allow auth to complete
      const timer = setTimeout(() => {
        start();
      }, 3000);

      return () => {
        clearTimeout(timer);
        stop();
      };
    }
  }, [enabled, isNative, start, stop]);

  return {
    isActive,
    currentLocation,
    geofences,
    checkNow,
    start,
    stop,
  };
}

export type { Geofence, UseGeofenceOptions, UseGeofenceResult };
