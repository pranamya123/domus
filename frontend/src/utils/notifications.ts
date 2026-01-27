/**
 * Push Notification utilities for Domus PWA
 */

const API_BASE = '/api/alerts';

// Check if push notifications are supported
export function isPushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window;
}

// Request notification permission
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) {
    console.warn('Notifications not supported');
    return 'denied';
  }

  const permission = await Notification.requestPermission();
  console.log('Notification permission:', permission);
  return permission;
}

// Subscribe to push notifications
export async function subscribeToPush(): Promise<PushSubscription | null> {
  if (!isPushSupported()) {
    console.warn('Push notifications not supported');
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.ready;

    // Get VAPID public key from server
    const response = await fetch(`${API_BASE}/push/vapid-key`);
    const { publicKey } = await response.json();

    // Subscribe to push
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });

    // Send subscription to server
    await fetch(`${API_BASE}/push/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        keys: {
          p256dh: arrayBufferToBase64(subscription.getKey('p256dh')),
          auth: arrayBufferToBase64(subscription.getKey('auth')),
        },
      }),
    });

    console.log('Push subscription successful');
    return subscription;
  } catch (error) {
    console.error('Push subscription failed:', error);
    return null;
  }
}

// Show a local notification (for testing/demo)
export async function showLocalNotification(
  title: string,
  body: string,
  options: NotificationOptions = {}
): Promise<void> {
  const permission = await requestNotificationPermission();

  if (permission !== 'granted') {
    console.warn('Notification permission not granted');
    return;
  }

  if ('serviceWorker' in navigator) {
    const registration = await navigator.serviceWorker.ready;
    registration.showNotification(title, {
      body,
      icon: '/icons/icon-192x192.png',
      badge: '/icons/badge-72x72.png',
      vibrate: [100, 50, 100],
      ...options,
    });
  } else {
    new Notification(title, { body, ...options });
  }
}

// Fetch proactive alerts
export async function fetchProactiveAlerts(): Promise<any> {
  try {
    const response = await fetch(`${API_BASE}/proactive`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch alerts:', error);
    return { alerts: [], count: 0 };
  }
}

// Create Instacart order
export async function createInstacartOrder(items: string[]): Promise<any> {
  try {
    const response = await fetch(`${API_BASE}/order/instacart`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to create order:', error);
    throw error;
  }
}

// Approve order
export async function approveOrder(orderId: string): Promise<any> {
  try {
    const response = await fetch(`${API_BASE}/order/${orderId}/approve`, {
      method: 'POST',
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to approve order:', error);
    throw error;
  }
}

// Get store deals
export async function fetchStoreDeals(): Promise<any> {
  try {
    const response = await fetch(`${API_BASE}/deals`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch deals:', error);
    return { deals: [] };
  }
}

// Get calendar events
export async function fetchCalendarEvents(): Promise<any> {
  try {
    const response = await fetch(`${API_BASE}/calendar-events`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch calendar events:', error);
    return { events: [] };
  }
}

// Helper: Convert VAPID key
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Helper: Convert ArrayBuffer to Base64
function arrayBufferToBase64(buffer: ArrayBuffer | null): string {
  if (!buffer) return '';
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}
