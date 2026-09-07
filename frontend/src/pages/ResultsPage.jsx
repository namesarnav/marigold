import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import QuizReview from "../components/QuizReview.jsx";
import Results from "../components/Results.jsx";

export default function ResultsPage() {
  const { id: quizId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const docId = location.state?.docId;

  const [showReview, setShowReview] = useState(false);

  return (
    <div className="min-h-screen bg-base-100">
      <Navbar />
      <main className="page max-w-3xl py-8">
        {showReview ? (
          <QuizReview
            quizId={quizId}
            onRetake={() => (docId ? navigate(`/quiz/${docId}`) : navigate("/dashboard"))}
            onBack={() => setShowReview(false)}
          />
        ) : (
          <Results
            quizId={quizId}
            onRetry={() => (docId ? navigate(`/quiz/${docId}`) : navigate("/dashboard"))}
            onExit={() => (docId ? navigate(`/deck/${docId}`) : navigate("/dashboard"))}
            onReview={() => setShowReview(true)}
          />
        )}
      </main>
    </div>
  );
}
