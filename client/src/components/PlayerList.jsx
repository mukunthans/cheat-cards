const AVATAR_COLORS = ["bg-rose-500", "bg-sky-500", "bg-amber-500", "bg-violet-500"];

function initials(name) {
  return (name || "?").trim().slice(0, 2).toUpperCase();
}

/** Seats around the table: name, card count, doubt quota, connection + turn state. */
export default function PlayerList({ players, hostId, activePlayerId, selfId, minDoubts, disconnected }) {
  return (
    <div className="flex flex-wrap justify-center gap-3">
      {players.map((p, i) => {
        const isActive = p.id === activePlayerId;
        const isSelf = p.id === selfId;
        const grace = disconnected?.[p.id];
        const quotaMet = p.doubts_made >= minDoubts;
        return (
          <div
            key={p.id}
            className={`flex items-center gap-2 rounded-xl px-3 py-2 bg-black/25 border ${
              isActive ? "border-amber-400 animate-pulse-ring" : "border-white/10"
            }`}
          >
            <div
              className={`w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0 ${AVATAR_COLORS[i % 4]} ${
                grace ? "opacity-40 grayscale" : ""
              }`}
            >
              {initials(p.name)}
            </div>
            <div className="text-left leading-tight">
              <p className="text-white text-sm font-semibold flex items-center gap-1">
                {p.name}
                {isSelf && <span className="text-[10px] text-amber-300">(you)</span>}
                {p.id === hostId && <span className="text-[10px] text-felt-light">★</span>}
              </p>
              <p className="text-[11px] text-felt-light/80">
                🂠 {p.card_count} · doubts {p.doubts_made}/{minDoubts}{" "}
                <span className={quotaMet ? "text-emerald-400" : ""}>{quotaMet ? "✓" : ""}</span>
              </p>
              {grace && <p className="text-[11px] text-red-400">reconnecting…</p>}
              {!p.connected && !grace && <p className="text-[11px] text-red-400">offline</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
