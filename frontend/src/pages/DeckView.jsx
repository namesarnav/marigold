import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getDocument, getFlashcards } from "../api.js";
import Navbar from "../components/Navbar.jsx";
import StudyMode from "../components/StudyMode.jsx";
import EditCards from "../components/EditCards.jsx";

export default function DeckView() {
  const { id: docId } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(null);
  const [flashcards, setFlashcards] = useState([]);
  const [view, setView] = useState("study"); // "study" | "edit"
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

  return (
    <div className="min-h-screen bg-cream">
      <Navbar />
      <main className="max-w-3xl mx-auto px-6 py-8">
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
              setLoading(true);
              try {
                const cards = await getFlashcards(docId);
                setFlashcards(cards);
              } catch (_) {}
              finally { setLoading(false); }
              setView("study");
            }}
          />
        )}
      </main>
    </div>
  );
}
