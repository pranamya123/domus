/**
 * Domus App - Main Application Component
 *
 * Event-driven screen rendering based on backend events.
 * Includes Capacitor integration for iOS push notifications and deep links.
 */

import { useEffect, useCallback } from 'react';
import { useStore } from './store/useStore';
import { useApi } from './hooks/useApi';
import { useCapacitor, getDeviceToken } from './hooks/useCapacitor';
import { ScreenType } from './types';

// Pages
import { SplashScreen } from './pages/SplashScreen';
import { LoginPage } from './pages/LoginPage';
import { ChatPage } from './pages/ChatPage';

import './assets/styles.css';

function App() {
  const currentScreen = useStore((state) => state.currentScreen);
  const isAuthenticated = useStore((state) => state.isAuthenticated);
  const token = useStore((state) => state.token);
  const logout = useStore((state) => state.logout);
  const setScreen = useStore((state) => state.setScreen);
  const { fetchCurrentUser, registerDeviceToken } = useApi();

  // Clear session on app startup - require fresh login every time
  useEffect(() => {
    console.log('[App] Startup - clearing previous session');
    logout();
  }, []); // Empty deps = run once on mount

  // Debug logging for iOS
  useEffect(() => {
    console.log('[App] State changed:', {
      currentScreen,
      isAuthenticated,
      hasToken: !!token,
    });
  }, [currentScreen, isAuthenticated, token]);

  // Handle notification tap - navigate to chat
  const handleNotificationTap = useCallback((notificationId: string) => {
    console.log('[App] Notification tapped:', notificationId);
    setScreen(ScreenType.CHAT);
  }, [setScreen]);

  // Initialize Capacitor for iOS push notifications and deep links
  const { isNative, platform } = useCapacitor({
    onNotificationTap: handleNotificationTap,
  });

  // Register device token with backend when authenticated
  useEffect(() => {
    if (isAuthenticated && isNative) {
      // Give Capacitor time to register and get token
      const timer = setTimeout(() => {
        const token = getDeviceToken();
        if (token) {
          console.log('[App] Registering device token with backend...');
          registerDeviceToken(token)
            .then((result) => {
              console.log('[App] Device token registered:', result);
            })
            .catch((err) => {
              console.error('[App] Failed to register device token:', err);
            });
        }
      }, 2000); // Wait 2s for push registration to complete

      return () => clearTimeout(timer);
    }
  }, [isAuthenticated, isNative, registerDeviceToken]);

  // Fetch user on initial load if authenticated
  // Only logout on explicit 401 errors, not network failures
  useEffect(() => {
    if (isAuthenticated) {
      fetchCurrentUser().catch((err) => {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error('[App] fetchCurrentUser error:', errorMsg);

        // Only logout on explicit auth errors (401/token issues)
        // Don't logout on network errors - let user try to use the app
        if (errorMsg.includes('401') ||
            errorMsg.includes('Unauthorized') ||
            errorMsg.includes('token') ||
            errorMsg.includes('Session')) {
          console.log('[App] Auth error detected, logging out');
          logout();
        }
      });
    }
  }, [isAuthenticated, fetchCurrentUser, logout]);

  // Log platform info
  useEffect(() => {
    console.log('[App] Platform:', platform, 'Native:', isNative);
  }, [platform, isNative]);

  // Render current screen
  const renderScreen = () => {
    switch (currentScreen) {
      case ScreenType.SPLASH:
        return <SplashScreen />;

      case ScreenType.LANDING:
      case ScreenType.LOGIN:
        return <LoginPage />;

      case ScreenType.CHAT:
        return <ChatPage />;

      // TODO: Add more screens
      case ScreenType.CONNECT_FRIDGE_SENSE:
      case ScreenType.BLINK_2FA:
      case ScreenType.FRIDGE_SENSE_SUCCESS:
      case ScreenType.ACTIVITY_CENTER:
      case ScreenType.MENU:
        // Placeholder - navigate to chat for now
        return <ChatPage />;

      default:
        return <SplashScreen />;
    }
  };

  return (
    <div className="app-container">
      {renderScreen()}
    </div>
  );
}

export default App;
