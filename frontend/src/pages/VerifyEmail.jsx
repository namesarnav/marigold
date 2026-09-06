import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getMe, verifyEmail } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import Navbar from "../components/Navbar.jsx";

/**
 * Where the emailed confirmation link lands.
 *
 * The token is spent immediately on mount — there is no "click to confirm"
 * step, because arriving here *is* the click. The backend returns a full
 * session for it, so this also signs the account in: following the link in a
 * browser that was never logged in goes straight to the dashboard instead of
 * to a login form.
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
        // actually readable rather than a flash.
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

  return (
    <div className="min-h-screen bg-cream flex flex-col">
      <Navbar />

      <div className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-md animate-fade-up text-center">
          {status === "working" && (
            <>
              <span className="inline-block h-7 w-7 border-2 border-fl-black border-t-transparent rounded-full animate-spin mb-6" />
              <h1 className="text-3xl font-serif text-fl-black mb-2">
                Confirming your email…
              </h1>
              <p className="text-sm text-fl-muted font-sans">One moment.</p>
            </>
          )}

          {status === "done" && (
            <>
              <div className="text-4xl mb-5">✓</div>
              <h1 className="text-3xl font-serif text-fl-black mb-2">
                You're all set.
              </h1>
              <p className="text-sm text-fl-muted font-sans">
                Taking you to your dashboard…
              </p>
            </>
          )}

          {status === "missing" && (
            <>
              <h1 className="text-3xl font-serif text-fl-black mb-3">
                Nothing to confirm.
              </h1>
              <p className="text-sm text-fl-muted font-sans mb-8">
                This link is missing its token. Open the most recent link from
                your inbox, or request a new one after signing in.
              </p>
              <Link
                to="/login"
                className="btn-press inline-block px-6 py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold transition-colors"
              >
                Go to sign in
              </Link>
            </>
          )}

          {status === "failed" && (
            <>
              <h1 className="text-3xl font-serif text-fl-black mb-3">
                That link didn't work.
              </h1>
              <p className="text-sm text-fl-muted font-sans mb-8">
                {error || "The link may have expired or already been used."}
              </p>
              {/* Signing in lands on the gate, which is where a fresh link is
                  requested — so this is the route back rather than a dead end. */}
              <Link
                to="/login"
                className="btn-press inline-block px-6 py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold transition-colors"
              >
                Sign in to get a new link
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
