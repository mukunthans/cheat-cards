import { useLayoutEffect, useRef, useState } from "react";
import Card from "./Card.jsx";

const FALLBACK_CARD_W = 72; // Card size "lg" before it is measured
const MAX_STEP = 52; // the design's -mr-5 fan overlap
const MIN_STEP = 22; // enough sliver to keep each card's corner index readable
const GUTTER = 8; // safety margin so the fan never trips the scrollbar

/**
 * The player's own hand — the only cards whose true values this client ever sees.
 *
 * The fan opens to the design's -mr-5 overlap when there is room and tightens as the
 * hand grows, so a 15-card fixed-deck hand still lands inside a 390px table instead
 * of running off the edge. It only scrolls once even the tightest fan overflows.
 */
export default function Hand({ cards, selected, onToggle, disabled = false, maxSelect = 4 }) {
  const wrapRef = useRef(null);
  const [{ width, cardW }, setBox] = useState({ width: 0, cardW: FALLBACK_CARD_W });

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    // contentRect is the padding-excluded box, which is exactly the room the fan has.
    const measure = (rect) => {
      const first = el.querySelector("button");
      setBox({
        width: rect ? rect.width : el.clientWidth,
        cardW: first?.offsetWidth || FALLBACK_CARD_W,
      });
    };
    const ro = new ResizeObserver(([entry]) => measure(entry.contentRect));
    ro.observe(el);
    measure(null);
    return () => ro.disconnect();
  }, [cards.length]);

  if (!cards.length) {
    return <p className="text-center text-felt-fog/70 text-sm py-8 italic font-display">Your hand is empty.</p>;
  }

  const n = cards.length;
  const fit = width > 0 && n > 1 ? (width - cardW - GUTTER) / (n - 1) : MAX_STEP;
  const step = Math.round(Math.max(MIN_STEP, Math.min(MAX_STEP, fit)));
  // Once the fan is tighter than this, a centred numeral is only ever seen as a
  // clipped sliver, so the corner index carries the card on its own.
  const indexOnly = step < 44;

  return (
    <div ref={wrapRef} className="overflow-x-auto py-3">
      <div className="flex justify-center w-max min-w-full">
        {cards.map((card, i) => {
          const isSelected = selected.includes(card.id);
          const blocked = disabled || (!isSelected && selected.length >= maxSelect);
          return (
            <button
              key={card.id}
              type="button"
              disabled={blocked}
              onClick={() => onToggle(card.id)}
              aria-pressed={isSelected}
              style={{
                marginRight: i === n - 1 ? 0 : step - cardW,
                animationDelay: `${Math.min(i, 12) * 35}ms`,
              }}
              className={`shrink-0 animate-deal-in rounded-xl transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-gold ${
                isSelected ? "z-20" : "z-10 hover:z-20"
              } ${blocked ? "cursor-not-allowed" : "cursor-pointer hover:-translate-y-1"}`}
            >
              <Card value={card.value} selected={isSelected} disabled={blocked && !isSelected} size="lg" corner indexOnly={indexOnly} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
