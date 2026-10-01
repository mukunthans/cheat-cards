import { useCallback, useEffect, useMemo, useState } from "react";
import socket from "./socket.js";
import { SESSION_KEY } from "./session.js";
import useRoomSocket from "./hooks/useRoomSocket.js";
import Home from "./pages/Home.jsx";
import Lobby from "./pages/Lobby.jsx";
import Game from "./pages/Game.jsx";

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const TONES = {
  error: "border-lie/40 bg-felt-void/95 text-ivory",
  burn: "border-gold/40 bg-felt-void/95 text-ivory",
  info: "border-white/15 bg-felt-void/95 text-ivory",
};

/** Toasts stack bottom-up, oldest at the bottom, and sit clear of the hand on mobile. */
function Toasts({ toasts }) {
  if (!toasts.length) return null;
  return (
    <div className="fixed z-[60] bottom-4 inset-x-4 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-80 flex flex-col-reverse gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-3 rounded-2xl border px-4 py-3 shadow-card-lg animate-slide-up ${
            TONES[t.tone] || TONES.info
          }`}
        >
          <span className="text-lg leading-none mt-0.5" aria-hidden>
            {t.icon}
          </span>
          <div className="text-left">
            <p className="text-sm font-semibold">{t.title}</p>
            {t.body && <p className="text-xs text-felt-fog/80 mt-0.5">{t.body}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function RoomScreen({ session, onLeave }) {
  const { ready, room, hand, turn, pile, reveal, burned, gameOver, disconnected, toasts, fatalError, actions } =
    useRoomSocket(session);
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (fatalError) onLeave();
  }, [fatalError, onLeave]);

  // Drive the reconnect-grace countdown shown in disconnect toasts.
  const graceIds = Object.keys(disconnected || {});
  useEffect(() => {
    if (!graceIds.length) return;
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [graceIds.length]);

  const nameOf = useCallback(
    (id) => room.players.find((p) => p.id === id)?.name || "Someone",
    [room.players]
  );

  const allToasts = useMemo(() => {
    const list = toasts.map((t) => ({ id: `err-${t.id}`, icon: "⚠️", title: t.message, tone: "error" }));
    if (burned) {
      list.push({
        id: `burn-${burned.new_starter_id}-${burned.burned_count}`,
        icon: "🔥",
        title: "Pile's burned!",
        body: `Nobody called it — ${nameOf(burned.new_starter_id)} starts fresh.`,
        tone: "burn",
      });
    }
    for (const [pid, deadline] of Object.entries(disconnected || {})) {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      list.push({
        id: `dc-${pid}`,
        icon: "📡",
        title: `${nameOf(pid)} dropped`,
        body: `Holding their seat for ${left}s…`,
        tone: "info",
      });
    }
    return list;
  }, [toasts, burned, disconnected, nameOf]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-felt-table flex items-center justify-center">
        <p className="font-display italic text-xl text-felt-fog animate-breathe">Connecting…</p>
      </div>
    );
  }

  return (
    <>
      <Toasts toasts={allToasts} />
      {room.state === "lobby" ? (
        <Lobby room={room} roomCode={session.roomCode} selfId={session.playerId} actions={actions} onLeave={onLeave} />
      ) : (
        <Game
          room={room}
          roomCode={session.roomCode}
          selfId={session.playerId}
          hand={hand}
          turn={turn}
          pile={pile}
          reveal={reveal}
          burned={burned}
          gameOver={gameOver}
          disconnected={disconnected}
          actions={actions}
          onLeave={onLeave}
        />
      )}
    </>
  );
}

export default function App() {
  const [session, setSession] = useState(loadSession);

  const handleJoined = useCallback((newSession) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(newSession));
    setSession(newSession);
  }, []);

  const handleLeave = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    socket.disconnect();
    setSession(null);
  }, []);

  if (!session) {
    return <Home onJoined={handleJoined} />;
  }
  return <RoomScreen key={session.roomCode + session.playerId} session={session} onLeave={handleLeave} />;
}
