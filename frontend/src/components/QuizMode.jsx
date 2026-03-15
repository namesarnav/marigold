import { useState, useEffect } from "react";
import { startQuiz, submitAnswer, skipQuestion } from "../api.js";

export default function QuizMode({ docId, onExit, onComplete }) {
  const [quizId, setQuizId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [selected, setSelected] = useState("");
  const [timer, setTimer] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [numQuestions, setNumQuestions] = useState(10);

  useEffect(() => {
    if (!quizId || !question) return;
    setTimer(30);
    const id = setInterval(() => {
      setTimer((t) => {
        if (t <= 1) { clearInterval(id); return 0; }
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
      advance(await submitAnswer(quizId, selected, 30 - timer));
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
      advance(await skipQuestion(quizId, 30 - timer));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const timerPct = (timer / 30) * 100;
  const timerColor = timer <= 5 ? "#e05c5c" : "#ffe459";

  return (
    <div className="animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-2xl font-serif text-fl-black">Quiz Mode</h2>
        <button onClick={onExit} className="text-sm font-sans text-fl-muted hover:text-fl-black transition-colors border border-fl-border rounded-lg px-3 py-1.5">
          ← Back
        </button>
      </div>

      {!question && (
        <div
          className="bg-fl-card border border-fl-border rounded-xl p-8 max-w-md"
          style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
        >
          <h3 className="text-xl font-serif text-fl-black mb-1">Ready to test yourself?</h3>
          <p className="text-sm text-fl-muted font-sans mb-6">30 seconds per question. Choose how many you want.</p>
          <div className="flex items-center gap-4 mb-6">
            {[5, 10, 15].map((n) => (
              <button
                key={n}
                onClick={() => setNumQuestions(n)}
                className={`btn-press flex-1 py-2 rounded-lg text-sm font-sans font-semibold border transition-all ${
                  numQuestions === n
                    ? "bg-fl-yellow border-fl-yellow text-fl-black"
                    : "bg-fl-card border-fl-border text-fl-black hover:border-fl-black"
                }`}
              >
                {n} Q
              </button>
            ))}
          </div>
          {error && <p className="text-sm text-fl-red font-sans mb-4">{error}</p>}
          <button
            onClick={handleStart}
            disabled={loading}
            className="btn-press w-full py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold disabled:opacity-60 transition-colors"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
                Starting…
              </span>
            ) : "Start quiz →"}
          </button>
        </div>
      )}

      {question && (
        <div className="max-w-lg animate-fade-in">
          {/* Progress */}
          <div className="flex items-center justify-between text-xs font-sans font-medium text-fl-muted mb-2">
            <span>Question {question.question_number} of {question.total_questions}</span>
            <span className={timer <= 5 ? "text-fl-red font-semibold" : ""}>{timer}s</span>
          </div>

          {/* Timer bar */}
          <div className="h-1 w-full bg-fl-border rounded-full mb-6 overflow-hidden">
            <div
              className="h-full rounded-full timer-bar"
              style={{ width: `${timerPct}%`, backgroundColor: timerColor }}
            />
          </div>

          {/* Question */}
          <div
            className="bg-fl-card border border-fl-border rounded-xl p-6 mb-5"
            style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
          >
            <p className="text-base font-sans text-fl-black leading-relaxed">{question.text}</p>
          </div>

          {/* Options */}
          <div className="space-y-2 mb-5">
            {question.options.map((opt) => (
              <button
                key={opt}
                onClick={() => setSelected(opt)}
                className={`btn-press w-full text-left px-4 py-3 rounded-lg border text-sm font-sans transition-all ${
                  selected === opt
                    ? "bg-fl-yellow border-fl-yellow text-fl-black font-medium"
                    : "bg-fl-card border-fl-border text-fl-black hover:border-fl-black"
                }`}
              >
                {opt}
              </button>
            ))}
          </div>

          {error && <p className="text-sm text-fl-red font-sans mb-3">{error}</p>}

          <div className="flex items-center gap-3">
            <button
              onClick={handleSubmit}
              disabled={loading || !selected}
              className="btn-press flex-1 py-2.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-sm font-sans font-semibold disabled:opacity-50 transition-colors"
            >
              Submit
            </button>
            <button
              onClick={handleSkip}
              disabled={loading}
              className="px-4 py-2.5 rounded-lg border border-fl-border text-sm font-sans text-fl-muted hover:border-fl-black hover:text-fl-black transition-all disabled:opacity-50"
            >
              Skip
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
