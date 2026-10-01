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
  // "Let it ride" is a local choice not to doubt — there is no server event for
  // declining, and the window still closes on the server's own clock.
  const [rideOut, setRideOut] = useState(null); // doubt deadline the player waved off
  const [nowTs, setNowTs] = useState(() => Date.now());

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

  // Retire the whole doubt prompt — button and "let it ride" alike — the moment the
  // window lapses, so no half-open affordance is left on screen. The server's clock
  // still decides; this only stops offering an action that would be rejected.
  useEffect(() => {
    if (!pile.doubtDeadline) return;
    setNowTs(Date.now());
    const id = setInterval(() => setNowTs(Date.now()), 200);
    return () => clearInterval(id);
  }, [pile.doubtDeadline]);

  const wouldEmptyHand = selected.length > 0 && selected.length === hand.length;
  const myDoubtsMade = self?.doubts_made ?? 0;
  const doubtsLeft = Math.max(0, minDoubts - myDoubtsMade);
  const quotaBlocked = wouldEmptyHand && myDoubtsMade < minDoubts;
  const canPlay =
    isMyTurn &&
    selected.length >= 1 &&
    selected.length <= 4 &&
    (!mustDeclare || declaredValue !== null) &&
    !quotaBlocked;
  const canPass = isMyTurn && roundInProgress;

  const claimValue = mustDeclare ? declaredValue : turn.roundDeclaredValue;
  const doubtOpen =
    !!pile.doubtDeadline &&
    pile.doubtDeadline > nowTs &&
    !!pile.lastPlayerId &&
    pile.lastPlayerId !== selfId &&
    rideOut !== pile.doubtDeadline;

  function toggleCard(id) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]));
  }

  function handlePlay() {
    if (!canPlay) return;
    actions.playCards(selected, mustDeclare ? declaredValue : undefined);
    setSelected([]);
    setDeclaredValue(null);
  }

  const playLabel = () => {
    if (!selected.length) return "Play";
    if (wouldEmptyHand) return `Play last card${selected.length > 1 ? "s" : ""}`;
    if (claimValue !== null && claimValue !== undefined)
      return `Play ${selected.length} as ${claimValue}s`;
    return `Play ${selected.length}`;
  };

  return (
    <div className="min-h-screen bg-felt-table flex flex-col">
      <header className="flex items-center justify-between gap-4 px-4 sm:px-10 py-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-felt-fog/60">Room</p>
          <p className="font-mono text-ivory tracking-[0.18em]">{roomCode}</p>
        </div>
        <div
          className={`rounded-full border px-4 py-1.5 font-mono text-xs ${
            doubtsLeft === 0 ? "border-truth/40 text-truth" : "border-white/15 text-felt-fog"
          }`}
        >
          doubts {myDoubtsMade}/{minDoubts}
          {doubtsLeft === 0 && " ✓"}
        </div>
        <button
          onClick={onLeave}
          className="h-12 px-3 text-felt-fog/70 hover:text-ivory text-sm transition-colors"
        >
          Leave
        </button>
      </header>

      <div className="px-4 sm:px-10 pb-4">
        <PlayerList
          players={room.players}
          hostId={room.host_id}
          activePlayerId={turn.activePlayerId}
          selfId={selfId}
          minDoubts={minDoubts}
          disconnected={disconnected}
        />
      </div>

      <main className="flex-1 flex flex-col items-center justify-center gap-4 sm:gap-6 px-4 py-2 sm:py-4">
        <Pile
          size={pile.size}
          declaredValue={turn.roundDeclaredValue}
          lastPlayerName={pile.lastPlayerId ? nameOf(pile.lastPlayerId) : null}
          lastCount={pile.lastCount}
          burning={!!burned}
        />

        <p className="font-display italic text-lg text-ivory/90 text-center min-h-[1.75rem]">
          {isMyTurn
            ? mustDeclare
              ? "Your move — kick off a round"
              : "Your move"
            : `${nameOf(turn.activePlayerId)}'s move…`}
        </p>

        {doubtOpen && (
          <div className="flex flex-col items-center gap-3 animate-slide-up">
            <DoubtButton deadline={pile.doubtDeadline} onDoubt={actions.callDoubt} />
            <p className="font-display italic text-sm text-felt-fog/70">
              or trust them and let it ride —
            </p>
            <button
              type="button"
              onClick={() => setRideOut(pile.doubtDeadline)}
              className="h-12 px-6 rounded-full border border-white/15 text-felt-fog hover:text-ivory hover:border-white/30 text-sm transition-colors"
            >
              Let it ride
            </button>
          </div>
        )}
      </main>

      <footer className="border-t border-white/10 bg-felt-void/60 px-4 sm:px-10 pt-3 pb-5 sm:pt-4 sm:pb-6">
        {mustDeclare && (
          <div className="mb-3">
            <DeclareBar value={declaredValue} onChange={setDeclaredValue} />
          </div>
        )}

        <Hand cards={hand} selected={selected} onToggle={toggleCard} disabled={!isMyTurn} />

        {quotaBlocked && (
          <p className="flex items-center justify-center gap-2 text-center text-lie text-sm mb-3">
            <span aria-hidden>✋</span>
            You need {doubtsLeft} more doubt{doubtsLeft === 1 ? "" : "s"} before you can play your last
            card{hand.length === 1 ? "" : "s"}.
          </p>
        )}

        <div className="flex justify-center gap-3 mt-1">
          <button
            type="button"
            disabled={!canPlay}
            onClick={handlePlay}
            className="h-12 px-7 rounded-full bg-gold hover:bg-gold-300 disabled:bg-white/5 disabled:text-felt-fog/30 disabled:shadow-none text-ink font-semibold shadow-gold transition-colors"
          >
            {playLabel()}
          </button>
          <button
            type="button"
            disabled={!canPass}
            onClick={actions.passTurn}
            className="h-12 px-7 rounded-full border border-white/15 text-ivory hover:border-white/30 disabled:opacity-25 disabled:cursor-not-allowed font-semibold transition-colors"
          >
            Pass
          </button>
        </div>
      </footer>

      <RevealModal reveal={reveal} players={room.players} onClose={actions.dismissReveal} />

      {gameOver && (
        <GameOver gameOver={gameOver} players={room.players} onLeave={onLeave} />
      )}
    </div>
  );
}

function GameOver({ gameOver, players, onLeave }) {
  const winner = players.find((p) => p.id === gameOver.winner_id);
  const seatIndex = Math.max(0, players.findIndex((p) => p.id === gameOver.winner_id));
  const seatColor = ["bg-seat-1", "bg-seat-2", "bg-seat-3", "bg-seat-4"][seatIndex % 4];
  const forfeit = gameOver.reason === "forfeit";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="relative overflow-hidden rounded-2xl border border-gold/30 bg-felt-dark shadow-card-lg max-w-md w-full px-8 py-10 text-center animate-pop-in">
        {!forfeit &&
          [12, 34, 56, 74, 88].map((left, i) => (
            <span
              key={left}
              aria-hidden
              className="absolute top-0 w-1.5 h-1.5 rounded-full bg-gold/70 animate-fall-gold"
              style={{ left: `${left}%`, animationDelay: `${i * 420}ms` }}
            />
          ))}

        {!forfeit && <p className="text-gold tracking-[0.4em] mb-4">★ ★ ★</p>}

        <p className="font-display font-extrabold text-4xl text-ivory mb-2 animate-pop-in">
          {gameOver.winner_name} wins{forfeit ? " by forfeit" : " the table!"}
        </p>
        <p className="font-display italic text-felt-fog mb-8">
          {forfeit
            ? "Everyone else wandered off. Last one at the table takes it — quota waived."
            : "Hand empty, quota met — clean sweep."}
        </p>

        <div
          className={`mx-auto w-20 h-20 rounded-full flex items-center justify-center text-white text-xl font-semibold shadow-gold mb-8 ${seatColor}`}
        >
          {(winner?.name || gameOver.winner_name || "?").trim().slice(0, 2).toUpperCase()}
        </div>

        <button
          type="button"
          onClick={onLeave}
          className="h-12 px-8 rounded-full bg-gold hover:bg-gold-300 text-ink font-semibold transition-colors"
        >
          Leave table
        </button>
      </div>
    </div>
  );
}
