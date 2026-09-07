import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { completeOAuthLogin, getMe } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout from "../components/AuthLayout.jsx";

/**
 * Where a provider sign-in comes back to.
 *
 * By the time the browser gets here the backend has done the whole exchange —
 * validated `state`, fetched the profile, resolved or created the account — and
 * set the httpOnly refresh cookie on its redirect. The only work left is
 * trading that cookie for an access token.
 *
 * Failures never reach this page: the callback redirects those to
 * /login?error=…, which Login renders. Getting here and still failing means the
 * cookie did not survive the redirect.
 */
export default function OAuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [failed, setFailed] = useState(false);

  // The refresh token rotates on every use, so a second run would spend the one
  // the first just consumed. StrictMode's double mount does exactly that.
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

  if (failed) {
    return (
      <AuthLayout
        title="Sign-in didn't complete"
        subtitle="We couldn't finish setting up your session. Please try again."
      >
        <Link to="/login" className="btn btn-primary w-full">
          Back to sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Signing you in" subtitle="One moment.">
      <div className="flex justify-center py-2">
        <span className="loading loading-spinner loading-lg text-primary" />
      </div>
    </AuthLayout>
  );
}
