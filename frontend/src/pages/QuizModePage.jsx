import { useParams, useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import QuizMode from "../components/QuizMode.jsx";

export default function QuizModePage() {
  const { id: docId } = useParams();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-cream">
      <Navbar />
      <main className="max-w-3xl mx-auto px-6 py-8">
        <QuizMode
          docId={docId}
          onExit={() => navigate(`/deck/${docId}`)}
          onComplete={(quizId) => navigate(`/results/${quizId}`, { state: { docId } })}
        />
      </main>
    </div>
  );
}
