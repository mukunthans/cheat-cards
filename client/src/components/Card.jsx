const SIZES = {
  sm: "w-10 h-14 text-base",
  md: "w-14 h-20 text-2xl",
  lg: "w-16 h-24 text-3xl",
};

/** A single playing card face. Face-down cards never reveal `value` (server never sends it). */
export default function Card({ value, faceDown = false, selected = false, size = "md", className = "" }) {
  const dims = SIZES[size] || SIZES.md;
  if (faceDown) {
    return (
      <div
        className={`${dims} rounded-lg border-2 border-white/20 bg-gradient-to-br from-felt-light to-felt-dark shadow-card flex items-center justify-center shrink-0 ${className}`}
      >
        <div className="w-2/3 h-2/3 rounded border border-white/10 bg-[repeating-linear-gradient(45deg,rgba(255,255,255,0.06)_0px,rgba(255,255,255,0.06)_4px,transparent_4px,transparent_8px)]" />
      </div>
    );
  }
  return (
    <div
      className={`${dims} rounded-lg border-2 bg-white text-felt-dark shadow-card flex items-center justify-center font-display font-bold shrink-0 transition-transform ${
        selected ? "border-amber-400 -translate-y-2 shadow-card-lg" : "border-slate-300"
      } ${className}`}
    >
      {value}
    </div>
  );
}
