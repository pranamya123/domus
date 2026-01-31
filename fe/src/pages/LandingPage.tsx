/**
 * Landing Page - Pre-login welcome screen
 */

import { useStore } from '../store/useStore';
import { ScreenType } from '../types';
import '../assets/styles.css';

export function LandingPage() {
  const setScreen = useStore((state) => state.setScreen);

  return (
    <div className="screen landing-screen">
      <div className="landing-content">
        {/* Logo */}
        <div className="landing-logo-container">
          <svg
            className="landing-logo"
            viewBox="0 0 120 120"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle cx="60" cy="60" r="55" fill="#2E7D32" />
            <path
              d="M60 25L25 55V95H50V70H70V95H95V55L60 25Z"
              fill="white"
            />
            <circle cx="60" cy="55" r="8" fill="#2E7D32" />
          </svg>
        </div>

        <h1 className="landing-title">Domus</h1>
        <p className="landing-description">
          Your AI-powered smart home assistant. Manage your fridge, calendar,
          and home services all in one place.
        </p>

        {/* Features */}
        <div className="landing-features">
          <div className="feature-item">
            <div className="feature-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="4" y="2" width="16" height="20" rx="2" />
                <line x1="4" y1="10" x2="20" y2="10" />
              </svg>
            </div>
            <span>Smart Fridge</span>
          </div>
          <div className="feature-item">
            <div className="feature-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <span>Calendar</span>
          </div>
          <div className="feature-item">
            <div className="feature-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 1v6m0 6v6m11-7h-6m-6 0H1" />
              </svg>
            </div>
            <span>Services</span>
          </div>
        </div>

        {/* CTA Button */}
        <button
          className="landing-cta-button"
          onClick={() => setScreen(ScreenType.LOGIN)}
        >
          Get Started
        </button>

        <p className="landing-terms">
          By continuing, you agree to our Terms of Service
        </p>
      </div>
    </div>
  );
}
