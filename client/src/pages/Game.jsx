import { useEffect, useState } from "react";
import PlayerList from "../components/PlayerList.jsx";
import Pile from "../components/Pile.jsx";
import Hand from "../components/Hand.jsx";
import DoubtButton from "../components/DoubtButton.jsx";
import DeclareBar from "../components/DeclareBar.jsx";
import RevealModal from "../components/RevealModal.jsx";

export default function Game({
  room,
  roomCode,
  selfId,
  hand,
  turn,
  pile,
  reveal,
  burned,
  gameOver,
  disconnected,
  actions,
  onLeave,
}) {
  const [selected, setSelected] = useState([]);
  const [declaredValue, setDeclaredValue] = useState(null);
  const [, forceTick] = useState(0);

  const self = room.players.find((p) => p.id === selfId);
  const minDoubts = room.settings?.min_doubts ?? 0;
  const isMyTurn = turn.activePlayerId === selfId;
  const roundInProgress = turn.roundDeclaredValue !== null && turn.roundDeclaredValue !== undefined;
  const mustDeclare = isMyTurn && !roundInProgress;

  const nameOf = (id) => room.players.find((p) => p.id === id)?.name || "Someone";

  useEffect(() => {
    setSelected((prev) => prev.filter((id) => hand.some((c) => c.id === id)));
  }, [hand]);

  useEffect(() => {
    if (!isMyTurn) {
      setSelected([]);
      setDeclaredValue(null);
    }
  }, [isMyTurn]);

  useEffect(() => {
    const hasGrace = Object.keys(disconnected || {}).length > 0;
    if (!hasGrace) return;
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [disconnected]);

  const wouldEmptyHand = selected.length > 0 && selected.length === hand.length;
  const myDoubtsMade = self?.doubts_made ?? 0;
  const quotaBlocked = wouldEmptyHand && myDoubtsMade < minDoubts;
  const canPlay =
    isMyTurn && selected.length >= 1 && selected.length <= 4 && (!mustDeclare || declaredValue !== null) && !quotaBlocked;
  const canPass = isMyTurn && roundInProgress;

  function toggleCard(id) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]));
  }

  function handlePlay() {
    if (!canPlay) return;
    actions.playCards(selected, mustDeclare ? declaredValue : undefined);
    setSelected([]);
    setDeclaredValue(null);
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-felt-dark to-felt flex flex-col">
      <header className="flex items-center justify-between px-4 py-3">
        <div>
          <p className="text-felt-light/60 text-[11px] uppercase tracking-wide">Room</p>
          <p className="text-white font-mono font-bold tracking-widest">{roomCode}</p>
        </div>
        <div className="text-center">
          <p className="text-white text-sm font-semibold">
            Your doubts: {myDoubtsMade}/{minDoubts}
          </p>
        </div>
        <button onClick={onLeave} className="text-felt-light/70 hover:text-white text-sm underline">
          Leave
        </button>
      </header>

      {Object.keys(disconnected || {}).length > 0 && (
        <div className="px-4 pb-2 flex flex-col gap-1">
          {Object.entries(disconnected).map(([pid, deadline]) => {
            const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
            return (
              <div
                key={pid}
                className="bg-red-950/60 border border-red-500/30 text-red-200 text-xs rounded-lg px-3 py-1.5 text-center"
              >
                {nameOf(pid)} disconnected — holding seat for {left}s
              </div>
            );
          })}
        </div>
      )}

      <div className="px-4 pb-3">
        <PlayerList
          players={room.players}
          hostId={room.host_id}
          activePlayerId={turn.activePlayerId}
          selfId={selfId}
          minDoubts={minDoubts}
          disconnected={disconnected}
        />
      </div>

      <main className="flex-1 flex flex-col items-center justify-center gap-4 px-4">
        <Pile
          size={pile.size}
          declaredValue={turn.roundDeclaredValue}
          lastPlayerName={pile.lastPlayerId ? nameOf(pile.lastPlayerId) : null}
          lastCount={pile.lastCount}
        />

        <p className="text-white/90 text-sm font-medium min-h-[1.25rem]">
          {isMyTurn
            ? mustDeclare
              ? "Your turn — play 1–4 cards and declare a value"
              : "Your turn — play 1–4 cards or pass"
            : `${nameOf(turn.activePlayerId)}'s turn`}
        </p>

        {pile.lastPlayerId && pile.lastPlayerId !== selfId && (
          <DoubtButton
            deadline={pile.doubtDeadline}
            onDoubt={actions.callDoubt}
            playerName={nameOf(pile.lastPlayerId)}
          />
        )}

        {burned && (
          <p className="text-amber-300 text-sm bg-black/30 rounded-full px-4 py-1 animate-slide-up">
            🔥 Pile burned ({burned.burned_count} cards) — {nameOf(burned.new_starter_id)} starts a new round
          </p>
        )}
      </main>

      <footer className="bg-black/30 border-t border-white/10 px-4 py-4">
        {mustDeclare && <DeclareBar value={declaredValue} onChange={setDeclaredValue} />}

        <Hand cards={hand} selected={selected} onToggle={toggleCard} disabled={!isMyTurn} />

        {quotaBlocked && (
          <p className="text-center text-red-400 text-xs mb-2">
            You need {minDoubts - myDoubtsMade} more doubt{minDoubts - myDoubtsMade === 1 ? "" : "s"} before you
            can play your last cards.
          </p>
        )}

        <div className="flex justify-center gap-3 mt-2">
          <button
            type="button"
            disabled={!canPlay}
            onClick={handlePlay}
            className="bg-amber-400 hover:bg-amber-300 disabled:bg-white/10 disabled:text-white/30 disabled:cursor-not-allowed text-felt-dark font-bold px-6 py-2.5 rounded-full"
          >
            Play {selected.length > 0 ? `(${selected.length})` : ""}
          </button>
          <button
            type="button"
            disabled={!canPass}
            onClick={actions.passTurn}
            className="bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed text-white font-bold px-6 py-2.5 rounded-full"
          >
            Pass
          </button>
        </div>
      </footer>

      <RevealModal reveal={reveal} players={room.players} onClose={actions.dismissReveal} />

      {gameOver && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="bg-felt-dark border border-amber-400/40 rounded-2xl shadow-card-lg max-w-sm w-full p-8 text-center animate-pop-in">
            <p className="text-5xl mb-3">🏆</p>
            <p className="text-2xl font-display font-bold text-amber-300 mb-1">{gameOver.winner_name} wins!</p>
            <p className="text-felt-light/80 text-sm mb-6">
              {gameOver.reason === "forfeit" ? "Won by forfeit — everyone else disconnected." : "Emptied their hand with quota met."}
            </p>
            <button
              onClick={onLeave}
              className="bg-amber-400 hover:bg-amber-300 text-felt-dark font-bold px-6 py-2.5 rounded-full"
            >
              Back to Home
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
