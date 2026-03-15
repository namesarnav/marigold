import { useState, useEffect } from "react";
import { getQuizResults } from "../api.js";

export default function Results({ quizId, onRetry, onExit, onReview }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuizResults(quizId)
      .then(setResults)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [quizId]);

  if (loading) {
    return (
      <div className="flex items-center gap-3 text-sm text-fl-muted font-sans p-8">
        <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
        Loading results…
      </div>
    );
  }

  if (error) return <p className="text-sm text-fl-red font-sans p-4">{error}</p>;
  if (!results) return null;

  const pct = results.percentage;
  const grade = pct >= 80 ? "Great work!" : pct >= 60 ? "Good effort." : "Keep practicing.";

  return (
    <div className="animate-fade-up max-w-lg">
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-2xl font-serif text-fl-black">Results</h2>
        <button onClick={onExit} className="text-sm font-sans text-fl-muted hover:text-fl-black transition-colors border border-fl-border rounded-lg px-3 py-1.5">
          ← Back
        </button>
      </div>

      {/* Score card */}
      <div
        className="bg-fl-card border border-fl-border rounded-xl p-8 mb-5"
        style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
      >
        <p className="text-sm font-sans text-fl-muted mb-1">{grade}</p>
        <p className="text-5xl font-serif text-fl-black mb-1">
          {results.score}<span className="text-fl-muted">/{results.total}</span>
        </p>
        <p className="text-2xl font-serif text-fl-muted">{pct.toFixed(0)}%</p>
        <div className="mt-4 h-2 w-full bg-fl-border rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-fl-green transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-3 text-xs font-sans text-fl-muted">
          Time taken: {Math.round(results.time_taken_seconds)}s
        </p>
      </div>

      {/* Wrong answers */}
      {results.wrong_answers?.length > 0 && (
        <div className="mb-6">
          <p className="text-sm font-sans font-semibold text-fl-black mb-3">Review wrong answers</p>
          <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
            {results.wrong_answers.map((wa, i) => (
              <div
                key={i}
                className="bg-fl-card border border-fl-border rounded-xl p-4"
                style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
              >
                <p className="text-xs font-sans text-fl-muted mb-2">{wa.question}</p>
                <p className="text-xs font-sans text-fl-red">
                  Your answer: <span className="font-medium">{wa.your_answer || "Skipped"}</span>
                </p>
                <p className="text-xs font-sans text-fl-green mt-0.5">
                  Correct: <span className="font-medium">{wa.correct_answer}</span>
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-3 flex-wrap">
        <button
          onClick={onRetry}
          className="btn-press flex-1 py-2.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-sm font-sans font-semibold transition-colors"
        >
          Retry quiz
        </button>
        {onReview && (
          <button
            onClick={() => onReview()}
            className="btn-press flex-1 py-2.5 rounded-lg border border-fl-black text-fl-black text-sm font-sans font-semibold hover:bg-fl-black hover:text-cream transition-colors"
          >
            Review answers
          </button>
        )}
        <button
          onClick={onExit}
          className="flex-1 py-2.5 rounded-lg border border-fl-border text-fl-black text-sm font-sans font-semibold hover:border-fl-black transition-colors"
        >
          Back to flashcards
        </button>
      </div>
    </div>
  );
}
