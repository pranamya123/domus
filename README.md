# Domus - Hierarchical Multi-Agent Smart Home System

A production-grade, extensible smart home system with **DomusFridge** - a camera-enabled fridge agent that tracks inventory, predicts expiration, and integrates with meal planning.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │   Chat   │  │  Camera  │  │  Notif   │  │  Debug   │    │
│  │Interface │  │   View   │  │  Inbox   │  │  Panel   │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Level 0: Domus Orchestrator             │    │
│  │  • Owns user communication                           │    │
│  │  • Routes notifications                              │    │
│  │  • Calls external services                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Level 1: DomusFridge Agent              │    │
│  │  • Manages fridge state                              │    │
│  │  • Emits intents only (no user communication)        │    │
│  │  • Tracks inventory & expiration                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                              │                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Services                          │    │
│  │  Vision (Gemini) │ Calendar │ Instacart │ Notifs    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Phase 1 (Current)
- **Fridge Inventory Management**: Upload or capture images to scan fridge contents
- **Vision AI Analysis**: Uses Gemini Vision API (or simulated responses)
- **Expiration Tracking**: Predicts and alerts on expiring items
- **Conversational Interface**: Chat with Domus about your fridge
- **Real-time Notifications**: In-app inbox, push (simulated), Alexa (simulated)
- **IoT Camera Support**: Simulated endpoint for fridge camera integration

### Agent Boundaries (Enforced)
- **Level 0 (Orchestrator)**: Sole authority for user communication and external APIs
- **Level 1 (DomusFridge)**: Domain expert that emits structured intents only

## Tech Stack

### Backend
- **FastAPI** - Async Python web framework
- **SQLAlchemy** - Async ORM with SQLite (PostgreSQL-ready)
- **Pydantic** - Data validation
- **Google Gemini** - Vision AI for image analysis
- **WebSockets** - Real-time communication

### Frontend
- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **TailwindCSS** - Styling (dark mode)
- **Zustand** - State management

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- (Optional) Gemini API key for real vision analysis

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (Gemini API key optional)

# Run the server
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

Visit `http://localhost:5173` to access the application.

## API Endpoints

### Authentication
- `POST /api/auth/login` - Development login
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout

### Chat
- `POST /api/chat/message` - Send message to Domus
- `GET /api/chat/history` - Get conversation history
- `WS /api/chat/ws/{token}` - WebSocket for real-time chat

### Upload
- `POST /api/upload/image` - Upload fridge image for analysis
- `POST /api/upload/validate` - Validate image without processing

### IoT
- `POST /api/ingest/iot` - Ingest image from IoT camera
- `POST /api/ingest/device/register` - Register IoT device
- `GET /api/ingest/device/{household_id}/status` - Get device status

### Notifications
- `GET /api/notifications/` - Get user notifications
- `POST /api/notifications/read/{id}` - Mark notification read
- `POST /api/notifications/read-all` - Mark all read
- `WS /api/notifications/ws/{token}` - WebSocket for real-time notifications

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | (optional) |
| `DATABASE_URL` | Database connection string | SQLite |
| `SECRET_KEY` | JWT signing key | (required in prod) |
| `IOT_DEVICE_TOKEN` | Token for IoT device auth | mock-iot-device-token |
| `IOT_IMAGE_DEBOUNCE_SECONDS` | Min seconds between IoT images | 900 (15 min) |

## Development

### Project Structure

```
domus/
├── backend/
│   ├── app/
│   │   ├── agents/          # L0 Orchestrator, L1 DomusFridge
│   │   ├── api/routes/      # FastAPI endpoints
│   │   ├── core/            # EventBus, Security, Database
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   └── services/        # Vision, Calendar, Instacart, Notifications
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── pages/           # Page components
│   │   ├── providers/       # Context providers
│   │   ├── services/        # API client
│   │   ├── store/           # Zustand store
│   │   └── types/           # TypeScript types
│   └── package.json
└── README.md
```

### Testing the System

1. **Login**: Use any email/name combination
2. **Chat**: Ask "What's in my fridge?"
3. **Scan**: Upload a fridge image (any image works in dev mode)
4. **Notifications**: Check the Alerts tab for expiry warnings

### Simulated vs Real Vision

Without a Gemini API key, the system uses simulated responses with realistic mock data. To enable real vision analysis:

1. Get an API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Add to `.env`: `GEMINI_API_KEY=your-key-here`
3. Restart the backend

## Success Criteria (per spec)

### Traceability Test
```
Upload Image → Validation Passed → Inventory Updated →
L1 emits EXPIRY_WARNING → L0 routes to NotificationService
```

### Debounce Test
```
T=0    IoT upload accepted
T=5m   IoT upload ignored (within debounce window)
T=16m  IoT upload accepted
```

### Notification Test
- Expiry event appears in `logs/notifications.log`
- Expiry event appears in React Notification Inbox

## Out of Scope (Phase 1)
- Multi-fridge households
- Pantry/Laundry agents
- Real Alexa skill integration
- Real payment processing
- Nutritional optimization

## License

MIT License - See LICENSE file for details.
