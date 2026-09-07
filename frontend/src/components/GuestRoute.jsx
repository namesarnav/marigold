import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { returnTo } from "../returnTo.js";
import RouteSpinner from "./RouteSpinner.jsx";

/**
 * The mirror of ProtectedRoute: for pages that only make sense signed *out*.
 *
 * Without this, a signed-in user following a stale /login link gets the form
 * again, signs in a second time, and the app quietly issues a fresh session
 * over the one they already had. Sending them where they were going instead is
 * both what they meant and one fewer token rotation.
 *
 * Deliberately narrow. It wraps /login and /register only — not the other
 * signed-out screens:
 *
 *   /verify-email and /oauth/callback are landing points for a redirect from
 *   outside the SPA, and both are reached *while* a session is being
 *   established; bouncing them would break the flow they complete.
 *
 *   /forgot-password and /reset-password stay reachable because there is no
 *   in-app way to change a password. Redirecting a signed-in user away from a
 *   reset link they legitimately requested would be a dead end.
 */
export default function GuestRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <RouteSpinner />;

  if (user) {
    // Honour the destination ProtectedRoute stashed on the way in, so a user
    // who was bounced from /deck/12, signed in elsewhere, and then hit Back
    // still ends up at /deck/12 rather than the dashboard.
    return <Navigate to={returnTo(location)} replace />;
  }

  return children;
}
