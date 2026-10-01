const SIZES = {
  sm: "w-10 h-14 text-lg rounded-lg", // 40x56 — opponent stacks
  md: "w-14 h-20 text-2xl rounded-xl", // 56x80 — pile
  lg: "w-[72px] h-[104px] text-4xl rounded-xl sm:w-16 sm:h-24 sm:text-3xl", // own hand
};

/**
 * A single playing card face. Face-down cards never reveal `value` — the server
 * never sends one for a card you don't own.
 *
 * Numerals are Alegreya, never Work Sans: they should read as stamped, not typed.
 */
export default function Card({
  value,
  faceDown = false,
  selected = false,
  disabled = false,
  size = "md",
  tone = null, // "lie" | "truth" — reveal modal only
  corner = false, // adds a top-left index so the card reads while fanned
  indexOnly = false, // tight fan: the corner index is the whole card, no centre numeral
  className = "",
  style,
}) {
  const dims = SIZES[size] || SIZES.md;

  if (faceDown) {
    return (
      <div
        style={style}
        className={`${dims} border border-felt-rail/60 bg-gradient-to-br from-felt-light to-felt-dark shadow-card flex items-center justify-center shrink-0 ${className}`}
      >
        <div className="w-2/3 h-2/3 rounded border border-gold/20 bg-weave" />
      </div>
    );
  }

  const border = tone
    ? tone === "lie"
      ? "border-lie shadow-card-lg"
      : "border-truth shadow-card-lg"
    : selected
      ? "border-gold shadow-gold -translate-y-2"
      : "border-black/10";

  return (
    <div
      style={style}
      className={`${dims} relative border-2 bg-ivory text-ink shadow-card flex items-center justify-center font-display font-extrabold leading-none shrink-0 transition-transform duration-150 ${border} ${
        disabled ? "opacity-45 saturate-50" : ""
      } ${className}`}
    >
      {corner && (
        <span
          className={`absolute top-1 left-1 leading-none tracking-tighter ${
            indexOnly ? "text-base" : "text-xs"
          }`}
        >
          {value}
        </span>
      )}
      {!indexOnly && value}
    </div>
  );
}
