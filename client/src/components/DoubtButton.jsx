import { useEffect, useState } from "react";

/**
 * Doubt window countdown is cosmetic only (server clock is authoritative);
 * this just mirrors the deadline timestamp the server already sent us.
 */
export default function DoubtButton({ deadline, onDoubt, disabled, playerName }) {
  const [remainingMs, setRemainingMs] = useState(() => (deadline ? deadline - Date.now() : 0));

  useEffect(() => {
    if (!deadline) {
      setRemainingMs(0);
      return;
    }
    setRemainingMs(deadline - Date.now());
    const id = setInterval(() => setRemainingMs(deadline - Date.now()), 100);
    return () => clearInterval(id);
  }, [deadline]);

  const windowOpen = !!deadline && remainingMs > 0;

  if (!windowOpen) return null;

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onDoubt}
      className="relative overflow-hidden rounded-full bg-red-600 hover:bg-red-500 disabled:bg-slate-500 disabled:cursor-not-allowed text-white font-display font-bold text-lg px-8 py-3 shadow-card-lg animate-slide-up"
    >
      <span key={deadline} className="absolute inset-0 bg-white/25 animate-shrink-bar" />
      <span className="relative">
        {disabled ? "Doubt" : `Doubt ${playerName ? `${playerName}!` : "!"}`}
        <span className="ml-2 text-sm font-normal">{Math.ceil(remainingMs / 1000)}s</span>
      </span>
    </button>
  );
}
