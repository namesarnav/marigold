import { useEffect, useState } from "react";
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
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className="alert alert-error">
        <span className="text-sm">{error}</span>
      </div>
    );
  }

  if (!results) return null;

  const pct = results.percentage;
  const grade = pct >= 80 ? "Great work" : pct >= 60 ? "Good effort" : "Keep practising";
  const tone = pct >= 80 ? "text-success" : pct >= 60 ? "text-warning" : "text-error";

  return (
    <div className="animate-fade-up mx-auto max-w-xl">
      <h2 className="mb-6 text-2xl">Results</h2>

      <div className="surface mb-5 p-8 text-center shadow-subtle">
        <p className={`text-sm font-medium ${tone}`}>{grade}</p>

        <p className="mt-2 text-5xl font-semibold tracking-tight">
          {results.score}
          <span className="text-base-content/30">/{results.total}</span>
        </p>
        <p className="mt-1 text-lg text-base-content/50">{pct.toFixed(0)}%</p>

        <progress
          className={`progress mt-5 w-full ${
            pct >= 80 ? "progress-success" : pct >= 60 ? "progress-warning" : "progress-error"
          }`}
          value={pct}
          max="100"
        />

        <p className="mt-3 text-xs text-base-content/50">
          Time taken: {Math.round(results.time_taken_seconds)}s
        </p>
      </div>

      {results.wrong_answers?.length > 0 && (
        <div className="mb-6">
          <p className="mb-3 text-sm font-medium">Where you slipped</p>
          <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
            {results.wrong_answers.map((wa, i) => (
              <div key={i} className="surface p-4">
                <p className="text-sm">{wa.question}</p>
                <p className="mt-2 text-xs text-error">
                  Your answer:{" "}
                  <span className="font-medium">{wa.your_answer || "Skipped"}</span>
                </p>
                <p className="mt-0.5 text-xs text-success">
                  Correct: <span className="font-medium">{wa.correct_answer}</span>
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button onClick={onRetry} className="btn btn-primary flex-1">
          Retry quiz
        </button>
        {onReview && (
          <button onClick={() => onReview()} className="btn btn-outline flex-1">
            Review answers
          </button>
        )}
        <button onClick={onExit} className="btn btn-ghost flex-1">
          Back to deck
        </button>
      </div>
    </div>
  );
}
