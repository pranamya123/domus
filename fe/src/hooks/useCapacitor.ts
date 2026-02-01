/**
 * Capacitor Hook - iOS Notifications & Deep Links
 *
 * Handles:
 * - Local notifications (no Apple Developer account needed)
 * - Push notification registration and permission (if available)
 * - Notification tap handling
 * - Deep link handling (domus://chat?notification_id=XYZ)
 */

import { useEffect, useCallback, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { PushNotifications, Token, PushNotificationSchema, ActionPerformed } from '@capacitor/push-notifications';
import { LocalNotifications } from '@capacitor/local-notifications';
import { App, URLOpenListenerEvent } from '@capacitor/app';
import { useStore } from '../store/useStore';
import { useApi } from './useApi';

// === DEMO: Log device token for testing ===
// In production, you'd send this to your backend
let cachedDeviceToken: string | null = null;

export function getDeviceToken(): string | null {
  return cachedDeviceToken;
}

// Track if local notifications are initialized
let localNotificationsInitialized = false;

/**
 * Send a local notification (works without Apple Developer account)
 * This shows a system notification even when app is backgrounded
 */
export async function sendLocalNotification(
  title: string,
  body: string,
  notificationId?: string
): Promise<void> {
  if (!Capacitor.isNativePlatform()) {
    console.log('[LocalNotification] Not native platform, skipping');
    return;
  }

  try {
    // Request permission if not already granted
    const permStatus = await LocalNotifications.checkPermissions();
    if (permStatus.display !== 'granted') {
      const reqResult = await LocalNotifications.requestPermissions();
      if (reqResult.display !== 'granted') {
        console.warn('[LocalNotification] Permission denied');
        return;
      }
    }

    // Schedule immediate local notification
    await LocalNotifications.schedule({
      notifications: [
        {
          id: Math.floor(Math.random() * 100000),
          title: title,
          body: body,
          schedule: { at: new Date(Date.now() + 100) }, // 100ms from now
          sound: 'default',
          extra: {
            notification_id: notificationId || '',
          },
        },
      ],
    });

    console.log('[LocalNotification] Scheduled:', title);
  } catch (err) {
    console.error('[LocalNotification] Failed to send:', err);
  }
}

// ID for the scheduled background notification (so we can cancel it)
const BACKGROUND_NOTIFICATION_ID = 999999;

/**
 * Schedule a notification to fire X minutes after app is backgrounded
 */
export async function scheduleBackgroundNotification(delayMinutes: number = 3): Promise<void> {
  if (!Capacitor.isNativePlatform()) {
    return;
  }

  try {
    // Cancel any existing scheduled background notification
    await LocalNotifications.cancel({ notifications: [{ id: BACKGROUND_NOTIFICATION_ID }] });

    // Request permission if not already granted
    const permStatus = await LocalNotifications.checkPermissions();
    if (permStatus.display !== 'granted') {
      return;
    }

    const delayMs = delayMinutes * 60 * 1000;
    const fireAt = new Date(Date.now() + delayMs);

    await LocalNotifications.schedule({
      notifications: [
        {
          id: BACKGROUND_NOTIFICATION_ID,
          title: 'domus',
          body: 'Missing items for the Bake Sale tomorrow, order now',
          schedule: { at: fireAt },
          sound: 'default',
          extra: {
            notification_id: 'background_reminder',
          },
        },
      ],
    });

    console.log('[LocalNotification] Background notification scheduled for:', fireAt.toLocaleTimeString());
  } catch (err) {
    console.error('[LocalNotification] Failed to schedule background notification:', err);
  }
}

/**
 * Cancel the scheduled background notification (when app comes to foreground)
 */
export async function cancelBackgroundNotification(): Promise<void> {
  if (!Capacitor.isNativePlatform()) {
    return;
  }

  try {
    await LocalNotifications.cancel({ notifications: [{ id: BACKGROUND_NOTIFICATION_ID }] });
    console.log('[LocalNotification] Background notification cancelled');
  } catch (err) {
    console.error('[LocalNotification] Failed to cancel background notification:', err);
  }
}

interface UseCapacitorOptions {
  onNotificationTap?: (notificationId: string) => void;
}

export function useCapacitor(options: UseCapacitorOptions = {}) {
  const { onNotificationTap } = options;
  const addMessage = useStore((state) => state.addMessage);
  const { resolveNotificationToChat } = useApi();
  const hasInitialized = useRef(false);

  /**
   * Handle notification_id from deep link or push tap
   * - Resolves the notification to get chat_seed_content
   * - Inserts as assistant message
   * - Marks notification as read
   */
  const handleNotificationId = useCallback(async (notificationId: string) => {
    console.log('[Capacitor] Handling notification_id:', notificationId);

    try {
      const result = await resolveNotificationToChat(notificationId);

      // Insert the chat seed content as assistant message
      addMessage({
        id: `notif-${notificationId}`,
        content: result.chat_seed_content,
        sender: 'domus',
        timestamp: new Date().toISOString(),
        fromNotification: true,
      });

      // Call optional callback
      onNotificationTap?.(notificationId);

      console.log('[Capacitor] Notification resolved, message added to chat');
    } catch (err) {
      console.error('[Capacitor] Failed to resolve notification:', err);
    }
  }, [resolveNotificationToChat, addMessage, onNotificationTap]);

  /**
   * Parse notification_id from URL
   */
  const extractNotificationId = useCallback((url: string): string | null => {
    try {
      // Handle both deep links (domus://chat?notification_id=X)
      // and web URLs (?notification_id=X)
      const urlObj = new URL(url.replace('domus://', 'https://domus.app/'));
      return urlObj.searchParams.get('notification_id');
    } catch {
      // Try simple query string parsing
      const match = url.match(/notification_id=([^&]+)/);
      return match ? match[1] : null;
    }
  }, []);

  /**
   * Initialize local notifications (works without Apple Developer account)
   */
  const initLocalNotifications = useCallback(async () => {
    if (!Capacitor.isNativePlatform() || localNotificationsInitialized) {
      return;
    }

    console.log('[Capacitor] Initializing local notifications...');

    try {
      // Request permission
      const permStatus = await LocalNotifications.checkPermissions();
      if (permStatus.display !== 'granted') {
        const reqResult = await LocalNotifications.requestPermissions();
        console.log('[Capacitor] Local notification permission:', reqResult.display);
      }

      // Listen for local notification taps
      LocalNotifications.addListener('localNotificationActionPerformed', (action) => {
        console.log('[Capacitor] Local notification tapped:', action);

        const notificationId = action.notification.extra?.notification_id;
        if (notificationId) {
          handleNotificationId(notificationId);
        }
      });

      localNotificationsInitialized = true;
      console.log('[Capacitor] Local notifications initialized');
    } catch (err) {
      console.error('[Capacitor] Failed to init local notifications:', err);
    }
  }, [handleNotificationId]);

  /**
   * Initialize push notifications (iOS only - requires Apple Developer account)
   */
  const initPushNotifications = useCallback(async () => {
    if (!Capacitor.isNativePlatform()) {
      console.log('[Capacitor] Not a native platform, skipping push init');
      return;
    }

    console.log('[Capacitor] Initializing push notifications...');

    try {
      // Request permission
      const permResult = await PushNotifications.requestPermissions();
      console.log('[Capacitor] Permission result:', permResult.receive);

      if (permResult.receive !== 'granted') {
        console.warn('[Capacitor] Push notification permission denied');
        return;
      }

      // Register for push notifications
      await PushNotifications.register();

      // === Event Listeners ===

      // Registration success - get FCM token
      PushNotifications.addListener('registration', (token: Token) => {
        cachedDeviceToken = token.value;
        // === DEMO: Log token for manual testing ===
        console.log('='.repeat(60));
        console.log('[DEMO] FCM Device Token:');
        console.log(token.value);
        console.log('='.repeat(60));
        console.log('Copy this token to your backend for testing push notifications');
      });

      // Registration error
      PushNotifications.addListener('registrationError', (error) => {
        console.error('[Capacitor] Push registration error:', error);
      });

      // Push received while app is in foreground
      PushNotifications.addListener('pushNotificationReceived', (notification: PushNotificationSchema) => {
        console.log('[Capacitor] Push received (foreground):', notification);
        // Notification will be shown by the OS based on presentationOptions
      });

      // Push notification tapped
      PushNotifications.addListener('pushNotificationActionPerformed', (action: ActionPerformed) => {
        console.log('[Capacitor] Push notification tapped:', action);

        // Extract notification_id from payload
        const data = action.notification.data;
        const notificationId = data?.notification_id;

        if (notificationId) {
          handleNotificationId(notificationId);
        }
      });

      console.log('[Capacitor] Push notification listeners registered');
    } catch (err) {
      console.error('[Capacitor] Push notifications not available:', err);
    }
  }, [handleNotificationId]);

  /**
   * Initialize deep link handling
   */
  const initDeepLinks = useCallback(async () => {
    if (!Capacitor.isNativePlatform()) {
      // For web, check URL params on load
      const notificationId = extractNotificationId(window.location.href);
      if (notificationId) {
        console.log('[Capacitor] Found notification_id in web URL:', notificationId);
        handleNotificationId(notificationId);
      }
      return;
    }

    // Handle app opened via deep link
    App.addListener('appUrlOpen', (event: URLOpenListenerEvent) => {
      console.log('[Capacitor] App opened via URL:', event.url);

      const notificationId = extractNotificationId(event.url);
      if (notificationId) {
        handleNotificationId(notificationId);
      }
    });

    // Check if app was launched with a URL
    const launchUrl = await App.getLaunchUrl();
    if (launchUrl?.url) {
      console.log('[Capacitor] App launched with URL:', launchUrl.url);
      const notificationId = extractNotificationId(launchUrl.url);
      if (notificationId) {
        handleNotificationId(notificationId);
      }
    }

    console.log('[Capacitor] Deep link listeners registered');
  }, [extractNotificationId, handleNotificationId]);

  /**
   * Initialize app state change listener for background notifications
   */
  const initAppStateListener = useCallback(async () => {
    if (!Capacitor.isNativePlatform()) {
      return;
    }

    // Listen for app state changes
    App.addListener('appStateChange', async (state) => {
      console.log('[Capacitor] App state changed:', state.isActive ? 'foreground' : 'background');

      if (!state.isActive) {
        // App went to background - schedule notification for 3 minutes later
        await scheduleBackgroundNotification(3);
      } else {
        // App came to foreground - cancel any pending notification
        await cancelBackgroundNotification();
      }
    });

    console.log('[Capacitor] App state listener registered');
  }, []);

  /**
   * Initialize Capacitor on mount
   */
  useEffect(() => {
    if (hasInitialized.current) return;
    hasInitialized.current = true;

    const init = async () => {
      console.log('[Capacitor] Platform:', Capacitor.getPlatform());
      console.log('[Capacitor] Is native:', Capacitor.isNativePlatform());

      // Initialize local notifications (works without Apple Developer account)
      await initLocalNotifications();

      // Initialize push notifications (requires Apple Developer account)
      await initPushNotifications();

      // Initialize deep link handling
      await initDeepLinks();

      // Initialize app state listener for background notifications
      await initAppStateListener();
    };

    init().catch(console.error);

    // Cleanup listeners on unmount
    return () => {
      if (Capacitor.isNativePlatform()) {
        PushNotifications.removeAllListeners();
        LocalNotifications.removeAllListeners();
        App.removeAllListeners();
      }
    };
  }, [initLocalNotifications, initPushNotifications, initDeepLinks, initAppStateListener]);

  return {
    isNative: Capacitor.isNativePlatform(),
    platform: Capacitor.getPlatform(),
    getDeviceToken,
    sendLocalNotification,
  };
}
