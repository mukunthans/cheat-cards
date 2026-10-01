const VALUES = Array.from({ length: 11 }, (_, i) => i); // 0..10

/**
 * Shown only when starting a round — the declared value locks for the whole round.
 * Occupies the DoubtButton's slot; the two never appear at the same time.
 */
export default function DeclareBar({ value, onChange }) {
  return (
    <div className="flex flex-col items-center gap-2.5">
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-gold">Declare value</p>
      <div className="flex flex-wrap justify-center gap-2 max-w-[340px]">
        {VALUES.map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            aria-pressed={value === v}
            className={`w-12 h-12 rounded-full font-display font-extrabold text-xl border transition-all duration-150 ${
              value === v
                ? "bg-gold border-gold text-ink scale-110 shadow-gold"
                : "bg-black/30 border-white/15 text-ivory hover:border-gold/50 hover:bg-black/45"
            }`}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}
