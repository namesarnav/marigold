import { useEffect, useState } from "react";
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

  if (!review) return null;

  const correct = review.questions.filter((q) => q.is_correct).length;
  const total = review.questions.length;
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;

  return (
    <div className="animate-fade-up mx-auto max-w-2xl">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <button onClick={onBack} className="btn btn-ghost btn-xs -ml-2 text-base-content/60">
            ← Back
          </button>
          <h2 className="mt-1 text-2xl">Quiz review</h2>
        </div>
        <button onClick={onRetake} className="btn btn-primary btn-sm">
          Retake quiz
        </button>
      </div>

      <div className="surface mb-6 flex items-center gap-5 px-6 py-4 shadow-subtle">
        <div>
          <p className="text-2xl font-semibold tracking-tight">
            {correct}
            <span className="text-base-content/30"> / {total}</span>
          </p>
          <p className="text-xs text-base-content/50">correct</p>
        </div>
        <progress className="progress progress-primary flex-1" value={pct} max="100" />
        <p className="text-xl font-semibold tabular-nums">{pct}%</p>
      </div>

      <div className="space-y-3">
        {review.questions.map((q, i) => (
          <div key={i} className="surface p-5">
            <div className="mb-4 flex items-start justify-between gap-4">
              <p className="flex-1 leading-snug">{q.question}</p>

              <div className="flex shrink-0 items-center gap-2">
                {q.user_answer === null ? (
                  <span className="badge badge-ghost badge-sm">Skipped</span>
                ) : q.is_correct ? (
                  <span className="badge badge-success badge-sm gap-1">✓</span>
                ) : (
                  <span className="badge badge-error badge-sm gap-1">✗</span>
                )}
                {q.time_taken_seconds != null && (
                  <span className="text-xs text-base-content/40">
                    {q.time_taken_seconds}s
                  </span>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              {q.options.map((opt) => {
                const isCorrect = opt === q.correct_answer;
                const isUserWrong = opt === q.user_answer && !q.is_correct;

                let cls = "flex items-center justify-between rounded-lg border px-3 py-2 text-sm ";
                if (isCorrect) cls += "border-success bg-success/10";
                else if (isUserWrong) cls += "border-error bg-error/10";
                else cls += "border-base-300 bg-base-200/40 text-base-content/50";

                return (
                  <div key={opt} className={cls}>
                    <span>{opt}</span>
                    {isCorrect && <span className="text-xs text-success">✓ correct</span>}
                    {isUserWrong && <span className="text-xs text-error">your answer</span>}
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
