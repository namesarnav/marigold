import { useState, useEffect } from "react";
import { getQuizReview } from "../api.js";

export default function QuizReview({ quizId, onRetake, onBack }) {
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuizReview(quizId)
      .then(setReview)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [quizId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-fl-muted font-sans p-8">
        <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
        Loading review…
      </div>
    );
  }

  if (error) return <p className="text-sm text-fl-red font-sans p-4">{error}</p>;
  if (!review) return null;

  const correct = review.questions.filter((q) => q.is_correct).length;
  const total = review.questions.length;
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;

  return (
    <div className="animate-fade-up max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <button onClick={onBack} className="text-xs font-sans text-fl-muted hover:text-fl-black transition-colors mb-1 flex items-center gap-1">
            ← Back
          </button>
          <h2 className="text-2xl font-serif text-fl-black">Quiz Review</h2>
        </div>
        <button
          onClick={onRetake}
          className="btn-press px-4 py-2 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-sm font-sans font-semibold transition-colors"
        >
          Retake quiz
        </button>
      </div>

      {/* Score summary */}
      <div
        className="bg-fl-card border border-fl-border rounded-xl px-6 py-4 mb-6 flex items-center gap-6"
        style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
      >
        <div>
          <p className="text-3xl font-serif text-fl-black">
            {correct}<span className="text-fl-muted text-xl"> / {total}</span>
          </p>
          <p className="text-xs font-sans text-fl-muted mt-0.5">correct</p>
        </div>
        <div className="flex-1">
          <div className="h-2 w-full bg-fl-border rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-fl-green transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        <p className="text-2xl font-serif text-fl-black">{pct}%</p>
      </div>

      {/* Question list */}
      <div className="space-y-3">
        {review.questions.map((q, i) => (
          <div
            key={i}
            className="bg-fl-card border border-fl-border rounded-xl p-5"
            style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
          >
            {/* Question text */}
            <div className="flex items-start justify-between gap-4 mb-4">
              <p className="text-base font-serif text-fl-black leading-snug flex-1">{q.question}</p>
              <div className="flex items-center gap-2 shrink-0">
                {q.user_answer === null ? (
                  <span className="px-2 py-0.5 rounded-full bg-fl-border text-fl-muted text-[10px] font-sans font-semibold uppercase tracking-wider">
                    Skipped
                  </span>
                ) : q.is_correct ? (
                  <span className="text-fl-green text-sm font-sans font-semibold">✓</span>
                ) : (
                  <span className="text-fl-red text-sm font-sans font-semibold">✗</span>
                )}
                {q.time_taken_seconds != null && (
                  <span className="text-[11px] font-sans text-fl-muted">{q.time_taken_seconds}s</span>
                )}
              </div>
            </div>

            {/* Options */}
            <div className="space-y-1.5">
              {q.options.map((opt) => {
                const isCorrect = opt === q.correct_answer;
                const isUserWrong = opt === q.user_answer && !q.is_correct;
                let cls = "px-3 py-2 rounded-lg text-sm font-sans border transition-none ";
                if (isCorrect) {
                  cls += "bg-fl-green/15 border-fl-green text-fl-black font-medium";
                } else if (isUserWrong) {
                  cls += "bg-fl-red/15 border-fl-red text-fl-black";
                } else {
                  cls += "bg-cream border-fl-border text-fl-muted";
                }
                return (
                  <div key={opt} className={cls}>
                    <span className="flex items-center justify-between">
                      <span>{opt}</span>
                      {isCorrect && <span className="text-fl-green text-xs">✓ correct</span>}
                      {isUserWrong && <span className="text-fl-red text-xs">your answer</span>}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
