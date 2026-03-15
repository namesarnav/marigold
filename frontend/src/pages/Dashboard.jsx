import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  listDocuments, deleteDocument, renameDocument,
  logout, getQuizHistory, getStats,
} from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "../toast.jsx";
import UploadZone from "../components/UploadZone.jsx";

function greeting(name) {
  const h = new Date().getHours();
  const part = h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
  return `Good ${part}, ${name.split(" ")[0]}.`;
}

function StatCard({ label, value, sub }) {
  return (
    <div
      className="bg-fl-card border border-fl-border rounded-xl px-4 py-3 flex-1 min-w-[110px]"
      style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
    >
      <p className="text-[11px] font-sans font-medium text-fl-muted uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-serif text-fl-black leading-none">{value}</p>
      {sub && <p className="text-[11px] font-sans text-fl-muted mt-0.5">{sub}</p>}
    </div>
  );
}

function DocMenu({ doc, onRename, onEditCards, onDelete }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="h-7 w-7 flex items-center justify-center rounded-lg border border-fl-border text-fl-muted hover:border-fl-black hover:text-fl-black transition-all text-sm"
        title="More options"
      >
        ···
      </button>
      {open && (
        <div
          className="absolute right-0 top-9 z-20 bg-fl-card border border-fl-border rounded-xl shadow-lg py-1 w-40"
          style={{ boxShadow: "0 8px 24px rgba(40,40,40,0.10)" }}
        >
          <button
            onClick={() => { setOpen(false); onRename(); }}
            className="w-full text-left px-4 py-2 text-sm font-sans text-fl-black hover:bg-fl-border/40 transition-colors"
          >
            Rename
          </button>
          <button
            onClick={() => { setOpen(false); onEditCards(); }}
            className="w-full text-left px-4 py-2 text-sm font-sans text-fl-black hover:bg-fl-border/40 transition-colors"
          >
            Edit cards
          </button>
          <div className="h-px bg-fl-border mx-2 my-1" />
          <button
            onClick={() => { setOpen(false); onDelete(); }}
            className="w-full text-left px-4 py-2 text-sm font-sans text-fl-red hover:bg-fl-border/40 transition-colors"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function RenameInput({ value, onSave, onCancel }) {
  const [val, setVal] = useState(value);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const submit = () => { if (val.trim()) onSave(val.trim()); };

  return (
    <div className="flex items-center gap-2 flex-1 mr-2">
      <input
        ref={inputRef}
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") submit(); if (e.key === "Escape") onCancel(); }}
        className="flex-1 bg-cream border-[1.5px] border-fl-black rounded-lg px-2 py-1 text-sm font-sans text-fl-black focus:outline-none"
      />
      <button onClick={submit} className="text-xs font-sans text-fl-black font-semibold hover:text-fl-muted transition-colors">Save</button>
      <button onClick={onCancel} className="text-xs font-sans text-fl-muted hover:text-fl-black transition-colors">Cancel</button>
    </div>
  );
}

function Sidebar({ view, setView, user, onLogout }) {
  return (
    <aside className="hidden md:flex flex-col w-60 border-r border-fl-border bg-cream shrink-0 min-h-screen">
      <div className="flex items-center gap-2 px-6 py-5 border-b border-fl-border">
        <div className="h-7 w-7 rounded-lg bg-fl-yellow flex items-center justify-center text-fl-black text-xs font-bold font-sans">🌼</div>
        <span className="font-serif text-lg text-fl-black">Marigold</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {[
          { id: "documents", label: "My Documents", icon: "📄" },
          { id: "history",   label: "Quiz History",  icon: "📊" },
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => setView(item.id)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-sans font-medium transition-all ${
              view === item.id
                ? "bg-fl-yellow text-fl-black"
                : "text-fl-muted hover:text-fl-black hover:bg-fl-border/40"
            }`}
          >
            <span className="text-base">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      <div className="px-3 pb-5 pt-3 border-t border-fl-border">
        <div className="flex items-center justify-between px-3 py-2">
          <div>
            <p className="text-xs font-sans font-medium text-fl-black truncate max-w-[120px]">{user.name}</p>
            <p className="text-[11px] font-sans text-fl-muted truncate max-w-[120px]">{user.email}</p>
          </div>
          <button onClick={onLogout} className="text-xs font-sans text-fl-muted hover:text-fl-red transition-colors" title="Sign out">↩</button>
        </div>
      </div>
    </aside>
  );
}

export default function Dashboard() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [view, setView] = useState("documents");
  const [documents, setDocuments] = useState([]);
  const [renamingId, setRenamingId] = useState(null);
  const [quizHistory, setQuizHistory] = useState([]);
  const [stats, setStats] = useState(null);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const toast = useToast();

  useEffect(() => {
    fetchDocs();
    getStats().then(setStats).catch(() => {});
  }, []);

  const fetchDocs = async () => {
    setLoadingDocs(true);
    try { setDocuments(await listDocuments()); } catch (_) {}
    finally { setLoadingDocs(false); }
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
      setDocuments((d) => d.map((doc) => doc.id === docId ? { ...doc, filename: newName } : doc));
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

  const handleViewHistory = async () => {
    setView("history");
    setLoadingHistory(true);
    try { setQuizHistory(await getQuizHistory()); } catch (_) {}
    finally { setLoadingHistory(false); }
  };

  const setViewWithSideEffects = (v) => {
    if (v === "history") handleViewHistory();
    else setView(v);
  };

  const renderMain = () => {
    if (view === "history") {
      return (
        <div>
          <h2 className="text-2xl font-serif text-fl-black mb-6">Quiz History</h2>
          {loadingHistory && (
            <div className="flex items-center gap-3 text-sm text-fl-muted font-sans">
              <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
              Loading…
            </div>
          )}
          {!loadingHistory && quizHistory.length === 0 && (
            <div className="text-center py-16">
              <p className="text-3xl font-serif text-fl-black mb-2">No quizzes yet.</p>
              <p className="text-sm text-fl-muted font-sans">Take your first quiz to see your history here.</p>
            </div>
          )}
          <div className="space-y-2">
            {quizHistory.map((h) => (
              <div
                key={h.quiz_id}
                className="bg-fl-card border border-fl-border rounded-xl px-5 py-4 flex items-center justify-between"
                style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
              >
                <div>
                  <p className="text-sm font-sans font-medium text-fl-black">{h.doc_filename}</p>
                  <p className="text-xs font-sans text-fl-muted mt-0.5">
                    {h.completed_at ? new Date(h.completed_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "—"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-base font-serif text-fl-black">{h.score}/{h.total}</p>
                  <p className="text-xs font-sans text-fl-muted">{h.percentage.toFixed(0)}%</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    }

    // Documents view (default)
    return (
      <div>
        <h2 className="text-2xl font-serif text-fl-black mb-1">{greeting(user.name)}</h2>
        <p className="text-sm text-fl-muted font-sans mb-6">Upload a PDF to generate flashcards and quizzes.</p>

        {stats && (
          <div className="flex gap-3 flex-wrap mb-8">
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
            <StatCard label="Cards reviewed" value={stats.total_flashcards_reviewed} />
          </div>
        )}

        <div className="mb-8">
          <UploadZone onUploaded={handleUploaded} />
        </div>

        {loadingDocs && (
          <div className="flex items-center gap-3 text-sm text-fl-muted font-sans">
            <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
            Loading…
          </div>
        )}

        {!loadingDocs && documents.length === 0 && (
          <div className="text-center py-12 border border-dashed border-fl-border rounded-xl">
            <p className="text-2xl font-serif text-fl-black mb-2">Nothing here yet.</p>
            <p className="text-sm text-fl-muted font-sans">Upload a PDF to get started. Your flashcards<br />and quizzes will appear here.</p>
          </div>
        )}

        {documents.length > 0 && (
          <div>
            <p className="text-sm font-sans font-semibold text-fl-black mb-3">Your documents</p>
            <div className="space-y-2">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="bg-fl-card border border-fl-border rounded-xl px-5 py-4 flex items-center justify-between card-hover"
                  style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
                >
                  <div className="min-w-0 mr-4 flex-1">
                    {renamingId === doc.id ? (
                      <RenameInput
                        value={doc.filename}
                        onSave={(name) => handleRename(doc.id, name)}
                        onCancel={() => setRenamingId(null)}
                      />
                    ) : (
                      <>
                        <p className="text-sm font-sans font-medium text-fl-black truncate">{doc.filename}</p>
                        <p className="text-xs font-sans text-fl-muted mt-0.5">{doc.page_count} pages · {doc.status}</p>
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {doc.status === "ready" && (
                      <button
                        onClick={() => navigate(`/deck/${doc.id}`)}
                        className="btn-press px-3 py-1.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-xs font-sans font-semibold transition-colors"
                      >
                        Study
                      </button>
                    )}
                    <DocMenu
                      doc={doc}
                      onRename={() => setRenamingId(doc.id)}
                      onEditCards={() => navigate(`/deck/${doc.id}?edit=1`)}
                      onDelete={() => handleDelete(doc.id)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex min-h-screen bg-cream">
      <Sidebar view={view} setView={setViewWithSideEffects} user={user} onLogout={handleLogout} />

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 inset-x-0 z-10 flex items-center justify-between px-4 py-3 bg-cream border-b border-fl-border">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-md bg-fl-yellow flex items-center justify-center text-fl-black text-[10px] font-bold font-sans">M</div>
          <span className="font-serif text-base text-fl-black">Marigold</span>
        </div>
        <button onClick={handleLogout} className="text-xs font-sans text-fl-muted">Sign out</button>
      </div>

      {/* Main content */}
      <main className="flex-1 px-6 md:px-10 py-8 md:py-10 mt-12 md:mt-0 max-w-4xl">
        {renderMain()}
      </main>
    </div>
  );
}
