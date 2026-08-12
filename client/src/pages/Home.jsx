import { useState } from "react";
import socket from "../socket.js";

const NAME_KEY = "cheatcards_name";

export default function Home({ onJoined }) {
  const [mode, setMode] = useState("create"); // "create" | "join"
  const [name, setName] = useState(() => localStorage.getItem(NAME_KEY) || "");
  const [roomCode, setRoomCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function submit(e) {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Enter your name first.");
      return;
    }
    setError("");
    setBusy(true);
    localStorage.setItem(NAME_KEY, trimmedName);

    if (!socket.connected) socket.connect();

    if (mode === "create") {
      socket.emit("create_room", { player_name: trimmedName }, (ack) => {
        setBusy(false);
        if (ack?.error) {
          setError(ack.error.message || "Could not create room.");
          return;
        }
        onJoined({
          roomCode: ack.room_code,
          playerId: ack.player_id,
          sessionToken: ack.session_token,
          playerName: trimmedName,
        });
      });
    } else {
      const code = roomCode.trim().toUpperCase();
      if (code.length !== 5) {
        setBusy(false);
        setError("Room codes are 5 characters.");
        return;
      }
      socket.emit("join_room", { room_code: code, player_name: trimmedName }, (ack) => {
        setBusy(false);
        if (ack?.error) {
          setError(ack.error.message || "Could not join room.");
          return;
        }
        onJoined({
          roomCode: code,
          playerId: ack.player_id,
          sessionToken: ack.session_token,
          playerName: trimmedName,
        });
      });
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-felt-dark to-felt flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-5xl font-display font-bold text-white tracking-tight">🃏 Cheat Cards</h1>
          <p className="text-felt-light/80 mt-2 text-sm">Bluff big. Doubt often. Empty your hand.</p>
        </div>

        <div className="bg-black/25 border border-white/10 rounded-2xl p-6 shadow-card-lg">
          <div className="grid grid-cols-2 gap-1 bg-black/30 rounded-full p-1 mb-5">
            {["create", "join"].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setMode(m);
                  setError("");
                }}
                className={`rounded-full py-2 text-sm font-semibold transition-colors ${
                  mode === m ? "bg-amber-400 text-felt-dark" : "text-white/70 hover:text-white"
                }`}
              >
                {m === "create" ? "Create Room" : "Join Room"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-felt-light/80 mb-1 uppercase tracking-wide">
                Your name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={20}
                placeholder="e.g. Mukunthan"
                className="w-full rounded-lg bg-white/95 px-3 py-2 text-felt-dark placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>

            {mode === "join" && (
              <div>
                <label className="block text-xs font-semibold text-felt-light/80 mb-1 uppercase tracking-wide">
                  Room code
                </label>
                <input
                  type="text"
                  value={roomCode}
                  onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
                  maxLength={5}
                  placeholder="ABCDE"
                  className="w-full rounded-lg bg-white/95 px-3 py-2 text-felt-dark tracking-[0.3em] font-mono text-center placeholder:text-slate-400 placeholder:tracking-[0.3em] focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>
            )}

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              type="submit"
              disabled={busy}
              className="w-full bg-amber-400 hover:bg-amber-300 disabled:opacity-60 text-felt-dark font-bold py-2.5 rounded-lg transition-colors"
            >
              {busy ? "…" : mode === "create" ? "Create Room" : "Join Room"}
            </button>
          </form>
        </div>

        <p className="text-center text-felt-light/50 text-xs mt-6">2–4 players · one shared room code</p>
      </div>
    </div>
  );
}
