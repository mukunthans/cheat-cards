import { useEffect, useRef, useState } from "react";

const R = 58;
const CIRC = 2 * Math.PI * R;

/**
 * The doubt window countdown is cosmetic only — the server clock is authoritative
 * and closes the window itself. This mirrors the `doubt_deadline_ts` the server
 * already sent us, ticking the ring on rAF rather than a client-only setTimeout.
 */
export default function DoubtButton({ deadline, onDoubt, disabled = false }) {
  const ringRef = useRef(null);
  const labelRef = useRef(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!deadline) {
      setOpen(false);
      return;
    }
    setOpen(deadline - Date.now() > 0);

    let raf = 0;
    const total = 5000; // DOUBT_WINDOW_MS on the server
    const tick = () => {
      const left = deadline - Date.now();
      if (left <= 0) {
        setOpen(false);
        return;
      }
      const frac = Math.min(1, left / total);
      if (ringRef.current) ringRef.current.style.strokeDashoffset = String(CIRC * (1 - frac));
      if (labelRef.current) labelRef.current.textContent = `${Math.ceil(left / 1000)}s`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [deadline]);

  if (!open) return null;

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onDoubt}
      className="relative w-32 h-32 shrink-0 rounded-full animate-pop-in disabled:opacity-40 disabled:cursor-not-allowed"
      aria-label="Call doubt"
    >
      <svg className="absolute inset-0 -rotate-90" viewBox="0 0 128 128" aria-hidden>
        <circle cx="64" cy="64" r={R} fill="none" stroke="rgba(0,0,0,0.35)" strokeWidth="5" />
        <circle
          ref={ringRef}
          cx="64"
          cy="64"
          r={R}
          fill="none"
          stroke="#e5484d"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset="0"
        />
      </svg>
      <span className="absolute inset-[12px] rounded-full bg-lie hover:brightness-110 transition-[filter] flex flex-col items-center justify-center shadow-card-lg">
        <span className="font-display font-extrabold text-white text-2xl tracking-wide leading-none">
          DOUBT
        </span>
        <span ref={labelRef} className="font-mono text-white/80 text-sm mt-1">
          5s
        </span>
      </span>
    </button>
  );
}
