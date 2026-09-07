import { useEffect, useState } from "react";
import { skipQuestion, startQuiz, submitAnswer } from "../api.js";

const SECONDS_PER_QUESTION = 30;
const LENGTHS = [5, 10, 15];

export default function QuizMode({ docId, onExit, onComplete }) {
  const [quizId, setQuizId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [selected, setSelected] = useState("");
  const [timer, setTimer] = useState(SECONDS_PER_QUESTION);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [numQuestions, setNumQuestions] = useState(10);

  // Restart the countdown whenever a new question arrives. Keyed on the
  // question id, not the object, so a re-render does not reset the clock.
  useEffect(() => {
    if (!quizId || !question) return;
    setTimer(SECONDS_PER_QUESTION);
    const id = setInterval(() => {
      setTimer((t) => {
        if (t <= 1) {
          clearInterval(id);
          return 0;
        }
        return t - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [quizId, question?.question_id]);

  const handleStart = async () => {
    setError("");
    setLoading(true);
    try {
      const data = await startQuiz(docId, numQuestions);
      setQuizId(data.quiz_id);
      setQuestion(data.question);
      setSelected("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const advance = (data) => {
    if (data.completed) {
      if (onComplete) onComplete(quizId);
    } else {
      setQuestion(data.question);
      setSelected("");
    }
  };

  const handleSubmit = async () => {
    if (!selected) return;
    setLoading(true);
    setError("");
    try {
      advance(await submitAnswer(quizId, selected, SECONDS_PER_QUESTION - timer));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    setLoading(true);
    setError("");
    try {
      advance(await skipQuestion(quizId, SECONDS_PER_QUESTION - timer));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const timerPct = (timer / SECONDS_PER_QUESTION) * 100;
  const urgent = timer <= 5;

  // --- Setup ---------------------------------------------------------------

  if (!question) {
    return (
      <div className="animate-fade-up">
        <button onClick={onExit} className="btn btn-ghost btn-xs -ml-2 mb-4 text-base-content/60">
          ← Back to deck
        </button>

        <div className="surface mx-auto max-w-md p-7 shadow-subtle">
          <h2 className="text-xl">Ready to test yourself?</h2>
          <p className="mt-1.5 text-sm text-base-content/60">
            {SECONDS_PER_QUESTION} seconds per question. Choose how many.
          </p>

          <div className="join mt-6 w-full">
            {LENGTHS.map((n) => (
              <button
                key={n}
                onClick={() => setNumQuestions(n)}
                className={`btn join-item flex-1 ${
                  numQuestions === n ? "btn-primary" : "btn-outline"
                }`}
              >
                {n}
              </button>
            ))}
          </div>

          {error && (
            <div role="alert" className="alert alert-error mt-5 py-2.5">
              <span className="text-sm">{error}</span>
            </div>
          )}

          <button
            onClick={handleStart}
            disabled={loading}
            className="btn btn-primary mt-6 w-full"
          >
            {loading && <span className="loading loading-spinner loading-sm" />}
            {loading ? "Starting…" : "Start quiz"}
          </button>
        </div>
      </div>
    );
  }

  // --- In progress ---------------------------------------------------------

  return (
    <div className="animate-fade-up mx-auto max-w-xl">
      <div className="mb-2 flex items-center justify-between text-xs font-medium">
        <span className="text-base-content/60">
          Question {question.question_number} of {question.total_questions}
        </span>
        <span className={urgent ? "text-error" : "text-base-content/60"}>{timer}s</span>
      </div>

      {/* A plain div rather than <progress>: the width transition is what makes
          the countdown read as continuous, and progress elements do not
          animate their value. */}
      <div className="mb-6 h-1 w-full overflow-hidden rounded-full bg-base-300">
        <div
          className={`timer-bar h-full rounded-full ${urgent ? "bg-error" : "bg-primary"}`}
          style={{ width: `${timerPct}%` }}
        />
      </div>

      <div className="surface mb-5 p-6 shadow-subtle">
        <p className="leading-relaxed">{question.text}</p>
      </div>

      <div className="mb-5 space-y-2">
        {question.options.map((opt) => {
          const active = selected === opt;
          return (
            <button
              key={opt}
              onClick={() => setSelected(opt)}
              aria-pressed={active}
              className={`w-full rounded-lg border px-4 py-3 text-left text-sm transition-colors ${
                active
                  ? "border-primary bg-primary text-primary-content font-medium"
                  : "border-base-300 bg-base-100 hover:border-primary/50 hover:bg-base-200/50"
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>

      {error && (
        <div role="alert" className="alert alert-error mb-4 py-2.5">
          <span className="text-sm">{error}</span>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={handleSubmit}
          disabled={loading || !selected}
          className="btn btn-primary flex-1"
        >
          {loading && <span className="loading loading-spinner loading-sm" />}
          Submit
        </button>
        <button onClick={handleSkip} disabled={loading} className="btn btn-ghost">
          Skip
        </button>
      </div>
    </div>
  );
}
