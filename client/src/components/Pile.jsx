import Card from "./Card.jsx";

const OFFSETS = [
  "translate-x-0 translate-y-0",
  "translate-x-1.5 -translate-y-1 rotate-3",
  "-translate-x-1.5 -translate-y-1.5 -rotate-3",
  "translate-x-2 -translate-y-2 rotate-6",
  "-translate-x-2 -translate-y-2.5 -rotate-6",
];

/** Face-down pile in the center of the table. True values never appear here. */
export default function Pile({ size, declaredValue, lastPlayerName, lastCount }) {
  const stackDepth = Math.min(size, 5);
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-24 w-16 flex items-center justify-center">
        {size === 0 ? (
          <div className="w-14 h-20 rounded-lg border-2 border-dashed border-white/25 flex items-center justify-center text-white/30 text-xs">
            empty
          </div>
        ) : (
          Array.from({ length: stackDepth }).map((_, i) => (
            <Card key={i} faceDown size="md" className={`absolute animate-pop-in ${OFFSETS[i]}`} />
          ))
        )}
      </div>
      <div className="text-center">
        <p className="text-white font-semibold">{size} card{size === 1 ? "" : "s"} in pile</p>
        {declaredValue !== null && declaredValue !== undefined && (
          <p className="text-amber-300 text-sm">
            Round value locked: <span className="font-bold">{declaredValue}</span>
          </p>
        )}
        {lastPlayerName && (
          <p className="text-felt-light/80 text-xs mt-1">
            {lastPlayerName} played {lastCount} card{lastCount === 1 ? "" : "s"}
          </p>
        )}
      </div>
    </div>
  );
}
