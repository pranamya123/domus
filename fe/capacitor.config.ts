import { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor Configuration for Domus iOS App
 *
 * DEMO MODE: Set DEMO_SERVER_URL to your ngrok/tunnel URL when testing
 * with a remote backend. Comment out the server block for local builds.
 */

// === DEMO CONFIGURATION ===
// Uncomment and set this to your ngrok URL for remote demo testing
// const DEMO_SERVER_URL = 'https://your-ngrok-url.ngrok.io';

const config: CapacitorConfig = {
  appId: 'com.domus.app',
  appName: 'Domus',
  webDir: 'dist',

  // === Server Configuration ===
  // For DEMO: Uncomment this block and set your ngrok URL to load remote web app
  // server: {
  //   url: DEMO_SERVER_URL,
  //   cleartext: true,  // Allow HTTP for local testing
  // },

  // === iOS Configuration ===
  ios: {
    // Allow mixed content for demo (HTTP + HTTPS)
    allowsLinkPreview: false,
    contentInset: 'automatic',
    // Custom URL scheme for deep links
    scheme: 'domus',
  },

  // === Plugins Configuration ===
  plugins: {
    // Push Notifications
    PushNotifications: {
      // Present notification when app is in foreground
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

export default config;
