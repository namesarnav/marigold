import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext.jsx";
import { ToastProvider } from "./toast.jsx";
import GuestRoute from "./components/GuestRoute.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import DeckView from "./pages/DeckView.jsx";
import QuizModePage from "./pages/QuizModePage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";
import Pricing from "./pages/Pricing.jsx";
import VerifyEmail from "./pages/VerifyEmail.jsx";
import OAuthCallback from "./pages/OAuthCallback.jsx";
// Password reset is disabled: it works by emailing a link, and no email
// delivery is configured (EMAIL_BACKEND=console only logs). Uncomment these
// imports and the two routes below once EMAIL_BACKEND=ses is set up.
// import ForgotPassword from "./pages/ForgotPassword.jsx";
// import ResetPassword from "./pages/ResetPassword.jsx";
import PlanNotReady from "./pages/PlanNotReady.jsx";
import NotFound from "./pages/NotFound.jsx";

/**
 * Every route falls into one of three groups, and the wrapper says which.
 *
 *   public      — renders the same signed in or out.
 *   GuestRoute  — signed-out only; a signed-in visitor is sent onward.
 *   Protected   — signed-in and verified only; anyone else is sent to sign in,
 *                 with the destination carried along so they arrive here after.
 *
 * Nothing is left to a page to enforce for itself. A page that checks its own
 * session is a page that can be added later without the check.
 */
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            {/* --- Public ------------------------------------------------ */}
            <Route path="/" element={<Landing />} />
            <Route path="/pricing" element={<Pricing />} />
            {/* Where the paid plans' buttons go until payments exist. */}
            <Route path="/checkout/:plan" element={<PlanNotReady />} />

            {/* Landing points for a redirect from outside the SPA — the
                emailed confirmation link, and the OAuth callback. Public
                because each exists to establish a session for someone who
                does not have one yet, and neither can be guest-gated: both
                are reached part-way through acquiring the session that a
                guest gate would then bounce. */}
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="/oauth/callback" element={<OAuthCallback />} />

            {/* Public for the same reason: someone who has forgotten their
                password by definition cannot sign in first. Left reachable
                while signed in too — there is no in-app way to change a
                password, so redirecting a signed-in user who followed their
                own reset link would strand them. */}
            {/* Disabled until email delivery exists; see the imports above.
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            */}

            {/* --- Signed out only --------------------------------------- */}
            <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
            <Route
              path="/register"
              element={<GuestRoute><Register /></GuestRoute>}
            />

            {/* --- Signed in and verified -------------------------------- */}
            <Route
              path="/dashboard"
              element={<ProtectedRoute><Dashboard /></ProtectedRoute>}
            />
            <Route
              path="/deck/:id"
              element={<ProtectedRoute><DeckView /></ProtectedRoute>}
            />
            <Route
              path="/quiz/:id"
              element={<ProtectedRoute><QuizModePage /></ProtectedRoute>}
            />
            <Route
              path="/results/:id"
              element={<ProtectedRoute><ResultsPage /></ProtectedRoute>}
            />

            {/* Rendered, not redirected, so the failing URL stays in the
                address bar and can be reported. */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
