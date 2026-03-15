import { useState, useEffect } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { getDocument, getFlashcards } from "../api.js";
import Navbar from "../components/Navbar.jsx";
import StudyMode from "../components/StudyMode.jsx";
import EditCards from "../components/EditCards.jsx";

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
      const cards = await getFlashcards(docId);
      setFlashcards(cards);
    } catch (_) {}
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-cream">
      <Navbar />
      <main className="max-w-3xl mx-auto px-6 py-8">
        {/* Tab bar */}
        {!loading && !error && (
          <div className="flex items-center gap-1 mb-6 border-b border-fl-border">
            <button
              onClick={() => setView("study")}
              className={`px-4 py-2 text-sm font-sans font-medium transition-colors border-b-2 -mb-px ${
                view === "study"
                  ? "border-fl-black text-fl-black"
                  : "border-transparent text-fl-muted hover:text-fl-black"
              }`}
            >
              Study
            </button>
            <button
              onClick={() => setView("edit")}
              className={`px-4 py-2 text-sm font-sans font-medium transition-colors border-b-2 -mb-px ${
                view === "edit"
                  ? "border-fl-black text-fl-black"
                  : "border-transparent text-fl-muted hover:text-fl-black"
              }`}
            >
              Edit cards
            </button>
          </div>
        )}

        {loading && (
          <div className="flex items-center gap-3 text-sm text-fl-muted font-sans py-16">
            <span className="h-5 w-5 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
            Loading…
          </div>
        )}

        {error && !loading && (
          <p className="text-sm text-fl-red font-sans py-4">{error}</p>
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
