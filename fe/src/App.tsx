/**
 * Domus App - Main Application Component
 *
 * Event-driven screen rendering based on backend events.
 */

import { useEffect } from 'react';
import { useStore } from './store/useStore';
import { useApi } from './hooks/useApi';
import { ScreenType } from './types';

// Pages
import { SplashScreen } from './pages/SplashScreen';
import { LoginPage } from './pages/LoginPage';
import { ChatPage } from './pages/ChatPage';

import './assets/styles.css';

function App() {
  const currentScreen = useStore((state) => state.currentScreen);
  const isAuthenticated = useStore((state) => state.isAuthenticated);
  const logout = useStore((state) => state.logout);
  const { fetchCurrentUser } = useApi();

  // Fetch user on initial load if authenticated
  // If token is invalid (401), clear it and go to login
  useEffect(() => {
    if (isAuthenticated) {
      fetchCurrentUser().catch((err) => {
        console.error('Session invalid:', err);
        logout(); // Clear stale token
      });
    }
  }, [isAuthenticated, fetchCurrentUser, logout]);

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
