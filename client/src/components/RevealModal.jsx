import Card from "./Card.jsx";

/** Doubt resolution — only the doubted cards' true values are ever shown here. */
export default function RevealModal({ reveal, players, onClose }) {
  if (!reveal) return null;
  const nameOf = (id) => players.find((p) => p.id === id)?.name || "Someone";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-felt-dark border border-white/15 rounded-2xl shadow-card-lg max-w-sm w-full p-6 text-center animate-pop-in">
        <p
          className={`text-2xl font-display font-bold mb-1 ${
            reveal.was_lie ? "text-red-400" : "text-emerald-400"
          }`}
        >
          {reveal.was_lie ? "It was a LIE!" : "They told the truth!"}
        </p>
        <p className="text-felt-light/90 text-sm mb-4">
          {nameOf(reveal.doubter_id)} doubted {nameOf(reveal.played_player_id)}
        </p>

        <div className="flex justify-center gap-2 mb-4">
          {reveal.revealed_cards.map((c) => (
            <Card key={c.id} value={c.value} size="lg" className="animate-flip-in" />
          ))}
        </div>

        <p className="text-white text-sm mb-5">
          <span className="font-semibold">{nameOf(reveal.pile_goes_to)}</span> picks up the pile.
          <br />
          <span className="text-felt-light/80">
            {nameOf(reveal.new_starter_id)} starts the next round.
          </span>
        </p>

        <button
          type="button"
          onClick={onClose}
          className="bg-amber-400 hover:bg-amber-300 text-felt-dark font-bold px-5 py-2 rounded-full"
        >
          Continue
        </button>
      </div>
    </div>
  );
}
