import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  deleteDocument,
  getQuizHistory,
  getStats,
  listDocuments,
  logout,
  renameDocument,
} from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "../toast.jsx";
import Logo from "../components/Logo.jsx";
import ReviewQueue from "../components/ReviewQueue.jsx";
import UploadZone from "../components/UploadZone.jsx";

// The tabs, and the only values `?view=` accepts — anything else falls back to
// Documents rather than rendering a blank pane.
const VIEWS = ["documents", "review", "history"];

const NAV = [
  { id: "documents", label: "Documents", icon: "📄" },
  { id: "review", label: "What to review", icon: "🎯" },
  { id: "history", label: "Quiz history", icon: "📊" },
];

function greeting(name) {
  const h = new Date().getHours();
  const part = h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
  return `Good ${part}, ${name?.split(" ")[0] ?? "there"}`;
}

function StatCard({ label, value, sub }) {
  return (
    <div className="surface px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wider text-base-content/40">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      {sub && <p className="text-xs text-base-content/50">{sub}</p>}
    </div>
  );
}

function RenameInput({ value, onSave, onCancel }) {
  const [val, setVal] = useState(value);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const submit = () => {
    if (val.trim()) onSave(val.trim());
  };

  return (
    <div className="flex flex-1 items-center gap-2">
      <input
        ref={inputRef}
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") onCancel();
        }}
        className="input input-bordered input-sm flex-1"
      />
      <button onClick={submit} className="btn btn-primary btn-sm">Save</button>
      <button onClick={onCancel} className="btn btn-ghost btn-sm">Cancel</button>
    </div>
  );
}

export default function Dashboard() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  // The open tab lives in the URL, so a refresh keeps you where you were and a
  // view can be linked to directly.
  const [params, setParams] = useSearchParams();
  const view = VIEWS.includes(params.get("view")) ? params.get("view") : "documents";
  const setView = (v) =>
    setParams(v === "documents" ? {} : { view: v }, { replace: true });

  const [documents, setDocuments] = useState([]);
  const [renamingId, setRenamingId] = useState(null);
  const [quizHistory, setQuizHistory] = useState([]);
  const [stats, setStats] = useState(null);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    fetchDocs();
    getStats().then(setStats).catch(() => {});
  }, []);

  // Quiz history is only fetched when its tab is opened, and only once per
  // visit to it — it is not needed to render anything else.
  useEffect(() => {
    if (view !== "history") return;
    setLoadingHistory(true);
    getQuizHistory()
      .then(setQuizHistory)
      .catch(() => {})
      .finally(() => setLoadingHistory(false));
  }, [view]);

  const fetchDocs = async () => {
    setLoadingDocs(true);
    try {
      setDocuments(await listDocuments());
    } catch (_) {
      /* leave whatever is on screen */
    } finally {
      setLoadingDocs(false);
    }
  };

  const handleUploaded = async (docId) => {
    await fetchDocs();
    navigate(`/deck/${docId}`);
  };

  const handleDelete = async (docId) => {
    try {
      await deleteDocument(docId);
      setDocuments((d) => d.filter((doc) => doc.id !== docId));
      toast("Document deleted", "success");
    } catch (err) {
      toast(err.message, "error");
    }
  };

  const handleRename = async (docId, newName) => {
    try {
      await renameDocument(docId, newName);
      setDocuments((d) =>
        d.map((doc) => (doc.id === docId ? { ...doc, filename: newName } : doc))
      );
      setRenamingId(null);
      toast("Renamed", "success");
    } catch (err) {
      toast(err.message, "error");
    }
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    navigate("/");
  };

  // --- Views ---------------------------------------------------------------

  const documentsView = (
    <>
      <div className="mb-6">
        <h1 className="text-2xl">{greeting(user.name)}</h1>
        <p className="mt-1 text-sm text-base-content/60">
          Upload a PDF to generate flashcards and quizzes.
        </p>
      </div>

      {stats && (
        <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            label="Streak"
            value={`${stats.streak}d`}
            sub={stats.streak === 1 ? "day in a row" : "days in a row"}
          />
          <StatCard label="Quizzes" value={stats.total_quizzes} sub="taken" />
          <StatCard
            label="Avg score"
            value={stats.average_score != null ? `${stats.average_score.toFixed(0)}%` : "—"}
          />
          <StatCard label="Cards" value={stats.total_flashcards_reviewed} sub="reviewed" />
        </div>
      )}

      <div className="mb-8">
        <UploadZone onUploaded={handleUploaded} />
      </div>

      {loadingDocs && (
        <div className="flex justify-center py-10">
          <span className="loading loading-spinner loading-md text-primary" />
        </div>
      )}

      {!loadingDocs && documents.length === 0 && (
        <div className="rounded-xl border border-dashed border-base-300 py-12 text-center">
          <p className="text-3xl" aria-hidden="true">🌼</p>
          <h2 className="mt-3 text-lg">Nothing here yet</h2>
          <p className="mt-1 text-sm text-base-content/60">
            Upload a PDF to get started.
          </p>
        </div>
      )}

      {documents.length > 0 && (
        <div>
          <p className="mb-3 text-sm font-medium">Your documents</p>
          <div className="space-y-2">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="surface flex items-center justify-between gap-3 px-4 py-3"
              >
                {renamingId === doc.id ? (
                  <RenameInput
                    value={doc.filename}
                    onSave={(name) => handleRename(doc.id, name)}
                    onCancel={() => setRenamingId(null)}
                  />
                ) : (
                  <>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{doc.filename}</p>
                      <p className="mt-0.5 flex items-center gap-1.5 text-xs text-base-content/50">
                        {doc.page_count} pages
                        <span
                          className={`badge badge-xs ${
                            doc.status === "ready"
                              ? "badge-success"
                              : doc.status === "failed"
                                ? "badge-error"
                                : "badge-ghost"
                          }`}
                        >
                          {doc.status}
                        </span>
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-1">
                      {doc.status === "ready" && (
                        <button
                          onClick={() => navigate(`/deck/${doc.id}`)}
                          className="btn btn-primary btn-sm"
                        >
                          Study
                        </button>
                      )}

                      <div className="dropdown dropdown-end">
                        <div
                          tabIndex={0}
                          role="button"
                          className="btn btn-ghost btn-sm px-2"
                          aria-label="More options"
                        >
                          ⋯
                        </div>
                        {/* DaisyUI's dropdown is CSS-driven off :focus, so this
                            needs no outside-click handler of its own. */}
                        <ul
                          tabIndex={0}
                          className="menu dropdown-content z-20 w-40 rounded-box border border-base-300 bg-base-100 p-1.5 shadow-lift"
                        >
                          <li>
                            <button onClick={() => setRenamingId(doc.id)}>Rename</button>
                          </li>
                          <li>
                            <button onClick={() => navigate(`/deck/${doc.id}?edit=1`)}>
                              Edit cards
                            </button>
                          </li>
                          <li>
                            <button
                              onClick={() => handleDelete(doc.id)}
                              className="text-error"
                            >
                              Delete
                            </button>
                          </li>
                        </ul>
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );

  const historyView = (
    <>
      <h1 className="mb-6 text-2xl">Quiz history</h1>

      {loadingHistory && (
        <div className="flex justify-center py-10">
          <span className="loading loading-spinner loading-md text-primary" />
        </div>
      )}

      {!loadingHistory && quizHistory.length === 0 && (
        <div className="rounded-xl border border-dashed border-base-300 py-12 text-center">
          <p className="text-3xl" aria-hidden="true">📊</p>
          <h2 className="mt-3 text-lg">No quizzes yet</h2>
          <p className="mt-1 text-sm text-base-content/60">
            Take your first quiz to see your history here.
          </p>
        </div>
      )}

      <div className="space-y-2">
        {quizHistory.map((h) => (
          <button
            key={h.quiz_id}
            onClick={() => navigate(`/results/${h.quiz_id}`)}
            className="surface flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:border-primary/40"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{h.doc_filename}</p>
              <p className="mt-0.5 text-xs text-base-content/50">
                {h.completed_at
                  ? new Date(h.completed_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })
                  : "—"}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="font-semibold tabular-nums">
                {h.score}/{h.total}
              </p>
              <p className="text-xs text-base-content/50">{h.percentage.toFixed(0)}%</p>
            </div>
          </button>
        ))}
      </div>
    </>
  );

  return (
    <div className="min-h-screen bg-base-100">
      {/* Mobile header. The rail is desktop-only, so small screens get the
          same navigation as a horizontal tab strip below. */}
      <div className="sticky top-0 z-20 border-b border-base-300 bg-base-100/90 backdrop-blur md:hidden">
        <div className="flex h-14 items-center justify-between px-5">
          <Logo size="sm" to={null} />
          <button onClick={handleLogout} className="btn btn-ghost btn-xs">
            Sign out
          </button>
        </div>
        <div role="tablist" className="tabs tabs-bordered px-2">
          {NAV.map((item) => (
            <button
              key={item.id}
              role="tab"
              onClick={() => setView(item.id)}
              className={`tab tab-sm ${view === item.id ? "tab-active font-medium" : ""}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-base-300 bg-base-200/40 md:flex">
          <div className="flex h-16 items-center border-b border-base-300 px-5">
            <Logo />
          </div>

          <nav className="flex-1 space-y-1 p-3">
            {NAV.map((item) => (
              <button
                key={item.id}
                onClick={() => setView(item.id)}
                aria-current={view === item.id ? "page" : undefined}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                  view === item.id
                    ? "bg-primary text-primary-content font-medium"
                    : "text-base-content/70 hover:bg-base-300/60"
                }`}
              >
                <span aria-hidden="true">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </nav>

          <div className="border-t border-base-300 p-3">
            <div className="flex items-center justify-between gap-2 px-2 py-1.5">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium">{user.name}</p>
                <p className="truncate text-xs text-base-content/50">{user.email}</p>
              </div>
              <button
                onClick={handleLogout}
                className="btn btn-ghost btn-xs shrink-0"
                aria-label="Sign out"
              >
                ↩
              </button>
            </div>
          </div>
        </aside>

        <main className="w-full min-w-0 flex-1 px-5 py-8 sm:px-8">
          <div className="mx-auto max-w-3xl animate-fade-in">
            {view === "review" ? <ReviewQueue /> : view === "history" ? historyView : documentsView}
          </div>
        </main>
      </div>
    </div>
  );
}
