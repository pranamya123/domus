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
  const isAuthenticated = useStore((state) => state.isAuthenticated);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (isAuthenticated) {
        setScreen(ScreenType.CHAT);
      } else {
        setScreen(ScreenType.LOGIN);
      }
    }, 4000); // <-- CHANGE THIS VALUE FOR DURATION (milliseconds)

    return () => clearTimeout(timer);
  }, [setScreen, isAuthenticated]);

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
    color: '#077507',
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
