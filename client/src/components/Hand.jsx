import Card from "./Card.jsx";

/** The player's own hand — the only place true values are ever shown for cards you don't own. */
export default function Hand({ cards, selected, onToggle, disabled = false, maxSelect = 4 }) {
  if (!cards.length) {
    return <p className="text-center text-felt-light/70 text-sm py-6">Your hand is empty.</p>;
  }
  return (
    <div className="flex flex-wrap justify-center gap-2 py-2">
      {cards.map((card) => {
        const isSelected = selected.includes(card.id);
        const blocked = disabled || (!isSelected && selected.length >= maxSelect);
        return (
          <button
            key={card.id}
            type="button"
            disabled={blocked}
            onClick={() => onToggle(card.id)}
            className={`disabled:cursor-not-allowed disabled:opacity-60 ${!disabled ? "cursor-pointer" : ""}`}
            aria-pressed={isSelected}
          >
            <Card value={card.value} selected={isSelected} size="lg" />
          </button>
        );
      })}
    </div>
  );
}
