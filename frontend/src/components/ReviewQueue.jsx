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

  if (pCorrect == null) return { label: "Unranked", tone: "muted" };

  // Never practised is a different state, not a weak score. It lands near the
  // population prior — mid-range — and calling that "getting shaky" describes
  // forgetting that cannot have happened. The distinction also matters because
  // a long-forgotten concept scores *below* a new one, so without this the two
  // would be presented as the same kind of thing.
  if (days == null) return { label: "Not started", tone: "muted" };

  if (pCorrect < 0.35) return { label: "Review now", tone: "red" };
  if (pCorrect < 0.55) return { label: "Getting shaky", tone: "amber" };
  return { label: "Holding up", tone: "green" };
}

const TONE = {
  red: { text: "text-fl-red", bar: "bg-fl-red", chip: "bg-fl-red/10 text-fl-red" },
  amber: { text: "text-[#c98a2e]", bar: "bg-[#e0a640]", chip: "bg-[#e0a640]/12 text-[#c98a2e]" },
  green: { text: "text-fl-green", bar: "bg-fl-green", chip: "bg-fl-green/10 text-fl-green" },
  muted: { text: "text-fl-muted", bar: "bg-fl-muted", chip: "bg-fl-muted/10 text-fl-muted" },
};

/** How long ago, in words. `null` means never practised. */
function lastSeen(days) {
  if (days == null) return "Never studied";
  if (days < 1) return "Studied today";
  if (days < 2) return "Studied yesterday";
  if (days < 30) return `Studied ${Math.round(days)} days ago`;
  // floor, not round: at 45 days "2 months ago" overstates it, and overstating
  // how long ago something was studied makes the queue look more alarming than
  // the data supports.
  const months = Math.max(1, Math.floor(days / 30));
  return `Studied ${months} month${months === 1 ? "" : "s"} ago`;
}

/**
 * What the estimate is based on, in the user's terms rather than the model's.
 *
 * `source` comes straight from the ranker: "prior" means there was too little
 * history for the sequence model and a population average was used, "sakt" and
 * "blend" mean the trained model contributed, and "unavailable" means the model
 * could not be loaded and the order is a least-practised fallback rather than a
 * forgetting estimate. Saying so matters — a confident-looking list that is
 * secretly just "least practised" would be misleading.
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
      <h2 className="text-2xl font-serif text-fl-black mb-1">What to review.</h2>
      <p className="text-sm text-fl-muted font-sans mb-6">
        Your concepts, ranked by how likely you are to have forgotten them.
      </p>

      {/* Projection. The forgetting curve is time-based, so "what will I have
          lost by my exam" is a real query the backend already answers. */}
      <div className="flex items-center gap-2 mb-6">
        {HORIZONS.map((h) => (
          <button
            key={h.id}
            onClick={() => setHorizon(h.id)}
            className={`btn-press px-3 py-1.5 rounded-lg text-xs font-sans font-semibold transition-colors ${
              horizon === h.id
                ? "bg-fl-yellow text-fl-black"
                : "bg-fl-card border border-fl-border text-fl-muted hover:text-fl-black hover:border-fl-black"
            }`}
          >
            {h.label}
          </button>
        ))}
        {horizon !== "now" && (
          <span className="text-xs font-sans text-fl-muted ml-1">
            projected — assumes you don't study in between
          </span>
        )}
      </div>

      {loading && (
        <div className="flex items-center gap-3 text-sm text-fl-muted font-sans">
          <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
          Working out what you're forgetting…
        </div>
      )}

      {!loading && error && (
        <p className="text-sm font-sans text-fl-red">{error}</p>
      )}

      {!loading && !error && concepts.length === 0 && (
        <div className="text-center py-12 border border-dashed border-fl-border rounded-xl">
          <p className="text-2xl font-serif text-fl-black mb-2">Nothing to review yet.</p>
          <p className="text-sm text-fl-muted font-sans">
            Upload a PDF and study a few cards. Concepts show up here<br />
            as soon as there's something to track.
          </p>
        </div>
      )}

      {!loading && !error && degraded && (
        // The backend degrades rather than failing when the model is
        // unavailable. Saying so is the honest thing: the order is still
        // useful, it is just not a forgetting estimate.
        <p className="mb-4 text-xs font-sans text-fl-muted border-l-4 border-fl-border bg-fl-card rounded-r-lg px-4 py-3">
          Scoring is unavailable right now, so these are ordered by how little
          you've practised them.
        </p>
      )}

      <div className="space-y-2">
        {concepts.map((c) => {
          const { label: bandLabel, tone: toneName } = band(c);
          const tone = TONE[toneName];
          const deck = c.documents?.[0];
          return (
            <div
              key={c.concept_id}
              className="bg-fl-card border border-fl-border rounded-xl px-5 py-4 card-hover"
              style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-sans font-medium text-fl-black truncate">
                      {c.label}
                    </p>
                    <span
                      className={`px-2 py-0.5 rounded-md text-[10px] font-sans font-semibold uppercase tracking-wide ${tone.chip}`}
                    >
                      {bandLabel}
                    </span>
                  </div>

                  <p className="text-xs font-sans text-fl-muted mt-1">
                    {lastSeen(c.days_since_last_review)}
                    {" · "}
                    {c.card_count} card{c.card_count === 1 ? "" : "s"}
                    {c.interaction_count > 0 && ` · ${c.interaction_count} attempts`}
                  </p>

                  {c.p_correct != null && (
                    <div className="mt-2.5 flex items-center gap-2">
                      {/* Recall, not risk: a longer bar reads as "you still
                          have this", which is the direction people expect. */}
                      <div className="h-1.5 flex-1 max-w-[180px] bg-fl-border rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${tone.bar}`}
                          style={{ width: `${Math.round(c.p_correct * 100)}%` }}
                        />
                      </div>
                      <span className={`text-[11px] font-sans font-medium ${tone.text}`}>
                        {Math.round(c.p_correct * 100)}%
                        {c.days_since_last_review == null ? " expected" : " recall"}
                      </span>
                    </div>
                  )}

                  <p className="text-[11px] font-sans text-fl-muted mt-1.5">
                    {basis(c.source)}
                  </p>
                </div>

                {deck && (
                  <button
                    onClick={() => navigate(`/deck/${deck.id}`)}
                    title={
                      c.documents.length > 1
                        ? `In ${c.documents.length} decks — opening ${deck.filename}`
                        : deck.filename
                    }
                    className="btn-press shrink-0 px-3 py-1.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-xs font-sans font-semibold transition-colors"
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
        // Deliberately understated. The prior path is the correct behaviour
        // until a model is trained on real data, not a broken state — but a
        // user comparing this to "personalised" claims deserves the truth.
        <p className="mt-6 text-[11px] font-sans text-fl-muted">
          Rankings currently use typical concept difficulty and how long it's
          been since you studied. They'll get more personal as you build up
          answer history.
        </p>
      )}
    </div>
  );
}
