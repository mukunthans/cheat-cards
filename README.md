# Cheat Cards

A bluffing card game for **2–4 friends**. Create a room, share its five-character code, and play from your phone or computer. The opener chooses a number. Everyone else can add cards face down, pass, or challenge the previous play.

**[Play Cheat Cards](https://cheat-cards.netlify.app/)** · [Alternate game link](https://cheat-cards-play.onrender.com/) · [Architecture guide](https://cheat-cards.netlify.app/architecture.html) · [Release history](CHANGELOG.md)

## How a round works

- Play any number of cards from your hand under the round’s declared number. You can tell the truth or bluff.
- Call doubt to reveal the most recent play. If any card differs from the claim, the player who laid the cards takes the pile. Otherwise the challenger takes it.
- If everyone passes after the latest play, the pile leaves the game. Each new play clears the previous passes.
- Players take turns opening rounds in seat order. At a three-player table, A opens, then B, then C, then A again. The opener can choose a fresh number each time.
- To win, meet the room’s doubt requirement and empty your hand. Other players can challenge your last play. The [full rules](CLAUDE.md#24-turn--round-system) cover timeouts and the one-card exception.

## Run locally

From the repository root, start the Python server in one terminal:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:asgi_app --reload --port 8000
```

In a second terminal, start the React frontend:

```bash
cd client
npm ci
npm run dev
```

To play multiplayer on one computer, open a separate tab for each seat. [Player 1](http://localhost:5173/?seat=1) creates the room. [Player 2](http://localhost:5173/?seat=2), [Player 3](http://localhost:5173/?seat=3), and [Player 4](http://localhost:5173/?seat=4) can join with its code. The game starts when at least two players have joined and everyone in the room is ready.

## Test and build

With the server virtual environment active, run these commands from the repository root:

```bash
python -m pytest -q server/tests
npm --prefix client run build
```

The tests exercise the game rules and multiplayer connections, including challenges, turn timers, reconnects, and private hand updates.

## Hosting

Netlify and Render each serve a copy of the React frontend. Players on either site can join the same room because their browsers connect directly to one FastAPI and Socket.IO server on Render. The server holds hands, rooms, and timers in memory. A server restart clears active games.

For another deployment, build the frontend with `VITE_SERVER_URL` set to the backend’s HTTPS URL. Set `CORS_ORIGINS` on the backend to the comma-separated list of frontend origins. The local Vite server already proxies game connections to port 8000.

[Render configuration](server/render.yaml) · [Dockerfile](server/Dockerfile) · [Netlify configuration](client/netlify.toml) · [Backend health check](https://cheat-cards.onrender.com/health)
