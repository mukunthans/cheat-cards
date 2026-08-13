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

## Deployment

The server is a FastAPI + Socket.IO app deployed as a container on Render's free
tier; the client is a static Vite build on Netlify's free tier. Neither requires a
credit card. Both configs are checked in — the deploy itself needs your own
Render/Netlify login, which only you can do (see below), but everything after that
login is a couple of clicks or commands.

### Server → Render
[`server/render.yaml`](server/render.yaml) and [`server/Dockerfile`](server/Dockerfile)
are ready to go.
1. On [dashboard.render.com](https://dashboard.render.com), **New → Blueprint**,
   connect GitHub, pick this repo. Render detects `server/render.yaml` and proposes
   the `cheat-cards-server` web service on the free plan — confirm it.
2. Deploy. Once live, Render shows the URL (e.g.
   `https://cheat-cards-server.onrender.com`).

Free-tier services spin down after 15 minutes of inactivity and take 30-60s to wake
on the next request — the first player to open the room after a quiet period will
see a slightly slow initial connect.

### Client → Netlify
[`client/netlify.toml`](client/netlify.toml) has the build command and output dir.
Easiest path is the Netlify dashboard (no CLI needed):
1. On [app.netlify.com](https://app.netlify.com), **Add new site → Import an
   existing project**, connect GitHub, pick this repo, and set **Base directory**
   to `client`. It reads `client/netlify.toml` for the rest.
2. In **Site configuration → Environment variables**, add `VITE_SERVER_URL` set to
   your Render server URL from above (e.g. `https://cheat-cards-server.onrender.com`
   — no trailing slash). This is read at build time, so redeploy after adding/changing it.
3. Deploy. Share the resulting `*.netlify.app` URL — that's the room link for friends.

(Or via CLI from `client/`: `netlify login`, `netlify init`, `netlify deploy --prod`.)

### Updating CORS after both are live
Once you have the real Netlify URL, set `CORS_ORIGINS` on the Render service
(**Environment** tab in the dashboard, or edit the `envVars` block in
`server/render.yaml` and push) to it, redeploy the server, so only your client can
open a socket connection.
