import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import RouteSpinner from "./RouteSpinner.jsx";
import VerifyEmailGate from "./VerifyEmailGate.jsx";

/**
 * Signed in, and confirmed, before any protected page renders.
 *
 * The verification check lives here rather than in each page for the same
 * reason the backend puts it in one dependency: every route wrapped in this is
 * covered automatically, including any added later. The two gates mirror each
 * other — if this one is ever bypassed the API still refuses.
 */
export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <RouteSpinner />;

  // Carry where they were trying to go. A shared link to /deck/12 otherwise
  // costs two navigations: bounced to the form, then dropped on the dashboard
  // with the deck they actually wanted nowhere in sight.
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;

  // `verification_required` is the server telling us whether it is enforcing
  // the gate. Checking it keeps the two halves from disagreeing: with the gate
  // off the API serves an unverified account normally, and blocking it in the
  // UI anyway would leave the app unusable for a reason the backend no longer
  // holds. It defaults to true, so an older server still gets gated.
  const gated = user.verification_required !== false;
  if (gated && !user.email_verified) return <VerifyEmailGate />;

  return children;
}
