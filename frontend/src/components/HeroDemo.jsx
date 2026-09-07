import { useEffect, useState } from "react";

/**
 * The hero's animated flashcard: the product doing its one thing, on a loop.
 *
 * This replaces a static row of three sample questions. A flashcard's whole
 * point is the reveal, and a still image of one can't show that — so the
 * landing page was describing the interaction in prose next to a picture of it
 * not happening.
 */
const CARDS = [
  {
    topic: "Biology",
    q: "What do mitochondria do?",
    a: "Generate ATP through cellular respiration — the usable energy the rest of the cell runs on.",
  },
  {
    topic: "Physics",
    q: "State Newton's second law",
    a: "The force on a body equals its mass times its acceleration: F = ma.",
  },
  {
    topic: "Chemistry",
    q: "What makes two atoms isotopes?",
    a: "Same element and the same number of protons, but a different number of neutrons.",
  },
];

// Long enough to actually read the side that is showing. Anything quicker
// reads as a flickering advert rather than a card being studied.
const DWELL_MS = 2800;

export default function HeroDemo() {
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [paused, setPaused] = useState(false);
  const reduced = usePrefersReducedMotion();
  const card = CARDS[index];

  useEffect(() => {
    if (reduced || paused) return;

    const timer = setTimeout(() => {
      if (flipped) {
        // Advance with the flip back rather than after it. The front face is
        // hidden for the first half of the rotation, so the next question is
        // already in place by the time it becomes visible — swapping it after
        // the transition would instead show the old question, then blink.
        setFlipped(false);
        setIndex((i) => (i + 1) % CARDS.length);
      } else {
        setFlipped(true);
      }
    }, DWELL_MS);

    return () => clearTimeout(timer);
  }, [flipped, paused, reduced]);

  // Reduced motion gets the same content with nothing moving: both sides at
  // once, which is the only honest still frame of a card that flips.
  if (reduced) {
    return (
      <div className="surface mx-auto w-full max-w-sm p-6 shadow-lift">
        <span className="badge badge-primary badge-sm font-medium">{card.topic}</span>
        <p className="mt-4 text-lg font-medium leading-snug">{card.q}</p>
        <p className="mt-4 border-t border-base-300 pt-4 text-sm leading-relaxed text-base-content/70">
          {card.a}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-sm">
      {/* Hovering pauses: the card is readable content, and text that flips
          away mid-sentence because you stopped to read it is a small hostility.
          Focus counts too, for anyone tabbing through. */}
      <div
        className="card-scene animate-float h-64"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocus={() => setPaused(true)}
        onBlur={() => setPaused(false)}
      >
        <div className={`card-3d ${flipped ? "flipped" : ""}`}>
          <div className="card-face surface flex flex-col p-6 shadow-lift">
            <span className="badge badge-primary badge-sm font-medium">
              {card.topic}
            </span>
            <p className="mt-4 text-lg font-medium leading-snug">{card.q}</p>
            <span className="mt-auto text-xs text-base-content/40">
              Tap to reveal
            </span>
          </div>

          <div className="card-face card-face-back surface flex flex-col bg-primary p-6 shadow-lift">
            <span className="text-xs font-semibold uppercase tracking-wider text-primary-content/60">
              Answer
            </span>
            <p className="mt-3 text-base leading-relaxed text-primary-content">
              {card.a}
            </p>
          </div>
        </div>
      </div>

      {/* Which of the three is showing. Decorative — the cards themselves are
          announced by the live region below. */}
      <div className="mt-6 flex justify-center gap-2" aria-hidden="true">
        {CARDS.map((c, i) => (
          <span
            key={c.q}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              i === index ? "w-6 bg-primary" : "w-1.5 bg-base-300"
            }`}
          />
        ))}
      </div>

      {/* The animation is decoration, so it is not narrated as it happens.
          This gives a screen reader the sample content once, statically. */}
      <p className="sr-only">
        Example flashcard. {card.topic}. {card.q} {card.a}
      </p>
    </div>
  );
}

/**
 * Tracks the OS "reduce motion" setting.
 *
 * The stylesheet already neutralises CSS animations under this preference, but
 * the flip here is driven by a timer — CSS can't switch that off, so a user who
 * asked for less movement would still get a card rearranging itself every few
 * seconds.
 */
function usePrefersReducedMotion() {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );

  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = (e) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
