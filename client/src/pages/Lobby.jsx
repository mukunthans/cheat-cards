import { useEffect, useRef, useState } from "react";

const SEAT_COLORS = ["bg-seat-1", "bg-seat-2", "bg-seat-3", "bg-seat-4"];
const MAX_PLAYERS = 4;

function initials(name) {
  return (name || "?").trim().slice(0, 2).toUpperCase();
}

function SectionTitle({ children, note }) {
  return (
    <h2 className="font-display font-bold text-xl text-ivory mb-4 flex items-baseline gap-2">
      {children}
      {note && <span className="font-sans text-xs font-normal text-felt-fog/60">{note}</span>}
    </h2>
  );
}

export default function Lobby({ room, roomCode, selfId, actions, onLeave }) {
  const [copied, setCopied] = useState(false);
  const [handoff, setHandoff] = useState(null); // { fromName, toName, toSelf }
  const prevPlayersRef = useRef(room.players);
  const prevHostRef = useRef(room.host_id);

  const isHost = room.host_id === selfId;
  const settings = room.settings || {};
  const numPlayers = Math.max(room.players.length, 2);
  const countMin = 10 * numPlayers;
  const countMax = 25 * numPlayers;
  const cardCount = settings.card_count ?? 12 * numPlayers;
  const self = room.players.find((p) => p.id === selfId);
  const notReady = room.players.filter((p) => !p.ready);

  // The host seat moved. Name who lost it using the roster from before the change.
  useEffect(() => {
    if (room.host_id !== prevHostRef.current) {
      const fromName = prevPlayersRef.current.find((p) => p.id === prevHostRef.current)?.name;
      const toName = room.players.find((p) => p.id === room.host_id)?.name;
      if (fromName && toName) {
        setHandoff({ fromName, toName, toSelf: room.host_id === selfId });
      }
      prevHostRef.current = room.host_id;
    }
    prevPlayersRef.current = room.players;
  }, [room.host_id, room.players, selfId]);

  function patchSettings(patch) {
    if (!isHost) return;
    actions.updateSettings({ ...settings, ...patch });
  }

  function copyCode() {
    navigator.clipboard?.writeText(roomCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const readOnly = !isHost;
  const panel = "rounded-2xl border border-white/10 bg-black/25 p-5 sm:p-6";
  const chip = (active) =>
    `h-12 rounded-full px-4 font-semibold text-sm border transition-all disabled:cursor-not-allowed ${
      active
        ? "bg-gold border-gold text-ink shadow-gold"
        : "bg-black/30 border-white/15 text-ivory/80"
    }`;

  return (
    <div className="min-h-screen bg-felt-table px-4 py-6 sm:px-10 sm:py-10">
      <div className="mx-auto w-full max-w-lg lg:max-w-4xl">
        <header className="flex items-start justify-between mb-8">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-felt-fog/70">Room code</p>
            <button
              onClick={copyCode}
              className="block font-mono text-4xl sm:text-5xl font-medium text-ivory tracking-[0.18em] hover:text-gold transition-colors"
            >
              {roomCode}
            </button>
            <p className="font-mono text-[11px] text-felt-fog/60 mt-1">
              {copied ? <span className="text-truth">copied!</span> : "tap to copy ⧉"}
            </p>
          </div>
          <button
            onClick={onLeave}
            className="h-12 px-4 text-felt-fog/70 hover:text-ivory text-sm transition-colors"
          >
            Leave
          </button>
        </header>

        {handoff && (
          <div className="mb-6 rounded-2xl border border-gold/40 bg-gold/10 px-5 py-4 flex items-start gap-3 animate-slide-up">
            <p className="flex-1 text-sm text-gold-200">
              {handoff.fromName} left the table. {handoff.toName} is holding the deck now
              {handoff.toSelf ? " — you're the host! 🎩" : "."}
            </p>
            <button
              onClick={() => setHandoff(null)}
              className="text-gold/60 hover:text-gold text-lg leading-none"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
          <section className={panel}>
            <SectionTitle>
              Players ({room.players.length}/{MAX_PLAYERS})
            </SectionTitle>
            <ul className="space-y-2.5">
              {room.players.map((p, i) => (
                <li
                  key={p.id}
                  className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                    p.ready ? "border-truth/40 bg-truth/5" : "border-white/10"
                  } ${!p.connected ? "opacity-50" : ""}`}
                >
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0 ${
                      SEAT_COLORS[i % 4]
                    } ${!p.connected ? "grayscale" : ""}`}
                  >
                    {initials(p.name)}
                  </div>
                  <span className="flex-1 min-w-0 flex items-baseline gap-1.5">
                    <span className="text-ivory font-medium truncate">{p.name}</span>
                    {p.id === room.host_id && (
                      <span className="text-gold/70 text-xs shrink-0">★<span className="hidden sm:inline"> host</span></span>
                    )}
                    {p.id === selfId && <span className="text-gold text-xs shrink-0">(you)</span>}
                  </span>
                  {!p.connected ? (
                    <span className="font-mono text-[11px] text-felt-fog/50">offline</span>
                  ) : (
                    <span
                      className={`font-mono text-[10px] uppercase tracking-[0.14em] px-2.5 py-1 rounded-full ${
                        p.ready ? "bg-truth/15 text-truth animate-pop-in" : "bg-white/5 text-felt-fog/60"
                      }`}
                    >
                      {p.ready ? "ready" : "not ready"}
                    </span>
                  )}
                </li>
              ))}
              {Array.from({ length: MAX_PLAYERS - room.players.length }).map((_, i) => (
                <li
                  key={`open-${i}`}
                  className="flex items-center gap-3 rounded-xl border border-dashed border-white/10 px-3 py-2.5"
                >
                  <div className="w-9 h-9 rounded-full border border-dashed border-white/15 flex items-center justify-center text-felt-fog/40">
                    +
                  </div>
                  <span className="text-felt-fog/40 text-sm italic font-display">open seat</span>
                </li>
              ))}
            </ul>
          </section>

          <section className={`${panel} ${readOnly ? "opacity-75" : ""}`}>
            <SectionTitle note={readOnly ? "— set by host" : null}>Table settings</SectionTitle>

            <div className="space-y-6">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-felt-fog/70 mb-2">
                  Deck mode
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    ["random", "Random"],
                    ["fixed", "Fixed"],
                  ].map(([mode, label]) => (
                    <button
                      key={mode}
                      type="button"
                      disabled={readOnly}
                      onClick={() => patchSettings({ deck_mode: mode })}
                      className={chip(settings.deck_mode === mode)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {settings.deck_mode === "random" ? (
                <div>
                  <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-felt-fog/70 mb-3">
                    Card count
                  </p>
                  <input
                    type="range"
                    min={countMin}
                    max={countMax}
                    disabled={readOnly}
                    value={Math.min(Math.max(cardCount, countMin), countMax)}
                    onChange={(e) => patchSettings({ card_count: Number(e.target.value) })}
                    className="w-full accent-gold disabled:cursor-not-allowed"
                  />
                  <div className="flex items-center justify-between font-mono text-[11px] text-felt-fog/60 mt-1">
                    <span>{countMin} min</span>
                    <span className="text-gold text-sm">{cardCount} cards</span>
                    <span>{countMax} max</span>
                  </div>
                  <p className="text-[11px] text-felt-fog/50 mt-2 leading-relaxed">
                    Leftovers after an even deal are discarded — no card counting possible.
                  </p>
                </div>
              ) : (
                <div>
                  <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-felt-fog/70 mb-2">
                    Copies per number
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {[4, 5].map((k) => (
                      <button
                        key={k}
                        type="button"
                        disabled={readOnly}
                        onClick={() => patchSettings({ copies: k })}
                        className={chip(settings.copies === k)}
                      >
                        {k} copies · {k * 11}
                      </button>
                    ))}
                  </div>
                  <p className="text-[11px] text-felt-fog/50 mt-2 leading-relaxed">
                    Every card is dealt — hands may differ by one.
                  </p>
                </div>
              )}

              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-felt-fog/70 mb-2">
                  Min doubts to win
                </p>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    disabled={readOnly || settings.min_doubts <= 0}
                    onClick={() => patchSettings({ min_doubts: settings.min_doubts - 1 })}
                    className="w-12 h-12 rounded-full border border-white/15 bg-black/30 text-ivory text-xl disabled:opacity-30 disabled:cursor-not-allowed hover:border-gold/50 transition-colors"
                  >
                    –
                  </button>
                  <span className="font-display font-extrabold text-3xl text-gold w-10 text-center">
                    {settings.min_doubts}
                  </span>
                  <button
                    type="button"
                    disabled={readOnly || settings.min_doubts >= 10}
                    onClick={() => patchSettings({ min_doubts: settings.min_doubts + 1 })}
                    className="w-12 h-12 rounded-full border border-white/15 bg-black/30 text-ivory text-xl disabled:opacity-30 disabled:cursor-not-allowed hover:border-gold/50 transition-colors"
                  >
                    +
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div className="mt-8 text-center">
          {self?.ready ? (
            <div className="animate-pop-in">
              <p className="font-display italic text-xl text-truth mb-1">You're in.</p>
              <p className="text-felt-fog/70 text-sm">
                {room.players.length < 2
                  ? "Waiting for at least one more player…"
                  : notReady.length > 0
                    ? `waiting on ${notReady.map((p) => p.name).join(", ")}…`
                    : "Dealing…"}
              </p>
            </div>
          ) : (
            <>
              <button
                onClick={actions.setPlayerReady}
                className="h-14 px-10 rounded-full bg-gold hover:bg-gold-300 text-ink font-semibold text-lg shadow-gold transition-colors"
              >
                {isHost ? "Deal 'em in" : "I'm ready"}
              </button>
              {room.players.length < 2 && (
                <p className="font-mono text-[11px] text-felt-fog/50 mt-3">need 2+ ready players</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
