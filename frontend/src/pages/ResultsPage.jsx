import { useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import Results from "../components/Results.jsx";
import QuizReview from "../components/QuizReview.jsx";

export default function ResultsPage() {
  const { id: quizId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const docId = location.state?.docId;

  const [showReview, setShowReview] = useState(false);

  return (
    <div className="min-h-screen bg-cream">
      <Navbar />
      <main className="max-w-3xl mx-auto px-6 py-8">
        {showReview ? (
          <QuizReview
            quizId={quizId}
            onRetake={() => docId ? navigate(`/quiz/${docId}`) : navigate("/dashboard")}
            onBack={() => setShowReview(false)}
          />
        ) : (
          <Results
            quizId={quizId}
            onRetry={() => docId ? navigate(`/quiz/${docId}`) : navigate("/dashboard")}
            onExit={() => docId ? navigate(`/deck/${docId}`) : navigate("/dashboard")}
            onReview={() => setShowReview(true)}
          />
        )}
      </main>
    </div>
  );
}
