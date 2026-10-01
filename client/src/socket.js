import { io } from "socket.io-client";

// In production the client and server are separately hosted, so the server's
// public URL is baked in at build time. In dev we connect same-origin and let
// Vite's /socket.io proxy (see vite.config.js) forward to the backend on :8000 —
// that way `npm run dev -- --host` also works from another device on the LAN,
// where "localhost" would mean *that device*, not this laptop.
const URL =
  import.meta.env.MODE === "production"
    ? import.meta.env.VITE_SERVER_URL
    : window.location.origin;

const socket = io(URL, { autoConnect: false });

export default socket;
