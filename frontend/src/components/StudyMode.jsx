import { useState, useEffect, useCallback } from "react";
import { regenerateFlashcards } from "../api.js";
import { useToast } from "../toast.jsx";

export default function StudyMode({ cards: initialCards, docId, onStartQuiz, onBack, onReloadCards }) {
  const [cards, setCards] = useState(initialCards);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [known, setKnown] = useState(new Set());
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [regenLoading, setRegenLoading] = useState(false);
  const toast = useToast();

  // Sync if parent reloads cards
  useEffect(() => { setCards(initialCards); setIndex(0); setFlipped(false); setKnown(new Set()); }, [initialCards]);

  const total = cards.length;
  const card = cards[index];
  const knownCount = known.size;
  const allKnown = knownCount === total && total > 0;

  const goNext = useCallback(() => { setFlipped(false); setIndex((i) => Math.min(i + 1, total - 1)); }, [total]);
  const goPrev = useCallback(() => { setFlipped(false); setIndex((i) => Math.max(i - 1, 0)); }, []);

  useEffect(() => {
    const handler = (e) => {
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === " ") { e.preventDefault(); setFlipped((f) => !f); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goNext, goPrev]);

  const handleGotIt = () => {
    setKnown((s) => new Set([...s, card.id]));
    if (index < total - 1) { setFlipped(false); setIndex((i) => i + 1); }
  };

  const handleStillLearning = () => {
    setKnown((s) => { const n = new Set(s); n.delete(card.id); return n; });
    if (index < total - 1) { setFlipped(false); setIndex((i) => i + 1); }
  };

  const handleRegen = async () => {
    setShowRegenModal(false);
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
      <div className="animate-fade-up flex flex-col items-center justify-center py-16 text-center">
        <p className="text-2xl font-serif text-fl-black mb-2">No cards yet.</p>
        <p className="text-sm text-fl-muted font-sans">Add cards via Edit Cards or regenerate with AI.</p>
      </div>
    );
  }

  // Completion screen
  if (allKnown) {
    return (
      <div className="animate-fade-up flex flex-col items-center justify-center py-16 text-center">
        <p className="text-4xl mb-2">🎉</p>
        <h2 className="text-3xl font-serif text-fl-black mb-2">Deck complete!</h2>
        <p className="text-sm text-fl-muted font-sans mb-8">You reviewed all {total} cards.</p>
        <div className="flex gap-3">
          <button
            onClick={() => { setKnown(new Set()); setIndex(0); setFlipped(false); }}
            className="px-5 py-2.5 rounded-lg border border-fl-border text-fl-black text-sm font-sans font-semibold hover:border-fl-black transition-colors"
          >
            Review again
          </button>
          <button
            onClick={onStartQuiz}
            className="btn-press px-5 py-2.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-sm font-sans font-semibold transition-colors"
          >
            Take a quiz →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <button onClick={onBack} className="text-sm font-sans text-fl-muted hover:text-fl-black transition-colors flex items-center gap-1">
          ← Back
        </button>
        <div className="flex items-center gap-3">
          <span className="text-xs font-sans text-fl-muted">Known: {knownCount} / {total}</span>
          <button
            onClick={() => setShowRegenModal(true)}
            disabled={regenLoading}
            className="text-xs font-sans text-fl-muted border border-fl-border rounded-lg px-3 py-1.5 hover:border-fl-black hover:text-fl-black transition-all disabled:opacity-50"
          >
            {regenLoading ? "Regenerating…" : "Regenerate with AI ↻"}
          </button>
          <button
            onClick={onStartQuiz}
            className="btn-press px-3 py-1.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-xs font-sans font-semibold transition-colors"
          >
            Quiz →
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 w-full bg-fl-border rounded-full mb-6 overflow-hidden">
        <div className="h-full rounded-full bg-fl-yellow transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>

      {/* Card */}
      <div className="flex justify-center mb-6">
        <div
          className="card-scene cursor-pointer w-full max-w-[480px]"
          style={{ height: "280px" }}
          onClick={() => setFlipped((f) => !f)}
        >
          <div className={`card-3d ${flipped ? "flipped" : ""}`}>
            {/* Front */}
            <div
              className="card-face bg-fl-card border border-fl-border rounded-2xl p-8 flex flex-col"
              style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.06)" }}
            >
              <div className="flex items-start justify-between mb-4">
                <p className="text-xs font-sans font-medium text-fl-muted uppercase tracking-wider">Question</p>
                {card.topic && (
                  <span className="inline-block px-2.5 py-0.5 rounded-full bg-fl-yellow text-fl-black text-[10px] font-sans font-semibold uppercase tracking-wider">
                    {card.topic}
                  </span>
                )}
              </div>
              <h3 className="font-serif text-xl text-fl-black leading-snug flex-1">{card.question}</h3>
              <p className="text-xs text-fl-muted font-sans mt-4">Space or tap to flip</p>
            </div>
            {/* Back */}
            <div
              className="card-face card-face-back bg-fl-yellow border border-fl-yellow rounded-2xl p-8 flex flex-col"
              style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.06)" }}
            >
              <p className="text-xs font-sans font-medium text-fl-black/60 uppercase tracking-wider mb-4">Answer</p>
              <p className="font-sans text-base text-fl-black leading-relaxed flex-1">{card.answer}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-center gap-5 mb-6">
        <button
          onClick={goPrev}
          disabled={index === 0}
          className="h-9 w-9 rounded-full border border-fl-border flex items-center justify-center text-fl-black hover:border-fl-black transition-colors disabled:opacity-30"
        >
          ←
        </button>
        <span className="text-sm font-sans font-medium text-fl-black tabular-nums">
          {index + 1} / {total}
        </span>
        <button
          onClick={goNext}
          disabled={index === total - 1}
          className="h-9 w-9 rounded-full border border-fl-border flex items-center justify-center text-fl-black hover:border-fl-black transition-colors disabled:opacity-30"
        >
          →
        </button>
      </div>

      {/* Known / Still learning */}
      <div className="flex justify-center gap-3">
        <button
          onClick={handleStillLearning}
          className="px-5 py-2.5 rounded-lg border border-fl-border text-fl-black text-sm font-sans font-semibold hover:border-fl-black transition-colors"
        >
          Still learning
        </button>
        <button
          onClick={handleGotIt}
          className={`btn-press px-5 py-2.5 rounded-lg text-sm font-sans font-semibold transition-colors ${
            known.has(card?.id)
              ? "bg-fl-green/20 border border-fl-green text-fl-green"
              : "bg-fl-yellow hover:bg-fl-yellow-h text-fl-black"
          }`}
        >
          Got it ✓
        </button>
      </div>

      {/* Regen modal */}
      {showRegenModal && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-fl-black/30 backdrop-blur-sm">
          <div
            className="bg-fl-card rounded-2xl p-8 max-w-sm w-full mx-4 animate-fade-up"
            style={{ boxShadow: "0 8px 32px rgba(40,40,40,0.12)" }}
          >
            <h3 className="text-xl font-serif text-fl-black mb-2">Regenerate flashcards?</h3>
            <p className="text-sm text-fl-muted font-sans mb-6">
              This will replace all {total} flashcards with newly generated ones. Continue?
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowRegenModal(false)}
                className="flex-1 py-2.5 rounded-lg border border-fl-border text-fl-black text-sm font-sans font-semibold hover:border-fl-black transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleRegen}
                className="btn-press flex-1 py-2.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-sm font-sans font-semibold transition-colors"
              >
                Regenerate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
