import { useState } from "react";
import socket from "../socket.js";
import Card from "../components/Card.jsx";
import { NAME_KEY } from "../session.js";

/** Full-screen "shuffling up a table" state — a spinning card back, never a spinner icon. */
function Shuffling({ label }) {
  return (
    <div className="min-h-screen bg-felt-table flex flex-col items-center justify-center gap-8 p-4">
      <div className="animate-slow-spin">
        <Card faceDown size="lg" />
      </div>
      <div className="text-center">
        <p className="font-display italic text-2xl text-ivory animate-breathe">{label}</p>
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-felt-fog/60 mt-3">
          dealing your room code
        </p>
      </div>
    </div>
  );
}

export default function Home({ onJoined }) {
  const [name, setName] = useState(() => localStorage.getItem(NAME_KEY) || "");
  const [roomCode, setRoomCode] = useState("");
  const [error, setError] = useState("");
  const [errorField, setErrorField] = useState(null); // "name" | "code"
  const [busy, setBusy] = useState(null); // "create" | "join"
  const [shakeKey, setShakeKey] = useState(0);

  function fail(message, field) {
    setError(message);
    setErrorField(field);
    setShakeKey((k) => k + 1);
    setBusy(null);
  }

  function requireName() {
    const trimmed = name.trim();
    if (!trimmed) {
      fail("Enter your name first.", "name");
      return null;
    }
    localStorage.setItem(NAME_KEY, trimmed);
    return trimmed;
  }

  function enter(ack, code, playerName) {
    onJoined({
      roomCode: code,
      playerId: ack.player_id,
      sessionToken: ack.session_token,
      playerName,
    });
  }

  function createRoom() {
    const playerName = requireName();
    if (!playerName) return;
    setError("");
    setErrorField(null);
    setBusy("create");
    if (!socket.connected) socket.connect();
    socket.emit("create_room", { player_name: playerName }, (ack) => {
      if (ack?.error) return fail(ack.error.message || "Could not deal a new table.", null);
      setBusy(null);
      enter(ack, ack.room_code, playerName);
    });
  }

  function joinRoom(e) {
    e.preventDefault();
    const playerName = requireName();
    if (!playerName) return;
    const code = roomCode.trim().toUpperCase();
    if (code.length !== 5) return fail("Room codes are 5 characters.", "code");
    setError("");
    setErrorField(null);
    setBusy("join");
    if (!socket.connected) socket.connect();
    socket.emit("join_room", { room_code: code, player_name: playerName }, (ack) => {
      if (ack?.error) {
        return fail(
          ack.error.code === "room_not_found"
            ? "No table's running that code. Typo, or it already ended."
            : ack.error.message || "Could not join that table.",
          "code"
        );
      }
      setBusy(null);
      enter(ack, code, playerName);
    });
  }

  if (busy) return <Shuffling label={busy === "create" ? "Shuffling up a table…" : "Pulling up a chair…"} />;

  const fieldRing = (field) =>
    errorField === field
      ? "border-lie focus:ring-lie/60"
      : "border-white/10 focus:ring-gold/70";

  return (
    <div className="min-h-screen bg-felt-table flex items-center justify-center p-4 sm:p-10">
      <div className="w-full max-w-sm lg:max-w-md">
        <div className="text-center mb-10 animate-pop-in">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="animate-hover3">
              <Card faceDown size="sm" />
            </div>
            <h1 className="font-display font-extrabold text-6xl lg:text-7xl text-ivory tracking-tight leading-none">
              Cheat<span className="text-gold">Cards</span>
            </h1>
          </div>
          <p className="font-display italic text-lg lg:text-xl text-felt-fog">
            everyone's lying tonight
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-black/25 p-6 shadow-card-lg">
          <label className="block font-mono text-[11px] uppercase tracking-[0.18em] text-felt-fog/80 mb-2">
            Your name
          </label>
          <input
            key={`name-${shakeKey}`}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={20}
            placeholder="who's playing?"
            className={`w-full h-12 rounded-xl border bg-black/30 px-4 text-ivory placeholder:text-felt-fog/40 focus:outline-none focus:ring-2 transition-colors mb-5 ${fieldRing(
              "name"
            )} ${errorField === "name" ? "animate-shake" : ""}`}
          />

          <button
            type="button"
            onClick={createRoom}
            className="w-full h-12 rounded-full bg-gold hover:bg-gold-300 text-ink font-semibold text-lg transition-colors shadow-gold"
          >
            Start a game
          </button>

          <div className="flex items-center gap-3 my-6">
            <div className="h-px flex-1 bg-white/10" />
            <span className="font-display italic text-sm text-felt-fog/70">
              or join one already going
            </span>
            <div className="h-px flex-1 bg-white/10" />
          </div>

          <form onSubmit={joinRoom} className="space-y-3">
            <input
              key={`code-${shakeKey}`}
              type="text"
              value={roomCode}
              onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
              maxLength={5}
              placeholder="ABCDE"
              className={`w-full h-12 rounded-xl border bg-black/30 px-4 text-center font-mono text-xl tracking-[0.35em] text-ivory placeholder:text-felt-fog/30 focus:outline-none focus:ring-2 transition-colors ${fieldRing(
                "code"
              )} ${errorField === "code" ? "animate-shake" : ""}`}
            />
            <button
              type="submit"
              className="w-full h-12 rounded-full border border-gold/50 text-gold hover:bg-gold/10 font-semibold transition-colors"
            >
              Join room
            </button>
          </form>

          {error && (
            <p className="mt-4 text-center text-lie text-sm flex items-center justify-center gap-2">
              <span aria-hidden>🙃</span>
              {error}
            </p>
          )}
        </div>

        <p className="text-center font-mono text-[11px] text-felt-fog/50 mt-8">
          2–4 players · one shared room code
        </p>
      </div>
    </div>
  );
}
