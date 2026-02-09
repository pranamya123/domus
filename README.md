# Domus — Multi-Agent Smart Home Assistant

An intelligent home assistant powered by Google Gemini, with specialized agents for fridge inventory (vision AI), calendar awareness, grocery shopping, and proactive notifications. Built with FastAPI + React, deployable as an iOS app via Capacitor.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     React + Capacitor (iOS)                      │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐   │
│  │   Chat   │  │  Fridge   │  │ Notif     │  │  Geofence    │   │
│  │ Interface│  │   Card    │  │ Panel     │  │  (Location)  │   │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────┘   │
└───────────────────────┬──────────────────────────────────────────┘
                        │ WebSocket + REST
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │            Level 0: Domus Orchestrator                      │  │
│  │  • Intent detection (context-aware)                        │  │
│  │  • Conversation state & multi-turn flows                   │  │
│  │  • Short reply expansion ("yes" → full context)            │  │
│  │  • Agent routing & response synthesis                      │  │
│  └──────────────┬─────────────────────────────────────────────┘  │
│                 │                                                 │
│  ┌──────────────▼─────────────────────────────────────────────┐  │
│  │                    Level 1: Agents                          │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐                │  │
│  │  │ DFridge  │  │DCalendar │  │DInstacart │                │  │
│  │  │ (Vision) │  │ (Events) │  │ (Cart)    │                │  │
│  │  └──────────┘  └──────────┘  └───────────┘                │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                      Services                              │  │
│  │  Blink Camera │ Gemini LLM │ Push (FCM) │ Location/Geo   │  │
│  │  Calendar     │ Grocery    │ Bake Sale  │ Redis Storage   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Design Principles

- **Business logic in code, judgment in Gemini.** The orchestrator manages state, lifecycle, and routing. All language generation, reasoning, and world knowledge come from the LLM.
- **Contract-first types.** Shared Pydantic/TypeScript schemas in `shared/` are the single source of truth for events, state, and storage interfaces.
- **Progressive disclosure.** Fridge responses lead with a judgment ("You're set for stir-fry tonight"), then reveal inventory and meals on demand.
- **Ephemeral context windows.** Shopping context lives for 10 minutes, enabling natural follow-ups without permanent state bloat.

## Features

### Fridge Agent (DFridge)
- **Gemini Vision analysis** of Blink camera thumbnails — identifies items, quantities, freshness
- Persistent vision chat sessions per user (upload once, ask many questions)
- Judgment-first responses: meal readiness assessment before inventory lists
- Structured output: `### MEALS` with title, time, servings, image_prompt for card rendering
- Budget meal planning with cost estimates
- Mid-shopping fridge checks (model-driven routing, not keywords)

### Calendar Agent (DCalendar)
- Time-aware meal recommendations based on today's schedule
- Workout detection for post-exercise nutrition suggestions
- Prep-required event detection (bake sales, dinner parties, potlucks)

### Instacart Agent (DInstacart)
- Shopping cart management with mock product catalog
- Cross-references fridge contents to suggest what's missing
- Activity-based recommendations (workout supplements, meal prep items)

### Proactive Notifications

**Grocery Store Notifications:**
- Geofence detection when user enters a grocery store
- Judgment-driven nudge: "You've been out of milk for a few days — and you're at Whole Foods, which makes this a good moment to grab it."
- 10-minute shopping context for natural follow-ups via Gemini
- 24-hour cooldown per store per item

**Bake Sale / Event Prep Notifications:**
- Calendar scan for prep-required events
- Fridge inventory vs. required items comparison
- Push notification with deep link to chat

### Multi-Turn Conversations
- Context-aware intent detection across conversation turns
- Short reply expansion: "yes" becomes "Yes, please show me the budget meal options"
- Interaction phases: INITIAL → OFFERED_OPTIONS → EXPANDING_OPTIONS → FOLLOW_UP
- Shopping context: all messages within 10-min window routed through Gemini with store/item context

## Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **FastAPI** | Async web framework (REST + WebSocket) |
| **Google Gemini** (`gemini-3-flash-preview`) | Text generation + multimodal vision |
| **Redis** (with hiredis) | Session storage, event streams, pub/sub, cooldowns |
| **Pydantic v2** | Data validation and serialization |
| **blinkpy** | Blink camera authentication and media fetching |
| **python-jose + passlib** | JWT authentication with bcrypt |
| **LangGraph** | Agent orchestration primitives |

### Frontend
| Technology | Purpose |
|---|---|
| **React 18** | UI framework |
| **TypeScript** | Type safety |
| **Vite** | Build tool and dev server |
| **Zustand** | Lightweight state management |
| **Capacitor 5** | iOS native bridge (camera, push, geolocation) |
| **react-markdown** | Rendering AI responses |

## Project Structure

```
domus/
├── be/                              # Backend
│   ├── app/
│   │   ├── main.py                  # FastAPI app entry point
│   │   ├── agents/
│   │   │   ├── base.py              # BaseAgent, AgentType, ConversationState, ShoppingContext
│   │   │   ├── orchestrator.py      # DomusOrchestrator — intent detection, routing, synthesis
│   │   │   ├── fridge_agent.py      # DFridge — Gemini vision chat, meal planning
│   │   │   ├── calendar_agent.py    # DCalendar — events, workouts, time-aware meals
│   │   │   └── instacart_agent.py   # DInstacart — cart management, product suggestions
│   │   ├── api/
│   │   │   ├── routes.py            # REST endpoints (auth, blink, fridge, notifications, location)
│   │   │   └── websocket.py         # WebSocket handler, notification triggers, shopping context
│   │   ├── core/
│   │   │   ├── config.py            # Settings (env vars, CORS, model config)
│   │   │   └── auth.py              # JWT tokens, mock Gmail OAuth
│   │   ├── llm/
│   │   │   ├── gemini_service.py    # Gemini API wrapper (generate, stream, vision)
│   │   │   └── prompts.py           # System prompts per agent
│   │   ├── services/
│   │   │   ├── blink_service.py     # Blink camera auth, 2FA, media sync
│   │   │   ├── blink_motion_watcher.py  # Background polling for thumbnail changes
│   │   │   ├── calendar_service.py  # Mock calendar events
│   │   │   ├── fridge_inventory_service.py  # Camera capture + inventory extraction
│   │   │   ├── grocery_notification_service.py  # Geofence-triggered grocery nudges
│   │   │   ├── bake_sale_notification_service.py  # Event prep notifications
│   │   │   ├── push_notification_service.py  # FCM HTTP v1 push delivery
│   │   │   ├── location_service.py  # Geofence validation, demo store registry
│   │   │   └── instacart_service.py # Mock shopping cart + product catalog
│   │   └── storage/
│   │       ├── memory_store.py      # In-memory storage (dev/Phase 1)
│   │       └── redis_store.py       # Redis storage with Streams + Pub/Sub
│   ├── requirements.txt
│   └── .env
│
├── fe/                              # Frontend
│   ├── src/
│   │   ├── App.tsx                  # Root component, screen routing, Capacitor init
│   │   ├── main.tsx                 # React entry point
│   │   ├── config.ts               # Demo mode flag, API base URL
│   │   ├── pages/
│   │   │   ├── ChatPage.tsx         # Main chat UI (messages, action cards, Blink modal, notifications)
│   │   │   ├── SplashScreen.tsx     # 3-second splash with logo
│   │   │   ├── LoginPage.tsx        # Email login form
│   │   │   └── LandingPage.tsx      # Pre-login welcome
│   │   ├── components/
│   │   │   └── FridgeResponseCard.tsx  # Premium card UI for fridge analysis results
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts      # Real-time event streaming + reconnection
│   │   │   ├── useApi.ts            # REST API wrapper (auth, blink, media, notifications)
│   │   │   ├── useCapacitor.ts      # iOS native: push, local notifications, deep links
│   │   │   └── useGeofence.ts       # Location-based grocery store detection
│   │   ├── store/
│   │   │   └── useStore.ts          # Zustand global state (auth, messages, agents, notifications)
│   │   ├── types/
│   │   │   └── index.ts             # TypeScript types (events, agents, messages)
│   │   ├── utils/
│   │   │   └── parseFridgeResponse.ts  # Parser for structured fridge AI responses
│   │   └── assets/
│   │       └── styles.css           # Global styles, animations
│   ├── ios/                         # Xcode project (Capacitor-generated)
│   ├── capacitor.config.ts          # iOS app config (com.domus.app)
│   ├── vite.config.ts               # Dev server + API proxy
│   └── package.json
│
├── shared/                          # Contract-first shared types
│   ├── schemas/
│   │   ├── events.py                # DomusEvent, EventType, payloads, factory functions
│   │   ├── state.py                 # UserSession, InventorySnapshot, NotificationRecord, etc.
│   │   └── storage.py               # StateStore + EventStore abstract interfaces
│   └── types/
│       └── events.ts                # TypeScript mirror of events.py
│
├── mcp/                             # MCP servers (planned, Phase 2+)
├── pyproject.toml                   # Python package config (domus v1.0.0, Python 3.11+)
├── start-backend.sh                 # Backend startup script
├── start-frontend.sh                # Frontend startup script
└── .gitignore
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Redis (optional in Phase 1 — falls back to in-memory storage)
- Google Gemini API key

### Backend

```bash
cd be

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Set DOMUS_GEMINI_API_KEY in .env

# Run
uvicorn app.main:app --reload --port 8000
```

Or from the project root:
```bash
./start-backend.sh
```

### Frontend

```bash
cd fe
npm install
npm run dev
```

Or from the project root:
```bash
./start-frontend.sh
```

Visit `http://localhost:5173`.

### iOS Build

```bash
cd fe
npm run build
npx cap sync ios
npx cap open ios    # Opens Xcode
```

## Environment Variables

### Backend (`be/.env`)

| Variable | Description | Default |
|---|---|---|
| `DOMUS_GEMINI_API_KEY` | Google Gemini API key | Required |
| `DOMUS_DEMO_MODE` | Bypass authentication | `true` |
| `DOMUS_REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `DOMUS_REDIS_PASSWORD` | Redis password | (none) |
| `DOMUS_BLINK_REGION` | Blink account region | `us` |
| `FCM_SERVER_KEY` | Firebase service account key | (optional) |
| `FCM_PROJECT_ID` | Firebase project ID | `domus-app` |
| `DEMO_DEVICE_TOKEN` | iOS device token for push testing | (optional) |

### Frontend (`fe/.env`)

| Variable | Description | Default |
|---|---|---|
| `VITE_API_URL` | Backend API URL | `http://localhost:8000` |
| `VITE_WS_URL` | WebSocket URL (derived from API URL if not set) | (auto) |

## API Endpoints

### Authentication
- `POST /api/auth/login` — Email-based mock OAuth login. Returns JWT token + user info.

### Blink Camera Integration
- `POST /api/blink/login` — Blink credentials (email, password)
- `POST /api/blink/verify-2fa` — 6-digit 2FA verification
- `GET /api/blink/status` — Connection status
- `POST /api/blink/logout` — Disconnect

### Fridge
- `POST /api/fridge/refresh` — Capture camera frame + extract inventory
- `GET /api/fridge/inventory` — Get latest inventory snapshot

### Notifications
- `GET /api/notifications` — Notification history
- `POST /api/notifications/{id}/read` — Mark as read
- `GET /api/notifications/unread/count` — Unread badge count

### Location / Geofence
- `GET /api/location/stores` — Demo store geofences
- `POST /api/location/entered` — Geofence entry event (triggers grocery notification)

### Media
- `GET /api/media/{filename}` — Retrieve thumbnails and video clips

### Health
- `GET /` — Root health check
- `GET /api/health` — Detailed health with Redis status

### WebSocket
- `GET /ws?token=<jwt>` — Real-time event stream (chat messages, agent status, notifications, heartbeat)

## Key Data Flows

### Chat Message
```
User types message
  → WebSocket sends to backend
  → Orchestrator: get/create ConversationState
  → Short reply expansion (if mid-conversation)
  → Intent detection (context + pattern-based)
  → Route to agent(s)
  → Agent calls Gemini with domain-specific prompt
  → Status callbacks → WebSocket → frontend shows "Activating DFridge..."
  → Response → WebSocket → frontend renders (Markdown or FridgeResponseCard)
```

### Grocery Notification (Proactive)
```
User enters store geofence (or simulated on WebSocket connect)
  → Location service validates store
  → Inventory checked for low/out items
  → GroceryNotificationService creates judgment-driven message
  → Push notification (FCM) + WebSocket event
  → User taps notification → chat seed content inserted
  → Action card: "Add to List" / "Picked Up"
  → Shopping context set (10-min TTL)
  → Follow-up messages routed through Gemini with store + item context
  → Mid-shopping fridge check: model classifies intent → Gemini vision on thumbnail
```

### Budget Meal Planning (Multi-Turn)
```
User: "cheapest way to eat this week?"
  → Intent: BUDGET_MEAL_PLANNING
  → FridgeAgent vision analysis
  → Orchestrator returns short intro + "Show options?"
  → Phase: OFFERED_OPTIONS

User: "yes"
  → Expanded to: "Yes, please show me the budget meal options."
  → Intent: BUDGET_SHOW_OPTIONS
  → 3-5 structured meal options returned
  → Phase: EXPANDING_OPTIONS
```

## Demo Stores (Geofence)

| Store | Location | Coordinates |
|---|---|---|
| Whole Foods SoMa | San Francisco | 37.7785, -122.3950 |
| Trader Joe's Castro | San Francisco | 37.7609, -122.4350 |
| Safeway Marina | San Francisco | 37.8005, -122.4369 |
| Demo Grocery | Apple Park area | 37.3318, -122.0312 |

## Development Notes

### Demo Mode
Set `DOMUS_DEMO_MODE=true` (backend) and `DEMO_MODE=true` in `fe/src/config.ts` to bypass authentication. The app auto-authenticates with a demo token.

### Storage
Phase 1 uses in-memory storage (`MemoryDomusStorage`). Redis (`RedisDomusStorage`) is available and swappable via the abstract `DomusStorage` interface.

### Mock Services
Calendar, Instacart, and Location services use hardcoded demo data. Production implementations would swap in real API integrations behind the same interfaces.

### Adding a New Agent
1. Create `be/app/agents/my_agent.py` extending `BaseAgent`
2. Add `AgentType.MY_AGENT` to `base.py`
3. Register in `orchestrator.py`'s `_agents` dict
4. Add intent detection patterns
5. Add system prompt in `prompts.py`

## License

MIT License
