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

The server is a FastAPI + Socket.IO app on Render's free tier; the client is a static
Vite build on Vercel's free tier. Both configs are checked in and turnkey — no
manual dashboard setup needed beyond connecting the repo.

### Server → Render
1. On [render.com](https://render.com), **New → Blueprint**, point it at this repo.
   Render reads [`render.yaml`](render.yaml) and creates the service automatically
   (free plan, `pip install -r requirements.txt`, starts on `$PORT`).
2. Once deployed, copy the service URL (e.g. `https://cheat-cards-server.onrender.com`).
3. In the service's **Environment** tab, set `CORS_ORIGINS` to your Vercel client
   URL from the step below (comma-separated if there's more than one, e.g. a
   preview + production URL). It defaults to `*` (open) so the app works before
   you've deployed the client — tighten it once you have a real client URL.

Free-tier services spin down after 15 min idle and take ~30–50s to wake on the
next request — the first player to open the room will see a slow initial connect.

### Client → Vercel
1. On [vercel.com](https://vercel.com), **Add New → Project**, import this repo, and
   set the project's **Root Directory** to `client`. It reads
   [`client/vercel.json`](client/vercel.json) for the build command and output dir.
2. Add an environment variable `VITE_SERVER_URL` set to your Render server URL from
   above (e.g. `https://cheat-cards-server.onrender.com` — no trailing slash).
   This must be set at build time, so redeploy after adding/changing it.
3. Deploy. Share the resulting `*.vercel.app` URL — that's the room link for friends.

### Updating CORS after both are live
Once you have the real Vercel URL, set `CORS_ORIGINS` on Render to it and redeploy
the server so only your client can open a socket connection.
