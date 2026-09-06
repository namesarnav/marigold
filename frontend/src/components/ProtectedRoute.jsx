import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import VerifyEmailGate from "./VerifyEmailGate.jsx";

/**
 * Signed in, and confirmed, before any protected page renders.
 *
 * The verification check lives here rather than in each page for the same
 * reason the backend puts it in one dependency: every route wrapped in this is
 * covered automatically, including any added later. The two gates mirror each
 * other — if this one is ever bypassed the API still refuses, so the worst case
 * is an ugly error rather than an unverified account reaching real data.
 */
export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center">
        <span className="h-6 w-6 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;
  if (!user.email_verified) return <VerifyEmailGate />;
  return children;
}
