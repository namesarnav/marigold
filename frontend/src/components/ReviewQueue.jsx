import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getReviewQueue } from "../api.js";

/**
 * Turns a probability of recall into something a person can read.
 *
 * The raw number is meaningless to a user — 0.26 is not "26% likely to be
 * remembered" in any calibrated sense, it is a model output on an uncalibrated
 * scale. Bands say what the ranking is actually claiming: relative urgency.
 */
function band(concept) {
  const { p_correct: pCorrect, days_since_last_review: days } = concept;

  if (pCorrect == null) return { label: "Unranked", tone: "neutral" };

  // Never practised is a different state, not a weak score. It lands near the
  // population prior — mid-range — and calling that "getting shaky" describes
  // forgetting that cannot have happened. The distinction also matters because
  // a long-forgotten concept scores *below* a new one.
  if (days == null) return { label: "Not started", tone: "neutral" };

  if (pCorrect < 0.35) return { label: "Review now", tone: "error" };
  if (pCorrect < 0.55) return { label: "Getting shaky", tone: "warning" };
  return { label: "Holding up", tone: "success" };
}

const TONE = {
  error: { badge: "badge-error", progress: "progress-error", text: "text-error" },
  warning: { badge: "badge-warning", progress: "progress-warning", text: "text-warning" },
  success: { badge: "badge-success", progress: "progress-success", text: "text-success" },
  neutral: { badge: "badge-ghost", progress: "", text: "text-base-content/50" },
};

/** How long ago, in words. `null` means never practised. */
function lastSeen(days) {
  if (days == null) return "Never studied";
  if (days < 1) return "Studied today";
  if (days < 2) return "Studied yesterday";
  if (days < 30) return `Studied ${Math.round(days)} days ago`;
  // floor, not round: at 45 days "2 months ago" overstates it, and overstating
  // staleness makes the queue look more alarming than the data supports.
  const months = Math.max(1, Math.floor(days / 30));
  return `Studied ${months} month${months === 1 ? "" : "s"} ago`;
}

/**
 * What the estimate is based on, in the user's terms rather than the model's.
 *
 * `source` comes straight from the ranker. Saying so matters — a
 * confident-looking list that is secretly just "least practised" would mislead.
 */
function basis(source) {
  switch (source) {
    case "sakt":
      return "Based on your answer history";
    case "blend":
      return "Based on your history and typical difficulty";
    case "prior":
      return "Based on typical difficulty";
    default:
      return "Ranked by how little you've practised it";
  }
}

const HORIZONS = [
  { id: "now", label: "Today", days: 0 },
  { id: "1w", label: "In a week", days: 7 },
  { id: "1m", label: "In a month", days: 30 },
];

export default function ReviewQueue() {
  const navigate = useNavigate();
  const [horizon, setHorizon] = useState("now");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (horizonId) => {
    setLoading(true);
    setError("");
    try {
      const { days } = HORIZONS.find((h) => h.id === horizonId) ?? HORIZONS[0];
      const asOf = days ? new Date(Date.now() + days * 86400000) : null;
      setData(await getReviewQueue({ limit: 20, asOf }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(horizon);
  }, [horizon, load]);

  const concepts = data?.concepts ?? [];
  const degraded = concepts.length > 0 && concepts.every((c) => c.source === "unavailable");

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-2xl">What to review</h1>
        <p className="mt-1 text-sm text-base-content/60">
          Your concepts, ranked by how likely you are to have forgotten them.
        </p>
      </div>

      {/* Projection. The forgetting curve is time-based, so "what will I have
          lost by my exam" is a real query the backend already answers. */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div role="tablist" className="join">
          {HORIZONS.map((h) => (
            <button
              key={h.id}
              role="tab"
              onClick={() => setHorizon(h.id)}
              className={`btn join-item btn-sm ${
                horizon === h.id ? "btn-primary" : "btn-outline"
              }`}
            >
              {h.label}
            </button>
          ))}
        </div>
        {horizon !== "now" && (
          <span className="text-xs text-base-content/50">
            projected — assumes you don't study in between
          </span>
        )}
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner loading-md text-primary" />
        </div>
      )}

      {!loading && error && (
        <div role="alert" className="alert alert-error">
          <span className="text-sm">{error}</span>
        </div>
      )}

      {!loading && !error && concepts.length === 0 && (
        <div className="rounded-xl border border-dashed border-base-300 py-12 text-center">
          <p className="text-3xl" aria-hidden="true">🎯</p>
          <h2 className="mt-3 text-lg">Nothing to review yet</h2>
          <p className="mt-1 text-sm text-base-content/60">
            Upload a PDF and study a few cards. Concepts show up here as soon as
            there's something to track.
          </p>
        </div>
      )}

      {!loading && !error && degraded && (
        // The backend degrades rather than failing when the model is
        // unavailable. Saying so is the honest thing.
        <div role="status" className="alert mb-4 py-2.5">
          <span className="text-sm">
            Scoring is unavailable right now, so these are ordered by how little
            you've practised them.
          </span>
        </div>
      )}

      <div className="space-y-2">
        {concepts.map((c) => {
          const { label: bandLabel, tone: toneName } = band(c);
          const tone = TONE[toneName];
          const deck = c.documents?.[0];

          return (
            <div key={c.concept_id} className="surface p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium">{c.label}</p>
                    <span className={`badge badge-sm ${tone.badge} font-medium`}>
                      {bandLabel}
                    </span>
                  </div>

                  <p className="mt-1 text-xs text-base-content/50">
                    {lastSeen(c.days_since_last_review)} · {c.card_count} card
                    {c.card_count === 1 ? "" : "s"}
                    {c.interaction_count > 0 && ` · ${c.interaction_count} attempts`}
                  </p>

                  {c.p_correct != null && (
                    <div className="mt-2.5 flex items-center gap-2">
                      {/* Recall, not risk: a longer bar reads as "you still
                          have this", which is the direction people expect. */}
                      <progress
                        className={`progress w-40 ${tone.progress}`}
                        value={Math.round(c.p_correct * 100)}
                        max="100"
                      />
                      <span className={`text-xs font-medium tabular-nums ${tone.text}`}>
                        {Math.round(c.p_correct * 100)}%
                        {c.days_since_last_review == null ? " expected" : " recall"}
                      </span>
                    </div>
                  )}

                  <p className="mt-1.5 text-xs text-base-content/40">{basis(c.source)}</p>
                </div>

                {deck && (
                  <button
                    onClick={() => navigate(`/deck/${deck.id}`)}
                    title={
                      c.documents.length > 1
                        ? `In ${c.documents.length} decks — opening ${deck.filename}`
                        : deck.filename
                    }
                    className="btn btn-primary btn-sm shrink-0"
                  >
                    Study
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {!loading && concepts.length > 0 && !data?.model_available && (
        // Deliberately understated. The prior path is correct behaviour until a
        // model is trained on real data, not a broken state.
        <p className="mt-6 text-xs text-base-content/40">
          Rankings currently use typical concept difficulty and how long it's
          been since you studied. They'll get more personal as you build up
          answer history.
        </p>
      )}
    </div>
  );
}
