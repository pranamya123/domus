/**
 * Domus Frontend Configuration
 */

// Demo mode: bypasses login screen and authentication
// Set to true for demos, false for production
export const DEMO_MODE = true;

// API configuration
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
