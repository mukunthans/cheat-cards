const SEAT_COLORS = ["bg-seat-1", "bg-seat-2", "bg-seat-3", "bg-seat-4"];

function initials(name) {
  return (name || "?").trim().slice(0, 2).toUpperCase();
}

/** A card-back glyph. Drawn rather than typed — U+1F0A0 has no coverage in the UI fonts. */
function CardsIcon() {
  return (
    <svg viewBox="0 0 10 14" className="w-2.5 h-3.5 inline-block align-[-2px]" aria-hidden>
      <rect x="0.5" y="0.5" width="9" height="13" rx="1.5" fill="none" stroke="currentColor" />
      <line x1="2.5" y1="3.5" x2="7.5" y2="10.5" stroke="currentColor" strokeWidth="0.75" />
    </svg>
  );
}

/**
 * Seats around the table: name, card count, doubt quota, connection + turn state.
 *
 * The active seat carries the gold pulse ring so "whose turn" reads at a glance
 * without extra copy. The quota check is emerald, never gold — gold stays
 * reserved for "your move" and primary actions. Below `sm` the quota drops off the
 * chip so four seats still fit across a 390px table; the header pill carries your own.
 */
export default function PlayerList({ players, hostId, activePlayerId, selfId, minDoubts, disconnected }) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {players.map((p, i) => {
        const isActive = p.id === activePlayerId;
        const grace = disconnected?.[p.id];
        const graceLeft = grace ? Math.max(0, Math.ceil((grace - Date.now()) / 1000)) : 0;
        const quotaMet = p.doubts_made >= minDoubts;
        const dimmed = grace || !p.connected;

        return (
          <div
            key={p.id}
            className={`flex items-center gap-2 rounded-2xl px-2.5 py-1.5 sm:px-3 sm:py-2 border transition-colors ${
              isActive ? "border-gold/70 bg-felt-dark/70 animate-pulse-ring" : "border-white/10 bg-black/25"
            } ${dimmed ? "opacity-60" : ""}`}
          >
            <div
              className={`w-8 h-8 sm:w-9 sm:h-9 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0 ${
                SEAT_COLORS[i % 4]
              } ${dimmed ? "grayscale" : ""}`}
            >
              {initials(p.name)}
            </div>

            <div className="text-left leading-tight">
              <p className="text-ivory text-sm font-semibold flex items-center gap-1.5">
                <span className="max-w-[7rem] truncate">{p.name}</span>
                {p.id === selfId && <span className="text-[10px] font-normal text-gold">(you)</span>}
                {p.id === hostId && <span className="text-[10px] text-gold/70">★</span>}
              </p>

              {grace ? (
                <p className="font-mono text-[11px] text-lie">reconnecting… {graceLeft}s</p>
              ) : !p.connected ? (
                <p className="font-mono text-[11px] text-felt-fog/50">offline</p>
              ) : (
                <p className="font-mono text-[11px] text-felt-fog/80 flex items-center gap-1">
                  <CardsIcon />
                  {p.card_count}
                  <span className="hidden sm:inline">
                    {" · "}doubts {p.doubts_made}/{minDoubts}
                    {quotaMet && <span className="text-truth"> ✓</span>}
                  </span>
                  {quotaMet && <span className="sm:hidden text-truth">✓</span>}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
