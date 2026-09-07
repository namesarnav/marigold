import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, logout, resendVerification } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout from "./AuthLayout.jsx";

/**
 * What an unverified account sees instead of the app.
 *
 * The backend gates every core feature behind `get_verified_user`, so before
 * this existed a new account could sign in, reach the dashboard, and get a 403
 * from every request it made — with nothing in the UI able to resolve it. This
 * is the frontend half of that gate.
 */
export default function VerifyEmailGate() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");

  const handleResend = async () => {
    setError("");
    setSending(true);
    try {
      await resendVerification(user.email);
      setSent(true);
    } catch (err) {
      // Mostly the 429 from the per-address hourly limit.
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  /**
   * Re-read the account after the user confirms somewhere else.
   *
   * The link almost always opens in a different tab, or on a phone, which
   * leaves this one showing the gate against a user object fetched before the
   * confirmation happened — verified everywhere except here.
   */
  const handleRecheck = async () => {
    setError("");
    setChecking(true);
    try {
      const fresh = await getMe();
      setUser(fresh);
      if (!fresh.email_verified) {
        setError("Still waiting on that confirmation. Check your inbox.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  };

  const handleSignOut = async () => {
    await logout();
    setUser(null);
    navigate("/login");
  };

  return (
    <AuthLayout
      title="Confirm your email"
      subtitle={
        <>
          We sent a link to{" "}
          <span className="font-medium text-base-content">{user?.email}</span>.
          Click it to unlock uploads, flashcards and quizzes — it expires in 24 hours.
        </>
      }
      footer={
        <>
          Wrong address?{" "}
          <button onClick={handleSignOut} className="link link-hover font-medium text-base-content">
            Sign out
          </button>
        </>
      }
    >
      <div className="space-y-2.5">
        {sent ? (
          // Deliberately not "we sent another one": the endpoint answers the
          // same way whether or not it actually sent, so that it cannot be used
          // to probe which addresses have accounts.
          <div role="status" className="alert alert-success py-2.5">
            <span className="text-sm">
              If that address still needs confirming, a new link is on its way.
            </span>
          </div>
        ) : (
          <button onClick={handleResend} disabled={sending} className="btn btn-primary w-full">
            {sending && <span className="loading loading-spinner loading-sm" />}
            {sending ? "Sending…" : "Resend the link"}
          </button>
        )}

        <button onClick={handleRecheck} disabled={checking} className="btn btn-outline w-full">
          {checking && <span className="loading loading-spinner loading-sm" />}
          {checking ? "Checking…" : "I've confirmed it"}
        </button>
      </div>

      {error && (
        <div role="alert" className="alert alert-error mt-4 py-2.5">
          <span className="text-sm">{error}</span>
        </div>
      )}
    </AuthLayout>
  );
}
