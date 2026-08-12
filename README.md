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

The server is a FastAPI + Socket.IO app deployed as a container on Fly.io's free
allowance; the client is a static Vite build on Netlify's free tier. Both configs
are checked in — the deploy itself needs your own Fly/Netlify login, which only you
can do (see below), but everything after that login is a couple of commands.

### Server → Fly.io
[`server/fly.toml`](server/fly.toml) and [`server/Dockerfile`](server/Dockerfile) are
ready to go. From the `server/` directory:
```bash
fly auth login          # opens a browser to log in / sign up — one-time
fly launch --no-deploy  # detects fly.toml; say NO to "Would you like to copy its
                         # configuration to the new app?" prompts that try to
                         # override it, confirm the app name (or pick a new one
                         # if "cheat-cards-server" is taken)
fly deploy
```
`fly launch` may ask to create a Postgres/Redis database — decline, this app needs
neither. Once deployed, `fly status` shows the live URL (e.g.
`https://cheat-cards-server.fly.dev`).

Free-tier machines scale to zero when idle (`auto_stop_machines` in `fly.toml`) and
take a few seconds to wake on the next request — the first player to open the room
after a quiet period will see a slightly slow initial connect.

### Client → Netlify
[`client/netlify.toml`](client/netlify.toml) has the build command and output dir.
Easiest path is the Netlify dashboard (no CLI needed):
1. On [app.netlify.com](https://app.netlify.com), **Add new site → Import an
   existing project**, connect GitHub, pick this repo, and set **Base directory**
   to `client`. It reads `client/netlify.toml` for the rest.
2. In **Site configuration → Environment variables**, add `VITE_SERVER_URL` set to
   your Fly server URL from above (e.g. `https://cheat-cards-server.fly.dev` — no
   trailing slash). This is read at build time, so redeploy after adding/changing it.
3. Deploy. Share the resulting `*.netlify.app` URL — that's the room link for friends.

(Or via CLI from `client/`: `netlify login`, `netlify init`, `netlify deploy --prod`.)

### Updating CORS after both are live
Once you have the real Netlify URL, set `CORS_ORIGINS` in `server/fly.toml`'s
`[env]` block to it (or `fly secrets set CORS_ORIGINS=https://your-site.netlify.app`),
redeploy the server, so only your client can open a socket connection.
