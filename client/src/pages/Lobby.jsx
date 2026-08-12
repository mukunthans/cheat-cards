import { useState } from "react";

const AVATAR_COLORS = ["bg-rose-500", "bg-sky-500", "bg-amber-500", "bg-violet-500"];

export default function Lobby({ room, roomCode, selfId, actions, onLeave }) {
  const [copied, setCopied] = useState(false);
  const isHost = room.host_id === selfId;
  const settings = room.settings;
  const numPlayers = Math.max(room.players.length, 2);
  const countMin = 10 * numPlayers;
  const countMax = 25 * numPlayers;
  const self = room.players.find((p) => p.id === selfId);
  const notReady = room.players.filter((p) => !p.ready);

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

  return (
    <div className="min-h-screen bg-gradient-to-b from-felt-dark to-felt p-4 flex flex-col items-center">
      <div className="w-full max-w-lg">
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-felt-light/70 text-xs uppercase tracking-wide">Room code</p>
            <button
              onClick={copyCode}
              className="text-3xl font-mono font-bold text-white tracking-[0.2em] hover:text-amber-300"
              title="Click to copy"
            >
              {roomCode} {copied && <span className="text-sm text-emerald-400 align-middle">copied!</span>}
            </button>
          </div>
          <button onClick={onLeave} className="text-felt-light/70 hover:text-white text-sm underline">
            Leave
          </button>
        </div>

        <section className="bg-black/25 border border-white/10 rounded-2xl p-5 mb-4">
          <h2 className="text-white font-semibold mb-3">Players ({room.players.length}/4)</h2>
          <ul className="space-y-2">
            {room.players.map((p, i) => (
              <li key={p.id} className="flex items-center gap-3">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold ${AVATAR_COLORS[i % 4]}`}
                >
                  {p.name.slice(0, 2).toUpperCase()}
                </div>
                <span className="text-white flex-1">
                  {p.name}
                  {p.id === selfId && <span className="text-amber-300 text-xs ml-1">(you)</span>}
                  {p.id === room.host_id && <span className="text-felt-light text-xs ml-1">★ host</span>}
                </span>
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    p.ready ? "bg-emerald-500/20 text-emerald-400" : "bg-white/10 text-white/60"
                  }`}
                >
                  {p.ready ? "Ready" : "Not ready"}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="bg-black/25 border border-white/10 rounded-2xl p-5 mb-6">
          <h2 className="text-white font-semibold mb-3">
            Settings {!isHost && <span className="text-felt-light/60 text-xs font-normal">(host only)</span>}
          </h2>

          <div className="space-y-4">
            <div>
              <p className="text-xs text-felt-light/80 uppercase tracking-wide mb-1">Deck mode</p>
              <div className="grid grid-cols-2 gap-2">
                {["random", "fixed"].map((m) => (
                  <button
                    key={m}
                    type="button"
                    disabled={!isHost}
                    onClick={() => patchSettings({ deck_mode: m })}
                    className={`rounded-lg py-2 text-sm font-semibold border transition-colors disabled:cursor-not-allowed ${
                      settings.deck_mode === m
                        ? "bg-amber-400 border-amber-300 text-felt-dark"
                        : "bg-black/20 border-white/15 text-white/80"
                    }`}
                  >
                    {m === "random" ? "Random" : "Fixed (card counting)"}
                  </button>
                ))}
              </div>
            </div>

            {settings.deck_mode === "random" ? (
              <div>
                <p className="text-xs text-felt-light/80 uppercase tracking-wide mb-1">
                  Total cards ({countMin}–{countMax})
                </p>
                <input
                  type="number"
                  min={countMin}
                  max={countMax}
                  disabled={!isHost}
                  value={settings.card_count ?? 12 * numPlayers}
                  onChange={(e) => patchSettings({ card_count: Number(e.target.value) })}
                  className="w-full rounded-lg bg-white/95 px-3 py-2 text-felt-dark disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
                <p className="text-[11px] text-felt-light/60 mt-1">
                  Leftover cards after an even deal are discarded — no card counting possible.
                </p>
              </div>
            ) : (
              <div>
                <p className="text-xs text-felt-light/80 uppercase tracking-wide mb-1">Copies per number</p>
                <div className="grid grid-cols-2 gap-2">
                  {[4, 5].map((k) => (
                    <button
                      key={k}
                      type="button"
                      disabled={!isHost}
                      onClick={() => patchSettings({ copies: k })}
                      className={`rounded-lg py-2 text-sm font-semibold border transition-colors disabled:cursor-not-allowed ${
                        settings.copies === k
                          ? "bg-amber-400 border-amber-300 text-felt-dark"
                          : "bg-black/20 border-white/15 text-white/80"
                      }`}
                    >
                      {k} copies ({k * 11} cards)
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-felt-light/60 mt-1">All cards are dealt — hands may differ by one card.</p>
              </div>
            )}

            <div>
              <p className="text-xs text-felt-light/80 uppercase tracking-wide mb-1">
                Minimum doubts to win: <span className="text-white font-semibold">{settings.min_doubts}</span>
              </p>
              <input
                type="range"
                min={0}
                max={10}
                disabled={!isHost}
                value={settings.min_doubts}
                onChange={(e) => patchSettings({ min_doubts: Number(e.target.value) })}
                className="w-full accent-amber-400 disabled:opacity-60"
              />
            </div>
          </div>
        </section>

        <div className="text-center">
          {self?.ready ? (
            <div>
              <p className="text-emerald-400 font-semibold mb-1">You're ready!</p>
              {notReady.length > 0 && (
                <p className="text-felt-light/70 text-sm">
                  Waiting on {notReady.map((p) => p.name).join(", ")}…
                </p>
              )}
              {room.players.length < 2 && (
                <p className="text-felt-light/70 text-sm">Waiting for at least one more player…</p>
              )}
            </div>
          ) : (
            <button
              onClick={actions.setPlayerReady}
              className="bg-amber-400 hover:bg-amber-300 text-felt-dark font-bold px-8 py-3 rounded-full text-lg"
            >
              I'm Ready
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
