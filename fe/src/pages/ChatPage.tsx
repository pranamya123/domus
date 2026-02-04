/**
 * Chat Page - Exact mockup specs
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Capacitor } from '@capacitor/core';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import ReactMarkdown from 'react-markdown';
import { useStore } from '../store/useStore';
import { useWebSocket } from '../hooks/useWebSocket';
import { useApi } from '../hooks/useApi';
import { AgentType, AgentStatus, Notification } from '../types';

const API_BASE = import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api` : 'http://localhost:8000/api';

// Agent detection keywords
const AGENT_KEYWORDS: Record<string, string[]> = {
  DFridge: ['fridge', 'refrigerator', 'food', 'groceries', 'ingredients', 'expired', 'expiring', 'milk', 'eggs', 'vegetables', 'fruits', 'meat', 'leftovers'],
  DCalendar: ['calendar', 'schedule', 'meeting', 'appointment', 'event', 'reminder', 'today', 'tomorrow', 'week'],
  DEnergy: ['energy', 'electricity', 'power', 'bill', 'usage', 'consumption', 'solar', 'thermostat', 'temperature'],
  DSecurity: ['security', 'camera', 'lock', 'door', 'alarm', 'motion', 'intruder'],
};

// Detect which agent should handle the message
function detectAgent(message: string): string | null {
  const lowerMessage = message.toLowerCase();
  for (const [agent, keywords] of Object.entries(AGENT_KEYWORDS)) {
    if (keywords.some(keyword => lowerMessage.includes(keyword))) {
      return agent;
    }
  }
  return null;
}

// Blink connection flow steps
type BlinkStep = 'none' | 'connect' | 'login' | '2fa' | 'success';

// Order card state
interface OrderCard {
  id: string;
  items: string[];
  status: 'pending' | 'approved' | 'ignored';
}

export function ChatPage() {
  const [inputValue, setInputValue] = useState('');
  const [activatingAgent, setActivatingAgent] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [blinkStep, setBlinkStep] = useState<BlinkStep>('none');
  const [blinkEmail, setBlinkEmail] = useState('');
  const [blinkPassword, setBlinkPassword] = useState('');
  const [blink2FA, setBlink2FA] = useState('');
  const [blinkError, setBlinkError] = useState('');
  const [blinkLoading, setBlinkLoading] = useState(false);
  const [showMediaPreview, setShowMediaPreview] = useState(false);
  const [mediaTimestamp, setMediaTimestamp] = useState(Date.now());
  const [orderCards, setOrderCards] = useState<OrderCard[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const user = useStore((state) => state.user);
  const messages = useStore((state) => state.messages);
  const agentStatus = useStore((state) => state.agentStatus);
  const addMessage = useStore((state) => state.addMessage);
  const capabilities = useStore((state) => state.capabilities);
  const notifications = useStore((state) => state.notifications);
  const unreadCount = useStore((state) => state.unreadCount);
  const notificationPanelOpen = useStore((state) => state.notificationPanelOpen);
  const setNotificationPanelOpen = useStore((state) => state.setNotificationPanelOpen);
  const addNotification = useStore((state) => state.addNotification);
  const pendingOrderCard = useStore((state) => state.pendingOrderCard);
  const setPendingOrderCard = useStore((state) => state.setPendingOrderCard);

  const { isConnected, sendMessage } = useWebSocket();
  const { blinkLogin, blinkVerify, token, fetchNotifications, resolveNotificationToChat } = useApi();

  // Handle pending order card from iOS notification tap (set by App.tsx)
  useEffect(() => {
    if (pendingOrderCard) {
      console.log('[ChatPage] Processing pending order card:', pendingOrderCard);
      setOrderCards(prev => [...prev, {
        id: pendingOrderCard.id,
        items: pendingOrderCard.items,
        status: 'pending',
      }]);
      // Clear the pending order card
      setPendingOrderCard(null);
    }
  }, [pendingOrderCard, setPendingOrderCard]);

  // Fetch notifications on mount
  useEffect(() => {
    if (token) {
      fetchNotifications().catch(console.error);
    }
  }, [token, fetchNotifications]);

  // Refresh media when Blink connects
  const refreshMedia = useCallback(() => {
    setMediaTimestamp(Date.now());
  }, []);

  const fridgeStatus = agentStatus[AgentType.FRIDGE];
  const isAgentActivating = fridgeStatus === AgentStatus.ACTIVATING || activatingAgent !== null;

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activatingAgent]);

  // Clear activating agent when a domus response arrives
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.sender === 'domus' && activatingAgent) {
      setActivatingAgent(null);
    }
  }, [messages, activatingAgent]);

  const handleSend = () => {
    if (!inputValue.trim() || isAgentActivating) return;

    const detectedAgent = detectAgent(inputValue);

    addMessage({
      id: `user-${Date.now()}`,
      content: inputValue,
      sender: 'user',
      timestamp: new Date().toISOString(),
      status: 'sending',
    });

    // Show agent activation status
    if (detectedAgent) {
      setActivatingAgent(detectedAgent);
    }

    sendMessage(inputValue);
    setInputValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // TODO: Replace with dynamic user name after real auth
  const userName = 'Priya';

  // Blink connection handlers
  const handleFridgeSenseClick = () => {
    setMenuOpen(false);
    if (!capabilities.blink_connected) {
      setBlinkStep('connect');
    } else {
      // Show media preview if already connected
      refreshMedia();
      setShowMediaPreview(true);
    }
  };

  const handleBlinkLogin = () => {
    setBlinkError('');
    setBlinkStep('login');
  };

  const handleBlinkSubmitCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!blinkEmail || !blinkPassword || blinkLoading) return;
    setBlinkLoading(true);
    setBlinkError('');
    try {
      const response = await blinkLogin(blinkEmail, blinkPassword);
      if (response.requires_2fa) {
        setBlinkStep('2fa');
      } else {
        setBlinkStep('success');
        // Auto-close success after 2 seconds
        setTimeout(() => {
          setBlinkStep('none');
          setBlinkEmail('');
          setBlinkPassword('');
          setBlink2FA('');
        }, 2000);
      }
    } catch (err) {
      setBlinkError(err instanceof Error ? err.message : 'Blink login failed');
    } finally {
      setBlinkLoading(false);
    }
  };

  const handleBlink2FASubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (blink2FA.length !== 6 || blinkLoading) return;
    setBlinkLoading(true);
    setBlinkError('');
    try {
      await blinkVerify(blink2FA);
      setBlinkStep('success');
      // Auto-close success after 2 seconds
      setTimeout(() => {
        setBlinkStep('none');
        setBlinkEmail('');
        setBlinkPassword('');
        setBlink2FA('');
      }, 2000);
    } catch (err) {
      setBlinkError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setBlinkLoading(false);
    }
  };

  const handleBlinkCancel = () => {
    setBlinkStep('none');
    setBlinkEmail('');
    setBlinkPassword('');
    setBlink2FA('');
    setBlinkError('');
    setBlinkLoading(false);
  };

  // Handle notification click - resolve to chat and insert seeded message
  const handleNotificationClick = async (notification: Notification) => {
    try {
      const result = await resolveNotificationToChat(notification.notification_id);

      // Insert the chat seed content as an assistant message
      addMessage({
        id: `notif-${notification.notification_id}`,
        content: result.chat_seed_content,
        sender: 'domus',
        timestamp: new Date().toISOString(),
        fromNotification: true,
      });

      // For proactive notifications with missing items, show order card
      if (notification.notification_type === 'proactive') {
        // Extract items from notification body (e.g., "missing: flour, sugar, vanilla")
        const bodyLower = notification.body.toLowerCase();
        const missingMatch = bodyLower.match(/missing[:\s]+([^.]+)/);
        if (missingMatch) {
          const items = missingMatch[1].split(',').map(s => s.trim()).filter(Boolean);
          if (items.length > 0) {
            setOrderCards(prev => [...prev, {
              id: notification.notification_id,
              items,
              status: 'pending',
            }]);
          }
        }
      }

      // Close the notification panel
      setNotificationPanelOpen(false);
    } catch (err) {
      console.error('Failed to resolve notification:', err);
    }
  };

  // Handle order card approve
  const handleOrderApprove = (cardId: string) => {
    setOrderCards(prev => prev.map(card =>
      card.id === cardId ? { ...card, status: 'approved' as const } : card
    ));
    // Mock Instacart order
    addMessage({
      id: `order-${cardId}`,
      content: 'Order placed with Instacart. Your items will arrive soon.',
      sender: 'domus',
      timestamp: new Date().toISOString(),
    });
    // Auto-remove after 3 seconds
    setTimeout(() => {
      setOrderCards(prev => prev.filter(card => card.id !== cardId));
    }, 3000);
  };

  // Handle order card ignore
  const handleOrderIgnore = (cardId: string) => {
    setOrderCards(prev => prev.filter(card => card.id !== cardId));
  };

  // Handle scan button - open camera
  const handleScanClick = async () => {
    try {
      if (!Capacitor.isNativePlatform()) {
        console.log('[Camera] Not on native platform, camera unavailable');
        return;
      }

      const image = await Camera.getPhoto({
        quality: 80,
        allowEditing: false,
        resultType: CameraResultType.Base64,
        source: CameraSource.Camera,
      });

      console.log('[Camera] Photo captured');
      // TODO: Send image to backend for fridge analysis
      // For now, just log that we got the image
      if (image.base64String) {
        addMessage({
          id: `scan-${Date.now()}`,
          content: 'Photo captured! Analyzing fridge contents...',
          sender: 'domus',
          timestamp: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.error('[Camera] Error:', err);
    }
  };

  return (
    <div style={styles.container}>
      {/* Sidebar Overlay */}
      {menuOpen && (
        <div style={styles.overlay} onClick={() => setMenuOpen(false)} />
      )}

      {/* Sidebar Menu */}
      <div style={{
        ...styles.sidebar,
        transform: menuOpen ? 'translateX(0)' : 'translateX(-100%)',
      }}>
        {/* SENSES Section */}
        <div style={styles.menuSection}>
          <span style={styles.menuSectionTitle}>SENSES</span>
          <div style={styles.menuItem} onClick={handleFridgeSenseClick}>
            <div style={styles.menuItemHeader}>
              <span style={styles.menuItemTitle}>Fridge Sense</span>
              <span style={{
                ...styles.menuItemStatus,
                color: capabilities.blink_connected ? '#077507' : '#D32F2F',
                textTransform: capabilities.blink_connected ? 'none' : 'uppercase',
                fontSize: capabilities.blink_connected ? '10px' : '9px',
              }}>
                {capabilities.blink_connected ? 'Connected' : 'NOT CONNECTED'}
              </span>
            </div>
            <span style={styles.menuItemDesc}>Provides visual data to the Fridge Agent</span>
          </div>
        </div>

        <div style={styles.menuDivider} />

        {/* SERVICES Section */}
        <div style={styles.menuSection}>
          <span style={styles.menuSectionTitle}>SERVICES</span>
          <div style={styles.menuItem}>
            <span style={styles.menuItemTitle}>Amazon Fresh</span>
            <span style={styles.menuItemDesc}>Provides visual data to the Fridge Agent</span>
          </div>
          <div style={styles.menuItem}>
            <span style={styles.menuItemTitle}>Google Calendar</span>
            <span style={styles.menuItemDesc}>Provides temporal context to the Schedule Agent</span>
          </div>
        </div>

        <div style={styles.menuDivider} />

        {/* ACCOUNT Section */}
        <div style={styles.menuSection}>
          <span style={styles.menuSectionTitle}>ACCOUNT</span>
          <button style={styles.menuButton}>Settings</button>
          <button style={styles.menuButton}>Sign out</button>
        </div>
      </div>

      {/* Blink Connection Modal - Step 1: Connect */}
      {blinkStep === 'connect' && (
        <div style={styles.modalOverlay}>
          <div style={styles.blinkModal}>
            <div style={styles.blinkModalHeader}>
              <button style={styles.blinkBackBtn} onClick={handleBlinkCancel}>
                <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
                  <path d="M7 1L1 7L7 13" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              <button style={styles.blinkCloseBtn} onClick={handleBlinkCancel}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M1 1L11 11M1 11L11 1" stroke="#000" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
            <h2 style={styles.blinkTitle}>Connect to Fridge Sense</h2>
            <p style={styles.blinkSubtitle}>Link your Blink camera to give Domus visual access to your fridge</p>
            <div style={styles.blinkButtons}>
              <button style={styles.blinkCancelBtn} onClick={handleBlinkCancel}>Cancel</button>
              <button style={styles.blinkPrimaryBtn} onClick={handleBlinkLogin}>Login with Blink</button>
            </div>
          </div>
        </div>
      )}

      {/* Blink Connection Modal - Step 2: Login */}
      {blinkStep === 'login' && (
        <div style={styles.modalOverlay}>
          <div style={styles.blinkModal}>
            <div style={styles.blinkModalHeader}>
              <button style={styles.blinkBackBtn} onClick={() => { setBlinkError(''); setBlinkStep('connect'); }}>
                <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
                  <path d="M7 1L1 7L7 13" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              <button style={styles.blinkCloseBtn} onClick={handleBlinkCancel}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M1 1L11 11M1 11L11 1" stroke="#000" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
            <h2 style={styles.blinkTitle}>Login to Blink</h2>
            <p style={styles.blinkSubtitle}>Enter your Blink account credentials</p>
            {blinkError && <p style={styles.blinkError}>{blinkError}</p>}
            <form onSubmit={handleBlinkSubmitCredentials} style={styles.blinkForm}>
              <input
                type="email"
                style={styles.blinkInput}
                placeholder="Email address"
                value={blinkEmail}
                onChange={(e) => setBlinkEmail(e.target.value)}
              />
              <input
                type="password"
                style={styles.blinkInput}
                placeholder="Password"
                value={blinkPassword}
                onChange={(e) => setBlinkPassword(e.target.value)}
              />
              <div style={styles.blinkButtons}>
                <button type="button" style={styles.blinkCancelBtn} onClick={handleBlinkCancel}>Cancel</button>
                <button
                  type="submit"
                  style={styles.blinkPrimaryBtn}
                  disabled={blinkLoading}
                >
                  {blinkLoading ? 'Connecting...' : 'Continue'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Blink Connection Modal - Step 3: 2FA */}
      {blinkStep === '2fa' && (
        <div style={styles.modalOverlay}>
          <div style={styles.blinkModal}>
            <div style={styles.blinkModalHeader}>
              <button style={styles.blinkBackBtn} onClick={() => { setBlinkError(''); setBlinkStep('login'); }}>
                <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
                  <path d="M7 1L1 7L7 13" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              <button style={styles.blinkCloseBtn} onClick={handleBlinkCancel}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M1 1L11 11M1 11L11 1" stroke="#000" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
            <h2 style={styles.blinkTitle}>Enter Verification Code</h2>
            <p style={styles.blinkSubtitle}>Enter the 6-digit code sent to your email</p>
            {blinkError && <p style={styles.blinkError}>{blinkError}</p>}
            <form onSubmit={handleBlink2FASubmit} style={styles.blinkForm}>
              <input
                type="text"
                style={styles.blinkInput}
                placeholder="000000"
                value={blink2FA}
                onChange={(e) => setBlink2FA(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
              />
              <div style={styles.blinkButtons}>
                <button type="button" style={styles.blinkCancelBtn} onClick={handleBlinkCancel}>Cancel</button>
                <button
                  type="submit"
                  style={styles.blinkPrimaryBtn}
                  disabled={blinkLoading}
                >
                  {blinkLoading ? 'Verifying...' : 'Verify'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Blink Connection Modal - Step 4: Success */}
      {blinkStep === 'success' && (
        <div style={styles.modalOverlay}>
          <div style={styles.blinkModal}>
            <div style={styles.successIcon}>
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="24" fill="#077507"/>
                <path d="M14 24L21 31L34 18" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <h2 style={styles.blinkTitle}>Connected!</h2>
            <p style={styles.blinkSubtitle}>Fridge Sense is now linked to your Domus account</p>
          </div>
        </div>
      )}

      {/* Header */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          {/* Hamburger menu */}
          <button style={styles.iconButton} onClick={() => setMenuOpen(true)}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M3 6H21M3 12H21M3 18H21" stroke="#000" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
          {/* d. logo */}
          <span style={styles.logo}>d.</span>
        </div>

        <span style={styles.greeting}>Hi, {userName}</span>

        <div style={styles.headerRight}>
          {/* Clock icon */}
          <button style={styles.iconButton}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 6v6l4 2"/>
            </svg>
          </button>
          {/* Bell icon with badge */}
          <button
            style={styles.iconButton}
            onClick={() => setNotificationPanelOpen(!notificationPanelOpen)}
          >
            <div style={{ position: 'relative' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
              </svg>
              {unreadCount > 0 && (
                <span style={styles.notificationBadge}>
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </div>
          </button>
        </div>
      </header>

      {/* Notification Panel */}
      {notificationPanelOpen && (
        <>
          <div
            style={styles.notificationOverlay}
            onClick={() => setNotificationPanelOpen(false)}
          />
          <div style={styles.notificationPanel}>
            <div style={styles.notificationHeader}>
              <span style={styles.notificationTitle}>Notifications</span>
              <button
                style={styles.notificationCloseBtn}
                onClick={() => setNotificationPanelOpen(false)}
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M1 1L11 11M1 11L11 1" stroke="#000" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
            <div style={styles.notificationList}>
              {notifications.length === 0 ? (
                <p style={styles.notificationEmpty}>No notifications</p>
              ) : (
                notifications.map((notification) => (
                  <div
                    key={notification.notification_id}
                    style={{
                      ...styles.notificationItem,
                      backgroundColor: notification.read_at ? '#FFFFFF' : '#F0FFF0',
                    }}
                    onClick={() => handleNotificationClick(notification)}
                  >
                    <div style={styles.notificationItemHeader}>
                      <span style={styles.notificationItemTitle}>{notification.title}</span>
                      {notification.notification_type === 'proactive' && (
                        <span style={styles.proactiveLabel}>Reminder</span>
                      )}
                    </div>
                    <p style={styles.notificationItemBody}>{notification.body}</p>
                    <span style={styles.notificationItemTime}>
                      {new Date(notification.sent_at).toLocaleString()}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}

      {/* Main content */}
      <div style={{
        ...styles.mainContent,
        justifyContent: messages.length === 0 ? 'center' : 'flex-end',
      }}>
        {messages.length === 0 ? (
          <div style={styles.emptyState}>
            <h1 style={styles.emptyTitle}>Ready to manage{'\n'}your home?</h1>
          </div>
        ) : (
          <div style={styles.messagesContainer}>
            {messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  ...styles.message,
                  ...(msg.sender === 'user' ? styles.userMessage : styles.domusMessage),
                }}
              >
                {msg.sender === 'domus' ? (
                  <div style={styles.markdownContainer}>
                    <ReactMarkdown
                      components={{
                        // Custom renderers for markdown elements
                        p: ({ children }) => <p style={styles.mdParagraph}>{children}</p>,
                        strong: ({ children }) => <strong style={styles.mdStrong}>{children}</strong>,
                        ul: ({ children }) => <ul style={styles.mdList}>{children}</ul>,
                        ol: ({ children }) => <ol style={styles.mdList}>{children}</ol>,
                        li: ({ children }) => <li style={styles.mdListItem}>{children}</li>,
                        h1: ({ children }) => <h1 style={styles.mdH1}>{children}</h1>,
                        h2: ({ children }) => <h2 style={styles.mdH2}>{children}</h2>,
                        h3: ({ children }) => <h3 style={styles.mdH3}>{children}</h3>,
                        code: ({ children }) => <code style={styles.mdCode}>{children}</code>,
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p style={styles.messageText}>{msg.content}</p>
                )}
              </div>
            ))}
            {activatingAgent && (
              <p style={styles.agentActivating}>Activating {activatingAgent} agent...</p>
            )}
            {/* Order Cards */}
            {orderCards.map((card) => (
              <div key={card.id} style={styles.orderCard}>
                {card.status === 'approved' ? (
                  <div style={styles.orderCardApproved}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" fill="#077507"/>
                      <path d="M8 12L11 15L16 9" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span style={styles.orderCardApprovedText}>Order placed</span>
                  </div>
                ) : (
                  <>
                    <p style={styles.orderCardText}>
                      Missing: <strong>{card.items.join(', ')}</strong>
                    </p>
                    <p style={styles.orderCardPrompt}>Order from Instacart?</p>
                    <div style={styles.orderCardButtons}>
                      <button
                        style={styles.orderCardIgnoreBtn}
                        onClick={() => handleOrderIgnore(card.id)}
                      >
                        Ignore
                      </button>
                      <button
                        style={styles.orderCardApproveBtn}
                        onClick={() => handleOrderApprove(card.id)}
                      >
                        Approve
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Bottom input card */}
      <div style={styles.bottomCard}>
        <div style={styles.inputRow}>
          <input
            type="text"
            style={styles.input}
            placeholder="Write your prompt here..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="placeholder-style"
          />
          <button style={styles.sendButton} onClick={handleSend} disabled={!inputValue.trim() || isAgentActivating}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A8A8A" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2L11 13"/>
              <path d="M22 2L15 22L11 13L2 9L22 2Z"/>
            </svg>
          </button>
        </div>
        <div style={styles.bottomRow}>
          {/* Scan icon - opens camera */}
          <button style={styles.scanButton} onClick={handleScanClick}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#A1A1A1" strokeWidth="2">
              <path d="M3 7V5a2 2 0 0 1 2-2h2"/>
              <path d="M17 3h2a2 2 0 0 1 2 2v2"/>
              <path d="M21 17v2a2 2 0 0 1-2 2h-2"/>
              <path d="M7 21H5a2 2 0 0 1-2-2v-2"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
            </svg>
          </button>
          {/* Speak button */}
          <button style={styles.speakButton}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000" strokeWidth="2">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
            <span style={styles.speakText}>Speak</span>
          </button>
        </div>
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
    flexDirection: 'column',
    position: 'fixed',
    top: 0,
    left: 0,
    overflow: 'hidden',
    boxSizing: 'border-box',
  },
  overlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: 'rgba(0, 0, 0, 0.3)',
    zIndex: 998,
  },
  sidebar: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '280px',
    height: '100vh',
    backgroundColor: '#FFFFFF',
    zIndex: 999,
    padding: '40px 24px',
    boxSizing: 'border-box',
    transition: 'transform 0.3s ease-in-out',
    overflowY: 'auto',
  },
  menuSection: {
    marginBottom: '24px',
  },
  menuSectionTitle: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '11px',
    fontWeight: 400,
    color: '#A1A1A1',
    letterSpacing: '2px',
    display: 'block',
    marginBottom: '16px',
  },
  menuItem: {
    marginBottom: '16px',
  },
  menuItemHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  menuItemTitle: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 400,
    color: '#000000',
    display: 'block',
  },
  menuItemStatus: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    fontWeight: 400,
    color: '#077507',
  },
  menuItemDesc: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    fontWeight: 400,
    color: '#A1A1A1',
    display: 'block',
    marginTop: '2px',
  },
  menuDivider: {
    height: '1px',
    backgroundColor: '#E8E8E8',
    margin: '24px 0',
  },
  menuButton: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 400,
    color: '#000000',
    background: 'none',
    border: 'none',
    padding: '8px 0',
    cursor: 'pointer',
    display: 'block',
    textAlign: 'left',
    width: '100%',
  },
  modalOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: 'rgba(232, 245, 233, 0.95)',
    zIndex: 1000,
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
  },
  blinkModal: {
    backgroundColor: '#FFFFFF',
    borderRadius: '10px',
    padding: '20px 24px 24px',
    width: '320px',
    boxShadow: '0 2px 10px rgba(0, 0, 0, 0.1)',
    position: 'relative',
  },
  blinkModalHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: '16px',
  },
  blinkBackBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: '4px',
    display: 'flex',
    alignItems: 'center',
  },
  blinkCloseBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: '4px',
    display: 'flex',
    alignItems: 'center',
  },
  blinkTitle: {
    fontFamily: '"Prata", serif',
    fontSize: '19px',
    fontWeight: 400,
    color: '#000000',
    textAlign: 'center',
    margin: '0 0 8px 0',
  },
  blinkSubtitle: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    fontWeight: 400,
    color: '#A1A1A1',
    textAlign: 'center',
    margin: '0 0 24px 0',
  },
  blinkError: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    fontWeight: 400,
    color: '#D32F2F',
    textAlign: 'center',
    margin: '-12px 0 16px 0',
  },
  blinkForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  blinkInput: {
    width: '100%',
    padding: '14px 20px',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '12px',
    fontWeight: 400,
    color: '#000000',
    backgroundColor: '#EDF7ED',
    border: '1px solid #C7D4C7',
    borderRadius: '25px',
    outline: 'none',
    boxSizing: 'border-box',
    textAlign: 'center',
  },
  blinkButtons: {
    display: 'flex',
    gap: '12px',
    marginTop: '12px',
  },
  blinkCancelBtn: {
    flex: 1,
    backgroundColor: '#9E9E9E',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 500,
    color: '#FFFFFF',
    border: 'none',
    borderRadius: '10px',
    padding: '12px 20px',
    cursor: 'pointer',
  },
  blinkPrimaryBtn: {
    flex: 1,
    backgroundColor: '#BEE3BC',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 500,
    color: '#000000',
    border: 'none',
    borderRadius: '10px',
    padding: '12px 20px',
    cursor: 'pointer',
  },
  successIcon: {
    display: 'flex',
    justifyContent: 'center',
    marginBottom: '16px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 16px',
    paddingTop: 'calc(env(safe-area-inset-top, 0px) + 8px)',
    flexShrink: 0,
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  logo: {
    fontFamily: '"Playfair Display", serif',
    fontSize: '32px',
    fontWeight: 800,
    color: '#077507',
    marginLeft: '1px',
  },
  greeting: {
    fontFamily: '"Prata", serif',
    fontSize: '19px',
    fontWeight: 300,
    color: '#5E5D5D',
  },
  headerRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  iconButton: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: 0,
    display: 'flex',
    alignItems: 'center',
  },
  mainContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    padding: '12px 16px',
    overflow: 'auto',
    minHeight: 0,
  },
  emptyState: {
    textAlign: 'center',
    marginBottom: '80px',
  },
  emptyTitle: {
    fontFamily: '"Prata", serif',
    fontSize: '42px',
    fontWeight: 400,
    color: '#000000',
    margin: 0,
    lineHeight: 1.2,
    whiteSpace: 'pre-line',
  },
  messagesContainer: {
    width: '100%',
    maxWidth: '400px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  message: {
    padding: '12px 16px',
    borderRadius: '16px',
    maxWidth: '80%',
  },
  userMessage: {
    alignSelf: 'flex-end',
    backgroundColor: '#FFFFFF',
  },
  domusMessage: {
    alignSelf: 'flex-start',
    backgroundColor: '#DAF7DA',
  },
  messageText: {
    margin: 0,
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    color: '#000000',
  },
  agentActivating: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 400,
    color: '#5E5D5D',
    margin: '8px 0',
    alignSelf: 'flex-start',
  },
  bottomCard: {
    width: 'calc(100% - 32px)',
    maxWidth: '340px',
    minHeight: '100px',
    backgroundColor: 'rgba(255, 255, 255, 0.7)',
    borderRadius: '10px',
    padding: '12px 16px',
    margin: '0 auto',
    marginBottom: 'calc(env(safe-area-inset-bottom, 0px) + 24px)',
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    flexShrink: 0,
    position: 'relative' as const,
    zIndex: 10,
  },
  inputRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    minHeight: '44px',
  },
  input: {
    flex: 1,
    border: 'none',
    outline: 'none',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '16px',
    color: '#000000',
    backgroundColor: 'transparent',
    WebkitAppearance: 'none' as const,
    padding: '8px 0',
    minHeight: '24px',
  },
  sendButton: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: 0,
    marginRight: '4px',
    display: 'flex',
    alignItems: 'center',
  },
  bottomRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  scanButton: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: 0,
    display: 'flex',
    alignItems: 'center',
  },
  speakButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    backgroundColor: '#FCFCFC',
    border: '1px solid #E3E3E3',
    borderRadius: '10px',
    padding: '8px 12px',
    cursor: 'pointer',
  },
  speakText: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '12px',
    fontWeight: 400,
    color: '#000000',
  },
  // Notification styles
  notificationBadge: {
    position: 'absolute' as const,
    top: '-6px',
    right: '-6px',
    backgroundColor: '#D32F2F',
    color: '#FFFFFF',
    borderRadius: '10px',
    padding: '1px 5px',
    fontSize: '10px',
    fontWeight: 600,
    fontFamily: '"Roboto", sans-serif',
    minWidth: '14px',
    textAlign: 'center' as const,
  },
  notificationOverlay: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    zIndex: 900,
  },
  notificationPanel: {
    position: 'fixed' as const,
    top: '60px',
    right: '16px',
    width: '320px',
    maxHeight: '70vh',
    backgroundColor: '#FFFFFF',
    borderRadius: '10px',
    boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)',
    zIndex: 901,
    display: 'flex',
    flexDirection: 'column' as const,
    overflow: 'hidden',
  },
  notificationHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px',
    borderBottom: '1px solid #E8E8E8',
  },
  notificationTitle: {
    fontFamily: '"Prata", serif',
    fontSize: '16px',
    fontWeight: 400,
    color: '#000000',
  },
  notificationCloseBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: '4px',
    display: 'flex',
    alignItems: 'center',
  },
  notificationList: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: '8px',
  },
  notificationEmpty: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    color: '#A1A1A1',
    textAlign: 'center' as const,
    padding: '24px',
  },
  notificationItem: {
    padding: '12px',
    borderRadius: '8px',
    marginBottom: '8px',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
    border: '1px solid #E8E8E8',
  },
  notificationItemHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '4px',
  },
  notificationItemTitle: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 500,
    color: '#000000',
  },
  proactiveLabel: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    fontWeight: 400,
    color: '#077507',
    backgroundColor: '#E8F5E9',
    padding: '2px 6px',
    borderRadius: '4px',
  },
  notificationItemBody: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '12px',
    color: '#5E5D5D',
    margin: '0 0 8px 0',
    lineHeight: 1.4,
  },
  notificationItemTime: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '10px',
    color: '#A1A1A1',
  },
  // Order Card styles
  orderCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: '12px',
    padding: '16px',
    marginTop: '12px',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
    border: '1px solid #E8F5E9',
    width: '100%',
    maxWidth: '300px',
    alignSelf: 'flex-start',
  },
  orderCardText: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    color: '#333',
    margin: '0 0 8px 0',
  },
  orderCardPrompt: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '13px',
    color: '#666',
    margin: '0 0 12px 0',
  },
  orderCardButtons: {
    display: 'flex',
    gap: '10px',
  },
  orderCardIgnoreBtn: {
    flex: 1,
    padding: '10px 16px',
    backgroundColor: '#F5F5F5',
    border: '1px solid #E0E0E0',
    borderRadius: '8px',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '13px',
    fontWeight: 500,
    color: '#666',
    cursor: 'pointer',
  },
  orderCardApproveBtn: {
    flex: 1,
    padding: '10px 16px',
    backgroundColor: '#077507',
    border: 'none',
    borderRadius: '8px',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '13px',
    fontWeight: 500,
    color: '#FFFFFF',
    cursor: 'pointer',
  },
  orderCardApproved: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    padding: '8px 0',
  },
  orderCardApprovedText: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 500,
    color: '#077507',
  },
  // Markdown styles for assistant messages
  markdownContainer: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    color: '#000000',
    lineHeight: 1.5,
  },
  mdParagraph: {
    margin: '0 0 8px 0',
    lineHeight: 1.5,
  },
  mdStrong: {
    fontWeight: 600,
    color: '#077507',
  },
  mdList: {
    margin: '4px 0 8px 0',
    paddingLeft: '20px',
  },
  mdListItem: {
    margin: '4px 0',
    lineHeight: 1.4,
  },
  mdH1: {
    fontSize: '18px',
    fontWeight: 600,
    margin: '0 0 8px 0',
    color: '#000000',
  },
  mdH2: {
    fontSize: '16px',
    fontWeight: 600,
    margin: '12px 0 6px 0',
    color: '#333333',
  },
  mdH3: {
    fontSize: '14px',
    fontWeight: 600,
    margin: '10px 0 4px 0',
    color: '#333333',
  },
  mdCode: {
    backgroundColor: '#f0f0f0',
    padding: '2px 6px',
    borderRadius: '4px',
    fontFamily: 'monospace',
    fontSize: '13px',
  },
};
