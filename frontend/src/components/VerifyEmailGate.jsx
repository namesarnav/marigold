import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, logout, resendVerification } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import Navbar from "./Navbar.jsx";

/**
 * What an unverified account sees instead of the app.
 *
 * The backend gates every core feature behind `get_verified_user`, so before
 * this existed a new account could sign in, reach the dashboard, and get a 403
 * from every request it made — with nothing in the UI able to resolve it,
 * because no screen had ever asked the user to confirm their address. This is
 * the frontend half of that gate: one screen, rendered in place of any
 * protected page, that explains the state and can send the email again.
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
      // Mostly the 429 from the per-address hourly limit, whose message is
      // already written for a reader.
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
   * confirmation happened — verified everywhere except here, with no way
   * forward but a manual reload. Re-fetching drops the gate in place.
   */
  const handleRecheck = async () => {
    setError("");
    setChecking(true);
    try {
      const fresh = await getMe();
      // Setting this re-renders ProtectedRoute, which stops gating as soon as
      // the flag is true; if it is still false the screen simply stays.
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
    <div className="min-h-screen bg-cream flex flex-col">
      <Navbar />

      <div className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-md animate-fade-up text-center">
          <div className="text-4xl mb-5">✉️</div>

          <h1 className="text-3xl font-serif text-fl-black mb-3">
            Confirm your email.
          </h1>

          <p className="text-sm text-fl-muted font-sans mb-2">
            We sent a link to
          </p>
          <p className="text-[15px] font-sans font-semibold text-fl-black mb-6">
            {user?.email}
          </p>

          <p className="text-sm text-fl-muted font-sans mb-8 leading-relaxed">
            Click it to unlock uploads, flashcards and quizzes. The link expires
            in 24&nbsp;hours.
          </p>

          {sent ? (
            // Deliberately not "we sent another one": the endpoint answers the
            // same way whether or not it actually sent, so that it cannot be
            // used to probe which addresses have accounts. Claiming delivery
            // would be a promise the API never made.
            <p className="text-sm font-sans text-fl-green mb-4">
              If that address still needs confirming, a new link is on its way.
            </p>
          ) : (
            <button
              onClick={handleResend}
              disabled={sending}
              className="btn-press w-full py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold disabled:opacity-60 transition-colors"
            >
              {sending ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
                  Sending…
                </span>
              ) : "Resend the link"}
            </button>
          )}

          <button
            onClick={handleRecheck}
            disabled={checking}
            className="btn-press w-full mt-3 py-3 rounded-lg bg-fl-card border-[1.5px] border-fl-border hover:border-fl-black text-fl-black text-[15px] font-sans font-medium disabled:opacity-60 transition-colors"
          >
            {checking ? "Checking…" : "I've confirmed it"}
          </button>

          {error && (
            <p className="text-sm text-fl-red font-sans mt-4">{error}</p>
          )}

          <p className="mt-8 text-sm text-fl-muted font-sans">
            Wrong address?{" "}
            <button
              onClick={handleSignOut}
              className="text-fl-black font-semibold underline underline-offset-2 hover:opacity-70 transition-opacity"
            >
              Sign out
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
