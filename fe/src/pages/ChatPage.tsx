/**
 * Chat Page - Exact mockup specs
 */

import { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react';
import { Capacitor } from '@capacitor/core';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import ReactMarkdown from 'react-markdown';
import { useStore } from '../store/useStore';
import { useWebSocket } from '../hooks/useWebSocket';
import { useApi } from '../hooks/useApi';
import { AgentType, AgentStatus, Notification } from '../types';
import { FridgeResponseCard } from '../components/FridgeResponseCard';
import { parseFridgeResponse, isFridgeResponse } from '../utils/parseFridgeResponse';

const API_BASE = import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api` : 'http://localhost:8000/api';

// Agent detection keywords
const AGENT_KEYWORDS: Record<string, string[]> = {
  DFridge: ['fridge', 'refrigerator', 'food', 'groceries', 'ingredients', 'expired', 'expiring', 'milk', 'eggs', 'vegetables', 'fruits', 'meat', 'leftovers', 'eat', 'meal', 'cheap', 'budget', 'cook', 'dinner', 'lunch', 'breakfast'],
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

// Action card state - supports both bake sale (Instacart) and in-store assist
type CardType = 'bake_sale' | 'in_store_assist';
interface ActionCard {
  id: string;
  type: CardType;
  items: string[];
  status: 'pending' | 'approved' | 'picked_up' | 'ignored';
  storeName?: string;
}

// Shopping context for conversational continuity (ephemeral, task-scoped)
interface ShoppingContext {
  storeName: string;
  item: string;
  section: string;  // e.g., "dairy section near the back"
  timestamp: number;
}

// Item to store section mapping (for contextual responses)
const ITEM_SECTIONS: Record<string, string> = {
  milk: 'dairy section near the back',
  eggs: 'dairy section',
  butter: 'dairy section',
  cheese: 'dairy section',
  yogurt: 'dairy section',
  bread: 'bakery section',
  produce: 'produce section',
  vegetables: 'produce section',
  fruits: 'produce section',
  meat: 'meat section',
  chicken: 'meat section',
  fish: 'seafood section',
};

export function ChatPage() {
  const [inputValue, setInputValue] = useState('');
  const [activatingAgent, setActivatingAgent] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [blinkStep, setBlinkStep] = useState<BlinkStep>('none');
  const [blinkEmail, setBlinkEmail] = useState('');
  const [blinkPassword, setBlinkPassword] = useState('');
  const [blink2FA, setBlink2FA] = useState('');
  const [blinkError, setBlinkError] = useState('');
  const [blinkLoading, setBlinkLoading] = useState(false);
  const [showMediaPreview, setShowMediaPreview] = useState(false);
  const [mediaTimestamp, setMediaTimestamp] = useState(Date.now());
  const [actionCards, setActionCards] = useState<ActionCard[]>([]);
  const [shoppingContext, setShoppingContext] = useState<ShoppingContext | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mainContentRef = useRef<HTMLDivElement>(null);

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

  // Add initial greeting message from Domus on first load
  // BUT skip if user entered from notification tap (pendingOrderCard is set)
  const [hasGreeted, setHasGreeted] = useState(false);
  useEffect(() => {
    // Don't show greeting if entered from notification (pendingOrderCard exists)
    if (pendingOrderCard) {
      setHasGreeted(true);  // Mark as greeted to prevent future greeting
      return;
    }
    if (!hasGreeted && messages.length === 0) {
      setHasGreeted(true);
      // Add greeting immediately
      addMessage({
        id: 'greeting-initial',
        content: "Hello! I'm Domus, your home assistant. I can help you manage your fridge, schedule, and more. What would you like to do today?",
        sender: 'domus',
        timestamp: new Date().toISOString(),
      });
    }
  }, [hasGreeted, messages.length, addMessage, pendingOrderCard]);

  // Handle pending order card from iOS notification tap (set by App.tsx)
  useEffect(() => {
    if (pendingOrderCard) {
      console.log('[ChatPage] Processing pending order card:', pendingOrderCard);
      setActionCards(prev => [...prev, {
        id: pendingOrderCard.id,
        type: 'bake_sale',  // Default to bake sale for iOS notification tap
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

  // Scroll to bottom when new messages arrive — useLayoutEffect runs before
  // the browser paints, so the user never sees a frame of shifted content.
  useLayoutEffect(() => {
    const el = mainContentRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, activatingAgent]);

  // Clear activating agent and thinking state when a domus response arrives
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.sender === 'domus') {
      if (activatingAgent) setActivatingAgent(null);
      if (isThinking) setIsThinking(false);
    }
  }, [messages, activatingAgent, isThinking]);

  const handleSend = () => {
    if (!inputValue.trim() || isAgentActivating || isThinking) return;

    const userInput = inputValue.trim();
    const inputLower = userInput.toLowerCase();

    // Check if user is responding to an action card
    const affirmatives = ['yes', 'yes!', 'yeah', 'yep', 'sure', 'yes sure', 'yes sure!', 'ok', 'okay', 'please', 'do it', 'go ahead', 'add it', 'add to list'];
    const negatives = ['no', 'no thanks', 'nope', 'not now', 'later', 'skip', 'ignore', 'nevermind', 'never mind'];
    const pickedUp = ['picked up', 'got it', 'already got it', 'i got it', 'grabbed it'];

    const isAffirmative = affirmatives.includes(inputLower) || inputLower.startsWith('yes');
    const isNegative = negatives.includes(inputLower) || inputLower.startsWith('no ');
    const isPickedUp = pickedUp.some(p => inputLower.includes(p));

    // Find pending action card (in-store assist or bake sale)
    const pendingCard = actionCards.find(c => c.status === 'pending');

    if (pendingCard && (isAffirmative || isNegative || isPickedUp)) {
      // Handle response to action card locally (don't send to orchestrator)
      addMessage({
        id: `user-${Date.now()}`,
        content: userInput,
        sender: 'user',
        timestamp: new Date().toISOString(),
      });

      if (isNegative) {
        // User declined - dismiss card with friendly acknowledgment
        handleCardIgnore(pendingCard.id);
        setShoppingContext(null);  // Clear shopping context
        addMessage({
          id: `dismiss-${pendingCard.id}`,
          content: "No problem!",
          sender: 'domus',
          timestamp: new Date().toISOString(),
        });
      } else if (isPickedUp && pendingCard.type === 'in_store_assist') {
        // User said they picked it up
        handlePickedUp(pendingCard.id, pendingCard.items[0]);
      } else if (isAffirmative) {
        if (pendingCard.type === 'in_store_assist') {
          handleAddToList(pendingCard.id, pendingCard.items[0]);
        } else if (pendingCard.type === 'bake_sale') {
          handleBakeSaleApprove(pendingCard.id);
        }
      }

      setInputValue('');
      return;
    }

    // Handle follow-up questions within shopping context (ephemeral, task-scoped)
    // Context expires after 10 minutes or when user leaves the store flow
    const contextActive = shoppingContext && (Date.now() - shoppingContext.timestamp < 10 * 60 * 1000);

    if (contextActive) {
      // Detect shopping context follow-ups
      const anythingElse = ['anything else', 'what else', 'something else', 'other items', 'low on'];
      const whereExactly = ['where exactly', 'where is', 'which aisle', 'find it', 'where can i find'];
      const alreadyGotIt = ['already picked', 'already got', 'i got it', 'picked it up', 'grabbed it'];
      const thanksDone = ['thanks', 'thank you', 'thats all', "that's all", 'done', 'all good', 'all set'];

      const isAnythingElse = anythingElse.some(p => inputLower.includes(p));
      const isWhereExactly = whereExactly.some(p => inputLower.includes(p));
      const isAlreadyGotIt = alreadyGotIt.some(p => inputLower.includes(p));
      const isThanksDone = thanksDone.some(p => inputLower.includes(p));

      if (isAnythingElse || isWhereExactly || isAlreadyGotIt || isThanksDone) {
        // Handle locally without orchestrator reset
        addMessage({
          id: `user-${Date.now()}`,
          content: userInput,
          sender: 'user',
          timestamp: new Date().toISOString(),
        });

        let response = '';
        if (isWhereExactly) {
          response = `${shoppingContext.item.charAt(0).toUpperCase() + shoppingContext.item.slice(1)} should be in the ${shoppingContext.section} at ${shoppingContext.storeName}.`;
        } else if (isAlreadyGotIt) {
          response = `Got it — ${shoppingContext.item} checked off. Let me know if there's anything else.`;
          setShoppingContext(null);  // Clear context
        } else if (isAnythingElse) {
          response = `Based on what I can see, you're good on most staples. I'll let you know if something else comes up.`;
        } else if (isThanksDone) {
          response = `Happy shopping!`;
          setShoppingContext(null);  // Clear context
        }

        addMessage({
          id: `followup-${Date.now()}`,
          content: response,
          sender: 'domus',
          timestamp: new Date().toISOString(),
        });

        setInputValue('');
        return;
      }
    }

    // Normal message flow
    const detectedAgent = detectAgent(userInput);

    addMessage({
      id: `user-${Date.now()}`,
      content: userInput,
      sender: 'user',
      timestamp: new Date().toISOString(),
      status: 'sending',
    });

    // Show thinking indicator
    setIsThinking(true);

    // Show agent activation status if specific agent detected
    if (detectedAgent) {
      setActivatingAgent(detectedAgent);
    }

    sendMessage(userInput);
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

      // For proactive notifications, show appropriate action card
      if (notification.notification_type === 'proactive') {
        const titleLower = notification.title.toLowerCase();
        const bodyLower = notification.body.toLowerCase();

        // Detect in-store assist (grocery) notification
        if (titleLower.includes("noticed you're at")) {
          // Extract item from body (e.g., "You're out of milk" or "Running low on eggs")
          const outMatch = bodyLower.match(/out of (\w+)/);
          const lowMatch = bodyLower.match(/low on (\w+)/);
          const item = outMatch?.[1] || lowMatch?.[1];

          if (item) {
            // Extract store name from title (e.g., "Noticed you're at Whole Foods")
            const storeMatch = notification.title.match(/at (.+)$/);
            const storeName = storeMatch?.[1] || 'the store';

            setActionCards(prev => [...prev, {
              id: notification.notification_id,
              type: 'in_store_assist',
              items: [item],
              status: 'pending',
              storeName,
            }]);
          }
        }
        // Detect bake sale notification (missing: item1, item2)
        else {
          const missingMatch = bodyLower.match(/missing[:\s]+([^.]+)/);
          if (missingMatch) {
            const items = missingMatch[1].split(',').map(s => s.trim()).filter(Boolean);
            if (items.length > 0) {
              setActionCards(prev => [...prev, {
                id: notification.notification_id,
                type: 'bake_sale',
                items,
                status: 'pending',
              }]);
            }
          }
        }
      }

      // Close the notification panel
      setNotificationPanelOpen(false);
    } catch (err) {
      console.error('Failed to resolve notification:', err);
    }
  };

  // Handle bake sale card approve (Instacart order)
  const handleBakeSaleApprove = (cardId: string) => {
    setActionCards(prev => prev.map(card =>
      card.id === cardId ? { ...card, status: 'approved' as const } : card
    ));
    addMessage({
      id: `order-${cardId}`,
      content: 'Order placed with Instacart. Your items will arrive soon.',
      sender: 'domus',
      timestamp: new Date().toISOString(),
    });
    setTimeout(() => {
      setActionCards(prev => prev.filter(card => card.id !== cardId));
    }, 3000);
  };

  // Handle in-store assist "Picked Up" action
  const handlePickedUp = (cardId: string, item: string) => {
    const card = actionCards.find(c => c.id === cardId);
    const storeName = card?.storeName || 'the store';

    setActionCards(prev => prev.map(c =>
      c.id === cardId ? { ...c, status: 'picked_up' as const } : c
    ));

    // Set shopping context for follow-up questions
    const section = ITEM_SECTIONS[item.toLowerCase()] || 'the store';
    setShoppingContext({
      storeName,
      item,
      section,
      timestamp: Date.now(),
    });

    // Contextual confirmation
    addMessage({
      id: `picked-${cardId}`,
      content: `Got it — ${item} checked off. Let me know if there's anything else while you're here.`,
      sender: 'domus',
      timestamp: new Date().toISOString(),
    });

    setTimeout(() => {
      setActionCards(prev => prev.filter(c => c.id !== cardId));
    }, 2000);
  };

  // Handle in-store assist "Add to List" action
  const handleAddToList = (cardId: string, item: string) => {
    const card = actionCards.find(c => c.id === cardId);
    const storeName = card?.storeName || 'the store';

    setActionCards(prev => prev.map(c =>
      c.id === cardId ? { ...c, status: 'approved' as const } : c
    ));

    // Get store section for item
    const section = ITEM_SECTIONS[item.toLowerCase()] || 'the store';

    // Set shopping context for follow-up questions
    setShoppingContext({
      storeName,
      item,
      section,
      timestamp: Date.now(),
    });

    // Contextual confirmation with helpful follow-up
    const capitalizedItem = item.charAt(0).toUpperCase() + item.slice(1);
    addMessage({
      id: `list-${cardId}`,
      content: `Done. ${capitalizedItem}'s usually in the ${section} — I can help you find it, or check if there's anything else you're low on while you're here.`,
      sender: 'domus',
      timestamp: new Date().toISOString(),
    });

    setTimeout(() => {
      setActionCards(prev => prev.filter(c => c.id !== cardId));
    }, 2000);
  };

  // Handle card ignore/dismiss
  const handleCardIgnore = (cardId: string) => {
    setActionCards(prev => prev.filter(card => card.id !== cardId));
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
                color: capabilities.blink_connected ? '#034F03' : '#D32F2F',
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
                <circle cx="24" cy="24" r="24" fill="#034F03"/>
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
      <div ref={mainContentRef} style={styles.mainContent}>
        <div style={styles.messagesContainer}>
            {messages.map((msg) => {
              const isDomus = msg.sender === 'domus';
              const fridgeData = isDomus ? parseFridgeResponse(msg.content) : null;
              const isFridgeCard = !!fridgeData;

              // User messages (right-aligned, no avatar)
              if (!isDomus) {
                return (
                  <div key={msg.id} style={styles.userMessageWrapper}>
                    <div style={styles.userMessage}>
                      <p style={styles.messageText}>{msg.content}</p>
                    </div>
                  </div>
                );
              }

              // Domus messages (left-aligned with avatar)
              return (
                <div key={msg.id} style={styles.domusMessageWrapper}>
                  {/* Avatar on the left */}
                  <div style={styles.domusAvatar}>
                    <span style={styles.domusAvatarText}>d.</span>
                  </div>

                  {/* Content column */}
                  <div style={styles.domusContentCol}>
                    {/* Message content */}
                    <div style={isFridgeCard ? styles.domusFridgeMessage : styles.domusMessage}>
                      {isFridgeCard ? (
                        <FridgeResponseCard data={fridgeData} />
                      ) : (
                        <div style={styles.markdownContainer}>
                          <ReactMarkdown
                            components={{
                              p: ({ children }) => <p style={styles.mdParagraph}>{children}</p>,
                              strong: ({ children }) => <strong style={styles.mdStrong}>{children}</strong>,
                              em: ({ children }) => <em style={styles.mdEmphasis}>{children}</em>,
                              ul: ({ children }) => <ul style={styles.mdList}>{children}</ul>,
                              ol: ({ children }) => <ol style={styles.mdOrderedList}>{children}</ol>,
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
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            {/* Thinking indicator */}
            {isThinking && (
              <div style={styles.thinkingContainer}>
                <div style={styles.thinkingDots}>
                  <span className="thinking-dot">●</span>
                  <span className="thinking-dot">●</span>
                  <span className="thinking-dot">●</span>
                </div>
                <span style={styles.thinkingText}>
                  {activatingAgent ? `Activating ${activatingAgent} agent...` : 'Thinking...'}
                </span>
              </div>
            )}
            {/* Action Cards - Bake Sale (Instacart) or In-Store Assist */}
            {actionCards.map((card) => (
              <div key={card.id} style={styles.orderCard}>
                {/* Success states */}
                {card.status === 'approved' && card.type === 'bake_sale' && (
                  <div style={styles.orderCardApproved}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" fill="#034F03"/>
                      <path d="M8 12L11 15L16 9" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span style={styles.orderCardApprovedText}>Order placed</span>
                  </div>
                )}
                {card.status === 'picked_up' && (
                  <div style={styles.orderCardApproved}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" fill="#034F03"/>
                      <path d="M8 12L11 15L16 9" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span style={styles.orderCardApprovedText}>Picked up</span>
                  </div>
                )}
                {card.status === 'approved' && card.type === 'in_store_assist' && (
                  <div style={styles.orderCardApproved}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" fill="#034F03"/>
                      <path d="M8 12L11 15L16 9" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span style={styles.orderCardApprovedText}>Added to list</span>
                  </div>
                )}

                {/* Pending states */}
                {card.status === 'pending' && card.type === 'bake_sale' && (
                  <>
                    <p style={styles.orderCardText}>
                      Missing: <strong>{card.items.join(', ')}</strong>
                    </p>
                    <p style={styles.orderCardPrompt}>Order from Instacart?</p>
                    <div style={styles.orderCardButtons}>
                      <button
                        style={styles.orderCardIgnoreBtn}
                        onClick={() => handleCardIgnore(card.id)}
                      >
                        Ignore
                      </button>
                      <button
                        style={styles.orderCardApproveBtn}
                        onClick={() => handleBakeSaleApprove(card.id)}
                      >
                        Approve
                      </button>
                    </div>
                  </>
                )}

                {/* In-Store Assist Card */}
                {card.status === 'pending' && card.type === 'in_store_assist' && (
                  <>
                    <p style={styles.orderCardText}>
                      <strong>{card.items[0]}</strong>
                    </p>
                    <div style={styles.orderCardButtons}>
                      <button
                        style={styles.orderCardIgnoreBtn}
                        onClick={() => handleAddToList(card.id, card.items[0])}
                      >
                        Add to List
                      </button>
                      <button
                        style={styles.orderCardApproveBtn}
                        onClick={() => handlePickedUp(card.id, card.items[0])}
                      >
                        Picked Up
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
      </div>

      {/* Bottom input card - pill shaped */}
      <div style={styles.inputPill}>
        {/* Microphone icon */}
        <button style={styles.micButton}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#034F03" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="23"/>
            <line x1="8" y1="23" x2="16" y2="23"/>
          </svg>
        </button>

        {/* Input field */}
        <input
          type="text"
          style={styles.pillInput}
          placeholder="Type your message..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        {/* Send button - dark green circle with send arrow */}
        <button
          style={{
            ...styles.sendButtonCircle,
            opacity: inputValue.trim() && !isAgentActivating ? 1 : 0.6,
          }}
          onClick={handleSend}
          disabled={!inputValue.trim() || isAgentActivating}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="#FFFFFF">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    height: '100vh',
    width: '100vw',
    backgroundColor: '#F8FAF8',
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
    color: '#034F03',
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
    backgroundColor: '#EBF0EB',
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
    color: '#034F03',
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
    alignItems: 'stretch',
    padding: '12px 16px',
    overflow: 'auto',
    minHeight: 0,
  },
  messagesContainer: {
    width: '100%',
    maxWidth: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    paddingRight: '8px',
    marginTop: 'auto',
  },
  // User message (right-aligned)
  userMessageWrapper: {
    display: 'flex',
    justifyContent: 'flex-end',
    width: '100%',
  },
  userMessage: {
    backgroundColor: '#FFFFFF',
    borderRadius: '16px',
    padding: '12px 16px',
    maxWidth: '75%',
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
  },
  // Domus message (left-aligned with avatar)
  domusMessageWrapper: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    width: '100%',
  },
  domusAvatar: {
    width: '32px',
    height: '32px',
    borderRadius: '50%',
    backgroundColor: '#E8F5E9',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    marginTop: '2px',
  },
  domusAvatarText: {
    fontFamily: '"Playfair Display", serif',
    fontSize: '16px',
    fontWeight: 700,
    color: '#034F03',
  },
  domusContentCol: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    flex: 1,
    minWidth: 0,
  },
  domusHeaderBubble: {
    backgroundColor: '#FFFFFF',
    borderRadius: '18px',
    padding: '8px 14px',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
    alignSelf: 'flex-start',
  },
  domusHeaderText: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '14px',
    fontWeight: 400,
    color: '#1a1a1a',
  },
  domusHeaderEmoji: {
    fontSize: '14px',
  },
  domusMessage: {
    backgroundColor: '#DAF7DA',
    borderRadius: '16px',
    padding: '14px 18px',
    maxWidth: '100%',
  },
  domusFridgeMessage: {
    alignSelf: 'flex-start',
    backgroundColor: 'transparent',
    padding: 0,
    maxWidth: '100%',
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
  // Thinking indicator styles
  thinkingContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '12px 16px',
    backgroundColor: '#DAF7DA',
    borderRadius: '16px',
    alignSelf: 'flex-start',
    maxWidth: '80%',
  },
  thinkingDots: {
    display: 'flex',
    gap: '3px',
  },
  thinkingText: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '14px',
    fontWeight: 400,
    color: '#5E5D5D',
    fontStyle: 'italic',
  },
  // New pill-shaped input styles
  inputPill: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    backgroundColor: '#FFFFFF',
    borderRadius: '50px',
    padding: '8px 8px 8px 16px',
    margin: '0 20px',
    marginBottom: 'calc(env(safe-area-inset-bottom, 0px) + 24px)',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)',
    flexShrink: 0,
    position: 'relative' as const,
    zIndex: 10,
  },
  micButton: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    padding: '4px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  pillInput: {
    flex: 1,
    border: 'none',
    outline: 'none',
    fontFamily: '"Roboto", sans-serif',
    fontSize: '17px',
    color: '#000000',
    backgroundColor: 'transparent',
    WebkitAppearance: 'none' as const,
    padding: '8px 0',
    minHeight: '24px',
  },
  sendButtonCircle: {
    width: '42px',
    height: '42px',
    borderRadius: '50%',
    backgroundColor: '#034F03',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    transition: 'opacity 0.2s',
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
    color: '#034F03',
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
    marginLeft: '42px',  // Align with chat bubble (avatar 32px + gap 10px)
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
    border: '1px solid #E8F5E9',
    width: 'calc(100% - 42px)',
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
    backgroundColor: '#034F03',
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
    color: '#034F03',
  },
  // Markdown styles for assistant messages - clean, readable typography
  markdownContainer: {
    fontFamily: '"Roboto", sans-serif',
    fontSize: '15px',
    color: '#1a1a1a',
    lineHeight: 1.6,
    letterSpacing: '-0.01em',
  },
  mdParagraph: {
    margin: '0 0 12px 0',
    lineHeight: 1.6,
  },
  mdStrong: {
    fontWeight: 600,
    color: '#1a1a1a',
  },
  mdList: {
    margin: '10px 0 14px 0',
    paddingLeft: '20px',
    listStyleType: 'disc',
  },
  mdOrderedList: {
    margin: '10px 0 14px 0',
    paddingLeft: '22px',
    listStyleType: 'decimal',
  },
  mdListItem: {
    margin: '8px 0',
    lineHeight: 1.55,
    paddingLeft: '6px',
  },
  mdH1: {
    fontSize: '17px',
    fontWeight: 600,
    margin: '0 0 10px 0',
    color: '#1a1a1a',
    letterSpacing: '-0.02em',
  },
  mdH2: {
    fontSize: '16px',
    fontWeight: 600,
    margin: '18px 0 10px 0',
    color: '#1a1a1a',
    letterSpacing: '-0.01em',
  },
  mdH3: {
    fontSize: '15px',
    fontWeight: 600,
    margin: '16px 0 8px 0',
    color: '#333333',
  },
  mdCode: {
    backgroundColor: '#f5f5f5',
    padding: '3px 8px',
    borderRadius: '6px',
    fontFamily: 'monospace',
    fontSize: '13px',
  },
  mdEmphasis: {
    fontStyle: 'italic',
    color: '#555555',
  },
};
