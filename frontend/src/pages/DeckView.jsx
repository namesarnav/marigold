import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { getDocument, getFlashcards } from "../api.js";
import EditCards from "../components/EditCards.jsx";
import Navbar from "../components/Navbar.jsx";
import StudyMode from "../components/StudyMode.jsx";

export default function DeckView() {
  const { id: docId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [doc, setDoc] = useState(null);
  const [flashcards, setFlashcards] = useState([]);
  const [view, setView] = useState(searchParams.get("edit") === "1" ? "edit" : "study");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [docData, cards] = await Promise.all([
          getDocument(docId),
          getFlashcards(docId),
        ]);
        setDoc(docData);
        setFlashcards(cards);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [docId]);

  const docName = doc?.filename?.replace(/\.pdf$/i, "") ?? "";

  const reloadCards = async () => {
    setLoading(true);
    try {
      setFlashcards(await getFlashcards(docId));
    } catch (_) {
      /* the existing cards stay on screen */
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-base-100">
      <Navbar />

      <main className="page max-w-3xl py-8">
        <div className="mb-6">
          <button
            onClick={() => navigate("/dashboard")}
            className="btn btn-ghost btn-xs -ml-2 gap-1 text-base-content/60"
          >
            ← Dashboard
          </button>
          {docName && <h1 className="mt-2 truncate text-2xl">{docName}</h1>}
        </div>

        {!loading && !error && (
          <div role="tablist" className="tabs tabs-bordered mb-6">
            <button
              role="tab"
              onClick={() => setView("study")}
              className={`tab ${view === "study" ? "tab-active font-medium" : ""}`}
            >
              Study
            </button>
            <button
              role="tab"
              onClick={() => setView("edit")}
              className={`tab ${view === "edit" ? "tab-active font-medium" : ""}`}
            >
              Edit cards
            </button>
          </div>
        )}

        {loading && (
          <div className="flex justify-center py-16">
            <span className="loading loading-spinner loading-lg text-primary" />
          </div>
        )}

        {error && !loading && (
          <div role="alert" className="alert alert-error">
            <span className="text-sm">{error}</span>
          </div>
        )}

        {!loading && !error && view === "study" && (
          <StudyMode
            cards={flashcards}
            docId={docId}
            onStartQuiz={() => navigate(`/quiz/${docId}`)}
            onBack={() => navigate("/dashboard")}
            onReloadCards={(newCards) => setFlashcards(newCards)}
          />
        )}

        {!loading && !error && view === "edit" && (
          <EditCards
            docId={docId}
            docName={docName}
            onBack={async () => {
              await reloadCards();
              setView("study");
            }}
          />
        )}
      </main>
    </div>
  );
}
