import Card from "./Card.jsx";

const CARD_STAGGER_MS = 80;
const FLIP_MS = 600;

/** Doubt resolution — only the doubted cards' true values are ever shown here. */
export default function RevealModal({ reveal, players, onClose }) {
  if (!reveal) return null;

  const nameOf = (id) => players.find((p) => p.id === id)?.name || "Someone";
  const cards = reveal.revealed_cards || [];
  const declared = reveal.declared_value;
  const pileCount = reveal.pile_count;
  const stampDelay = (cards.length - 1) * CARD_STAGGER_MS + FLIP_MS + 250;

  const liar = reveal.was_lie;
  const accent = liar ? "text-lie" : "text-truth";
  const takerName = nameOf(reveal.pile_goes_to);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="bg-felt-dark border border-white/10 rounded-2xl shadow-card-lg max-w-md w-full p-8 text-center animate-pop-in">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-felt-fog/70 mb-6">
          {nameOf(reveal.played_player_id)} claimed{declared !== null && declared !== undefined ? ` ${declared}s` : ""} ·{" "}
          {nameOf(reveal.doubter_id)} doubted
        </p>

        <div className="flex justify-center gap-3 mb-6" style={{ perspective: "800px" }}>
          {cards.map((c, i) => (
            <Card
              key={c.id}
              value={c.value}
              size="lg"
              tone={liar ? (c.value === declared ? null : "lie") : "truth"}
              className="animate-reveal-flip"
              style={{ animationDelay: `${i * CARD_STAGGER_MS}ms` }}
            />
          ))}
        </div>

        <p
          className={`font-display font-extrabold text-6xl tracking-tight mb-5 animate-stamp-in ${accent}`}
          style={{ animationDelay: `${stampDelay}ms` }}
        >
          {liar ? "LIAR!" : "HONEST!"}
        </p>

        <p className="text-ivory/90 text-sm leading-relaxed mb-1">
          {liar ? (
            <>
              {declared !== null && declared !== undefined
                ? `One of those wasn't a ${declared}. `
                : "That play was a bluff. "}
              <span className="font-semibold">{takerName}</span> scoops up
              {pileCount ? ` all ${pileCount} cards` : " the pile"}.
            </>
          ) : (
            <>
              {declared !== null && declared !== undefined
                ? `Those were really ${declared}s. `
                : "The play was honest. "}
              <span className="font-semibold">{nameOf(reveal.doubter_id)}</span> doubted a straight
              shooter — they take
              {pileCount ? ` all ${pileCount} cards` : " the pile"}.
            </>
          )}
        </p>
        <p className="text-felt-fog/70 text-xs mb-7">
          {nameOf(reveal.new_starter_id)} starts the next round.
        </p>

        <button
          type="button"
          onClick={onClose}
          className="h-12 px-8 rounded-full bg-gold hover:bg-gold-300 text-ink font-semibold transition-colors"
        >
          Next round
        </button>
      </div>
    </div>
  );
}
