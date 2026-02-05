/**
 * Splash Screen - Exact mockup specs
 * Shows for 4 seconds on app open
 *
 * To change duration: edit the 4000 value on line 21
 */

import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import { ScreenType } from '../types';

export function SplashScreen() {
  const setScreen = useStore((state) => state.setScreen);
  const currentScreen = useStore((state) => state.currentScreen);
  const isAuthenticated = useStore((state) => state.isAuthenticated);

  useEffect(() => {
    // Only run timer if we're actually on the splash screen
    if (currentScreen !== ScreenType.SPLASH) {
      console.log('[Splash] Not on splash screen, skipping timer');
      return;
    }

    console.log('[Splash] Starting timer, isAuthenticated:', isAuthenticated);

    const timer = setTimeout(() => {
      // Double-check we should still navigate
      const targetScreen = isAuthenticated ? ScreenType.CHAT : ScreenType.LOGIN;
      console.log('[Splash] Timer fired, navigating to:', targetScreen);
      setScreen(targetScreen);
    }, 3000); // 3 seconds splash duration

    return () => {
      console.log('[Splash] Cleaning up timer');
      clearTimeout(timer);
    };
  }, [setScreen, isAuthenticated, currentScreen]);

  return (
    <div style={styles.container}>
      <div style={styles.content}>
        <h1 style={styles.logo}>domus.</h1>
        <p style={styles.tagline}>one home, multiple agents</p>
      </div>
      <p style={styles.footer}>Powered by Gemini 3</p>
    </div>
  );
}

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    height: '100vh',
    width: '100vw',
    backgroundColor: '#E8F5E9',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    position: 'fixed',
    top: 0,
    left: 0,
  },
  content: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    textAlign: 'center',
  },
  logo: {
    fontFamily: '"Playfair Display", serif',
    fontSize: '73px',
    fontWeight: 800,
    color: '#034F03',
    margin: 0,
    lineHeight: 1,
  },
  tagline: {
    fontFamily: '"Playfair Display", serif',
    fontSize: '21px',
    fontWeight: 400,
    color: '#525151',
    margin: 0,
  },
  footer: {
    position: 'absolute',
    bottom: '39px',
    left: 0,
    right: 0,
    fontFamily: 'Roboto, sans-serif',
    fontSize: '12px',
    fontWeight: 400,
    color: '#525151',
    margin: 0,
    textAlign: 'center',
  },
};
