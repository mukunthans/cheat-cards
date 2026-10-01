import Card from "./Card.jsx";

const OFFSETS = [
  "translate-x-0 translate-y-0",
  "translate-x-1.5 -translate-y-1 rotate-3",
  "-translate-x-1.5 -translate-y-1.5 -rotate-3",
  "translate-x-2 -translate-y-2 rotate-6",
  "-translate-x-2 -translate-y-2.5 -rotate-6",
];

/**
 * Face-down pile at the centre of the table. True values never appear here.
 *
 * The declared-value badge is the most important string on the table, so it gets
 * the gold pill directly above the stack; the card count stays small and quiet.
 */
export default function Pile({ size, declaredValue, lastPlayerName, lastCount, burning = false }) {
  const stackDepth = Math.min(size, 5);
  const hasDeclared = declaredValue !== null && declaredValue !== undefined;

  return (
    <div className="flex flex-col items-center gap-2 sm:gap-3">
      <div className="h-9 flex items-end">
        {hasDeclared ? (
          <div
            key={`${declaredValue}-${size}`}
            className="animate-tick rounded-full border border-gold/60 bg-felt-dark/90 px-4 py-1.5 shadow-gold"
          >
            <span className="text-felt-fog text-xs">Claiming:</span>{" "}
            <span className="font-display font-extrabold text-gold text-xl align-middle">
              {declaredValue}s
            </span>
          </div>
        ) : (
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-felt-fog/60">
            round not started
          </p>
        )}
      </div>

      <div className="relative h-20 sm:h-24 w-16 flex items-center justify-center">
        {burning && (
          <span className="absolute z-10 text-4xl animate-rise-fade pointer-events-none" aria-hidden>
            🔥
          </span>
        )}
        {size === 0 ? (
          <div className="w-14 h-20 rounded-xl border-2 border-dashed border-felt-rail/50 flex items-center justify-center text-felt-fog/40 text-xs">
            empty
          </div>
        ) : (
          Array.from({ length: stackDepth }).map((_, i) => (
            <Card key={i} faceDown size="md" className={`absolute animate-pop-in ${OFFSETS[i]}`} />
          ))
        )}
      </div>

      <div className="text-center space-y-1">
        <p className="font-mono text-xs text-felt-fog/70">
          {size} card{size === 1 ? "" : "s"} in pile
        </p>
        {lastPlayerName && (
          <p className="text-felt-fog/60 text-xs">
            {lastPlayerName} played {lastCount} card{lastCount === 1 ? "" : "s"}
          </p>
        )}
      </div>
    </div>
  );
}
