const VALUES = Array.from({ length: 11 }, (_, i) => i); // 0..10

/** Shown only when starting a new round — the declared value locks for the whole round. */
export default function DeclareBar({ value, onChange }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <p className="text-xs text-felt-light/80 uppercase tracking-wide">Declare a value for this round</p>
      <div className="flex flex-wrap justify-center gap-1.5 max-w-xs">
        {VALUES.map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            className={`w-8 h-8 rounded-full text-sm font-bold border transition-colors ${
              value === v
                ? "bg-amber-400 border-amber-300 text-felt-dark"
                : "bg-black/25 border-white/15 text-white hover:bg-black/40"
            }`}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}
