import { useState } from "react";

export default function FlashCard({ card }) {
  const [flipped, setFlipped] = useState(false);

  return (
    <div
      className="card-scene cursor-pointer"
      style={{ height: "180px" }}
      onClick={() => setFlipped((f) => !f)}
    >
      <div className={`card-3d ${flipped ? "flipped" : ""}`}>
        {/* Front — Question */}
        <div
          className="card-face bg-fl-card border border-fl-border rounded-xl p-5 flex flex-col"
          style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
        >
          {card.topic && (
            <span className="inline-block self-start px-2.5 py-0.5 rounded-full bg-fl-yellow text-fl-black text-[10px] font-sans font-semibold uppercase tracking-wider mb-3">
              {card.topic}
            </span>
          )}
          <p className="text-[11px] font-sans font-medium text-fl-muted uppercase tracking-wider mb-2">Question</p>
          <p className="text-sm font-sans text-fl-black leading-snug line-clamp-4">{card.question}</p>
          <p className="mt-auto text-[10px] text-fl-muted font-sans pt-2">Tap to reveal →</p>
        </div>

        {/* Back — Answer */}
        <div
          className="card-face card-face-back bg-fl-yellow border border-fl-yellow rounded-xl p-5 flex flex-col"
          style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
        >
          <p className="text-[11px] font-sans font-medium text-fl-black/60 uppercase tracking-wider mb-2">Answer</p>
          <p className="text-sm font-sans text-fl-black leading-snug line-clamp-4">{card.answer}</p>
          <p className="mt-auto text-[10px] text-fl-black/50 font-sans pt-2">Tap to flip back</p>
        </div>
      </div>
    </div>
  );
}
