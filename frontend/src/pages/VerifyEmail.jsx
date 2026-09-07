import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getMe, verifyEmail } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout from "../components/AuthLayout.jsx";

/**
 * Where the emailed confirmation link lands.
 *
 * The token is spent immediately on mount — there is no "click to confirm"
 * step, because arriving here *is* the click. The backend returns a full
 * session for it, so this also signs the account in: following the link in a
 * browser that was never logged in goes straight to the dashboard.
 */
export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const { setUser } = useAuth();

  const [status, setStatus] = useState(token ? "working" : "missing");
  const [error, setError] = useState("");

  // Tokens are single-use, so spending one twice fails. React 18's StrictMode
  // mounts effects twice in development, which without this guard consumed the
  // token on the first pass and reported "already used" from the second.
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;

    let cancelled = false;

    (async () => {
      try {
        await verifyEmail(token);
        const user = await getMe();
        if (cancelled) return;
        setUser(user);
        setStatus("done");
        // A beat on the confirmation before moving on, so the outcome is
        // readable rather than a flash.
        setTimeout(() => navigate("/dashboard", { replace: true }), 1200);
      } catch (err) {
        if (cancelled) return;
        setError(err.message);
        setStatus("failed");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, navigate, setUser]);

  if (status === "working") {
    return (
      <AuthLayout title="Confirming your email" subtitle="One moment.">
        <div className="flex justify-center py-2">
          <span className="loading loading-spinner loading-lg text-primary" />
        </div>
      </AuthLayout>
    );
  }

  if (status === "done") {
    return (
      <AuthLayout title="You're all set" subtitle="Taking you to your dashboard…">
        <div className="flex justify-center py-2">
          <span className="text-4xl" aria-hidden="true">✓</span>
        </div>
      </AuthLayout>
    );
  }

  if (status === "missing") {
    return (
      <AuthLayout
        title="Nothing to confirm"
        subtitle="This link is missing its token. Open the most recent link from your inbox, or request a new one after signing in."
      >
        <Link to="/login" className="btn btn-primary w-full">
          Go to sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="That link didn't work"
      subtitle={error || "The link may have expired or already been used."}
    >
      {/* Signing in lands on the gate, which is where a fresh link is
          requested — so this is the route back rather than a dead end. */}
      <Link to="/login" className="btn btn-primary w-full">
        Sign in to get a new link
      </Link>
    </AuthLayout>
  );
}
