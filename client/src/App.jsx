import { useCallback, useEffect, useState } from "react";
import socket from "./socket.js";
import useRoomSocket from "./hooks/useRoomSocket.js";
import Home from "./pages/Home.jsx";
import Lobby from "./pages/Lobby.jsx";
import Game from "./pages/Game.jsx";

const SESSION_KEY = "cheatcards_session";

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function Toasts({ toasts }) {
  if (!toasts.length) return null;
  return (
    <div className="fixed top-3 left-1/2 -translate-x-1/2 z-[60] flex flex-col gap-2 items-center px-4 w-full max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="bg-red-950/90 border border-red-500/40 text-red-100 text-sm rounded-lg px-4 py-2 shadow-card-lg animate-slide-up w-full text-center"
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}

function RoomScreen({ session, onLeave }) {
  const { ready, room, hand, turn, pile, reveal, burned, gameOver, disconnected, toasts, fatalError, actions } =
    useRoomSocket(session);

  useEffect(() => {
    if (fatalError) onLeave();
  }, [fatalError, onLeave]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-felt-dark to-felt flex items-center justify-center">
        <p className="text-white/70 text-sm animate-pulse">Connecting…</p>
      </div>
    );
  }

  return (
    <>
      <Toasts toasts={toasts} />
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
