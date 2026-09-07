import { useState } from "react";

export default function FlashCard({ card }) {
  const [flipped, setFlipped] = useState(false);

  return (
    <div
      className="card-scene h-44 cursor-pointer"
      onClick={() => setFlipped((f) => !f)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setFlipped((f) => !f);
        }
      }}
      aria-label={flipped ? "Show question" : "Show answer"}
    >
      <div className={`card-3d ${flipped ? "flipped" : ""}`}>
        {/* Front — question */}
        <div className="card-face surface flex flex-col p-5 shadow-subtle">
          {card.topic && (
            <span className="badge badge-ghost badge-sm self-start font-medium">
              {card.topic}
            </span>
          )}
          <p className="mt-3 line-clamp-4 text-sm leading-snug">{card.question}</p>
          <p className="mt-auto pt-2 text-xs text-base-content/40">Tap to reveal →</p>
        </div>

        {/* Back — answer */}
        <div className="card-face card-face-back flex flex-col rounded-xl bg-primary p-5 text-primary-content shadow-subtle">
          <p className="text-xs font-medium uppercase tracking-wider text-primary-content/60">
            Answer
          </p>
          <p className="mt-2 line-clamp-4 text-sm leading-snug">{card.answer}</p>
          <p className="mt-auto pt-2 text-xs text-primary-content/60">Tap to flip back</p>
        </div>
      </div>
    </div>
  );
}
