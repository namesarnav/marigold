import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { completeOAuthLogin, getMe } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import Navbar from "../components/Navbar.jsx";

/**
 * Where a provider sign-in comes back to.
 *
 * By the time the browser gets here the backend has already done the whole
 * exchange — validated `state`, fetched the profile, resolved or created the
 * account — and set the httpOnly refresh cookie on its redirect. The only work
 * left on this side is trading that cookie for an access token, which is what
 * `completeOAuthLogin` does.
 *
 * Failures never reach this page: the callback redirects those to
 * /login?error=…, which Login renders. Getting here and still failing means the
 * cookie did not survive the redirect — a browser blocking it, or a mismatch
 * between the domain the cookie was set on and the one that loaded this page.
 */
export default function OAuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [failed, setFailed] = useState(false);

  // The refresh token rotates on every use, so a second run would spend the
  // one the first just consumed. StrictMode's double mount in development does
  // exactly that without this guard.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    let cancelled = false;

    (async () => {
      const ok = await completeOAuthLogin().catch(() => false);
      if (cancelled) return;

      if (!ok) {
        setFailed(true);
        return;
      }

      try {
        const user = await getMe();
        if (cancelled) return;
        setUser(user);
        // A provider-verified address arrives already confirmed, so this lands
        // on the dashboard rather than the verification gate.
        navigate("/dashboard", { replace: true });
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen bg-cream flex flex-col">
      <Navbar />

      <div className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-md animate-fade-up text-center">
          {failed ? (
            <>
              <h1 className="text-3xl font-serif text-fl-black mb-3">
                Sign-in didn't complete.
              </h1>
              <p className="text-sm text-fl-muted font-sans mb-8">
                We couldn't finish setting up your session. Please try again.
              </p>
              <Link
                to="/login"
                className="btn-press inline-block px-6 py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold transition-colors"
              >
                Back to sign in
              </Link>
            </>
          ) : (
            <>
              <span className="inline-block h-7 w-7 border-2 border-fl-black border-t-transparent rounded-full animate-spin mb-6" />
              <h1 className="text-3xl font-serif text-fl-black mb-2">
                Signing you in…
              </h1>
              <p className="text-sm text-fl-muted font-sans">One moment.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
