import { useCallback, useEffect, useRef, useState } from "react";
import { regenerateFlashcards, reviewFlashcard } from "../api.js";
import { useToast } from "../toast.jsx";

export default function StudyMode({ cards: initialCards, docId, onStartQuiz, onBack, onReloadCards }) {
  const [cards, setCards] = useState(initialCards);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [known, setKnown] = useState(new Set());
  const [regenLoading, setRegenLoading] = useState(false);
  const toast = useToast();
  const regenModal = useRef(null);
  // When the current card was first shown, so a self-grade carries a response
  // time. Feeds response_time_ms on the interaction the backend records.
  const shownAt = useRef(Date.now());

  useEffect(() => {
    setCards(initialCards);
    setIndex(0);
    setFlipped(false);
    setKnown(new Set());
  }, [initialCards]);

  const total = cards.length;
  const card = cards[index];
  const knownCount = known.size;
  const allKnown = knownCount === total && total > 0;

  useEffect(() => {
    shownAt.current = Date.now();
  }, [index, cards]);

  // Persist the self-grade. Deliberately not awaited: recording history must
  // never make the card advance feel slow, and a lost review is not worth
  // interrupting a study session over.
  const recordReview = (cardId, isKnown) => {
    const elapsed = Date.now() - shownAt.current;
    reviewFlashcard(cardId, isKnown, elapsed).catch((err) => {
      console.warn("Failed to record review", err);
    });
  };

  const goNext = useCallback(() => {
    setFlipped(false);
    setIndex((i) => Math.min(i + 1, total - 1));
  }, [total]);

  const goPrev = useCallback(() => {
    setFlipped(false);
    setIndex((i) => Math.max(i - 1, 0));
  }, []);

  useEffect(() => {
    const handler = (e) => {
      // Ignore keys while the confirm dialog owns the screen, or the arrows
      // would shuffle cards behind it.
      if (regenModal.current?.open) return;
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === " ") {
        e.preventDefault();
        setFlipped((f) => !f);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goNext, goPrev]);

  const grade = (isKnown) => {
    recordReview(card.id, isKnown);
    setKnown((s) => {
      const n = new Set(s);
      if (isKnown) n.add(card.id);
      else n.delete(card.id);
      return n;
    });
    if (index < total - 1) {
      setFlipped(false);
      setIndex((i) => i + 1);
    }
  };

  const handleRegen = async () => {
    regenModal.current?.close();
    setRegenLoading(true);
    try {
      const newCards = await regenerateFlashcards(docId);
      setCards(newCards);
      setIndex(0);
      setFlipped(false);
      setKnown(new Set());
      if (onReloadCards) onReloadCards(newCards);
      toast("Flashcards regenerated", "success");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setRegenLoading(false);
    }
  };

  const pct = total > 0 ? ((index + 1) / total) * 100 : 0;

  if (total === 0) {
    return (
      <div className="animate-fade-up py-16 text-center">
        <p className="text-3xl" aria-hidden="true">🗂</p>
        <h2 className="mt-3 text-xl">No cards yet</h2>
        <p className="mt-2 text-sm text-base-content/60">
          Add some under Edit cards, or regenerate them with AI.
        </p>
      </div>
    );
  }

  if (allKnown) {
    return (
      <div className="animate-fade-up py-16 text-center">
        <p className="text-4xl" aria-hidden="true">🎉</p>
        <h2 className="mt-3 text-2xl">Deck complete</h2>
        <p className="mt-2 text-sm text-base-content/60">
          You reviewed all {total} cards.
        </p>
        <div className="mt-7 flex justify-center gap-3">
          <button
            onClick={() => {
              setKnown(new Set());
              setIndex(0);
              setFlipped(false);
            }}
            className="btn btn-outline btn-sm"
          >
            Review again
          </button>
          <button onClick={onStartQuiz} className="btn btn-primary btn-sm">
            Take a quiz
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-base-content/60">
          Known <span className="font-medium text-base-content">{knownCount}</span> / {total}
        </span>

        <div className="flex items-center gap-2">
          <button
            onClick={() => regenModal.current?.showModal()}
            disabled={regenLoading}
            className="btn btn-ghost btn-xs"
          >
            {regenLoading && <span className="loading loading-spinner loading-xs" />}
            {regenLoading ? "Regenerating…" : "Regenerate ↻"}
          </button>
          <button onClick={onStartQuiz} className="btn btn-primary btn-xs">
            Quiz →
          </button>
        </div>
      </div>

      <progress className="progress progress-primary mb-6 h-1 w-full" value={pct} max="100" />

      <div className="mb-6 flex justify-center">
        <div
          className="card-scene h-72 w-full max-w-lg cursor-pointer"
          onClick={() => setFlipped((f) => !f)}
          role="button"
          tabIndex={0}
          aria-label={flipped ? "Show question" : "Show answer"}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              setFlipped((f) => !f);
            }
          }}
        >
          <div className={`card-3d ${flipped ? "flipped" : ""}`}>
            <div className="card-face surface flex flex-col p-8 shadow-subtle">
              <div className="mb-4 flex items-start justify-between gap-3">
                <p className="text-xs font-medium uppercase tracking-wider text-base-content/40">
                  Question
                </p>
                {card.topic && (
                  <span className="badge badge-ghost badge-sm font-medium">{card.topic}</span>
                )}
              </div>
              <h3 className="flex-1 text-xl leading-snug">{card.question}</h3>
              <p className="mt-4 text-xs text-base-content/40">Space or tap to flip</p>
            </div>

            <div className="card-face card-face-back flex flex-col rounded-xl bg-primary p-8 text-primary-content shadow-subtle">
              <p className="mb-4 text-xs font-medium uppercase tracking-wider text-primary-content/60">
                Answer
              </p>
              <p className="flex-1 leading-relaxed">{card.answer}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="mb-6 flex items-center justify-center gap-4">
        <button
          onClick={goPrev}
          disabled={index === 0}
          className="btn btn-circle btn-outline btn-sm"
          aria-label="Previous card"
        >
          ←
        </button>
        <span className="text-sm tabular-nums text-base-content/60">
          {index + 1} / {total}
        </span>
        <button
          onClick={goNext}
          disabled={index === total - 1}
          className="btn btn-circle btn-outline btn-sm"
          aria-label="Next card"
        >
          →
        </button>
      </div>

      <div className="flex justify-center gap-3">
        <button onClick={() => grade(false)} className="btn btn-outline">
          Still learning
        </button>
        <button
          onClick={() => grade(true)}
          className={`btn ${known.has(card?.id) ? "btn-success" : "btn-primary"}`}
        >
          Got it ✓
        </button>
      </div>

      {/* Native <dialog>: it traps focus, closes on Escape and renders in the
          top layer, none of which the hand-rolled overlay did. */}
      <dialog ref={regenModal} className="modal">
        <div className="modal-box">
          <h3 className="text-lg">Regenerate flashcards?</h3>
          <p className="py-4 text-sm text-base-content/70">
            This replaces all {total} cards with newly generated ones. Your study
            history is kept.
          </p>
          <div className="modal-action">
            <form method="dialog">
              <button className="btn btn-ghost btn-sm">Cancel</button>
            </form>
            <button onClick={handleRegen} className="btn btn-primary btn-sm">
              Regenerate
            </button>
          </div>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </div>
  );
}
