# Cheat Cards

A real-time, turn-based online card game for 2–4 players (the "Cheat / BS" card game).

## Quick Start

### Server
```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:asgi_app --reload --port 8000
```

### Client
```bash
cd client
npm install
npm run dev
```

Open http://localhost:5173
