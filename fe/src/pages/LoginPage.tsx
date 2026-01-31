/**
 * Login Page - Exact mockup specs
 */

import { useState } from 'react';
import { useStore } from '../store/useStore';
import { useApi } from '../hooks/useApi';
import { ScreenType } from '../types';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const isLoading = useStore((state) => state.isLoading);
  const setScreen = useStore((state) => state.setScreen);
  const { login } = useApi();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!email) {
      setError('Please enter your email');
      return;
    }

    try {
      await login(email);
      setScreen(ScreenType.CHAT);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        {/* Title */}
        <h1 style={styles.title}>Login with Google</h1>

        {/* Subtitle */}
        <p style={styles.subtitle}>Enter your credentials to login.</p>

        {/* Form */}
        <form onSubmit={handleSubmit} style={styles.form}>
          <input
            type="email"
            style={styles.input}
            placeholder="Enter your email id"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isLoading}
          />

          <input
            type="password"
            style={styles.input}
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={isLoading}
          />

          {error && <p style={styles.error}>{error}</p>}

          <button
            type="submit"
            style={styles.continueButton}
            disabled={isLoading}
          >
            {isLoading ? 'Loading...' : 'Continue'}
          </button>
        </form>
      </div>
    </div>
  );
}

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    height: '100vh',
    width: '100vw',
    backgroundColor: '#E8F5E9',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    position: 'fixed',
    top: 0,
    left: 0,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: '10px',
    padding: '24px',
    width: '320px',
    position: 'relative',
    boxShadow: '0 2px 10px rgba(0, 0, 0, 0.05)',
  },
  title: {
    fontFamily: '"Prata", serif',
    fontSize: '19px',
    fontWeight: 400,
    color: '#000000',
    textAlign: 'center',
    margin: '8px 0 8px 0',
  },
  subtitle: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    fontWeight: 400,
    color: '#A1A1A1',
    textAlign: 'center',
    margin: '0 0 24px 0',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    alignItems: 'center',
  },
  input: {
    width: '85%',
    padding: '14px 20px',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    fontWeight: 400,
    color: '#000000',
    backgroundColor: '#EDF7ED',
    border: '1px solid #C7D4C7',
    borderRadius: '25px',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  error: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    color: '#D32F2F',
    margin: 0,
  },
  continueButton: {
    backgroundColor: '#BEE3BC',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '17px',
    fontWeight: 500,
    color: '#000000',
    border: 'none',
    borderRadius: '10px',
    padding: '10px 28px',
    cursor: 'pointer',
    marginTop: '8px',
  },
};

// Add placeholder styling via CSS
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  input::placeholder {
    color: #A1A1A1;
    font-family: "Roboto", sans-serif;
    font-size: 10px;
  }
`;
document.head.appendChild(styleSheet);
