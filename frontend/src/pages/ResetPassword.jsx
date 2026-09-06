import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api.js";
import { checkPassword, PASSWORD_HINT } from "../passwordPolicy.js";
import Navbar from "../components/Navbar.jsx";

const INPUT_CLASS =
  "w-full bg-fl-card border-[1.5px] border-fl-border rounded-lg px-4 py-3 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black transition-colors";

/**
 * Choose a new password from an emailed reset link.
 *
 * Unlike /verify-email nothing happens on mount: the token is only spent when
 * the form is submitted. Landing here must not consume the link, or previewing
 * the email — or any scanner that follows links in it — would burn the reset
 * before the user typed anything.
 *
 * There is no session at the end. The backend revokes every refresh token as
 * part of the reset, so this finishes at the login form rather than the
 * dashboard.
 */
export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Shown under the field as the user types, but only once they have typed
  // something — an empty form should not open with a complaint.
  const policyError = password ? checkPassword(password) : "";
  const mismatch = confirm.length > 0 && confirm !== password;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    // Checked here as well as on the server, purely to save a round trip that
    // can only end in a 422.
    const problem = checkPassword(password);
    if (problem) return setError(problem);
    if (password !== confirm) return setError("Those passwords don't match.");

    setLoading(true);
    try {
      await resetPassword(token, password);
      navigate("/login?reset=1", { replace: true });
    } catch (err) {
      // An expired, spent or forged token lands here as a 400.
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-cream flex flex-col">
        <Navbar />
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="w-full max-w-sm animate-fade-up text-center">
            <h1 className="text-3xl font-serif text-fl-black mb-3">
              This link is incomplete.
            </h1>
            <p className="text-sm text-fl-muted font-sans mb-8">
              It's missing its token. Open the most recent link from your inbox,
              or ask for a new one.
            </p>
            <Link
              to="/forgot-password"
              className="btn-press inline-block px-6 py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold transition-colors"
            >
              Request a new link
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream flex flex-col">
      <Navbar />

      <div className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-sm animate-fade-up">
          <h1 className="text-3xl font-serif text-fl-black mb-2">
            Choose a new password.
          </h1>
          <p className="text-sm text-fl-muted font-sans mb-8">
            You'll sign in with it straight after.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-sans font-medium text-fl-black mb-1.5">
                New password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoFocus
                autoComplete="new-password"
                placeholder="••••••••••••"
                className={INPUT_CLASS}
              />
              <p
                className={`mt-1.5 text-xs font-sans ${
                  policyError ? "text-fl-red" : "text-fl-muted"
                }`}
              >
                {policyError || PASSWORD_HINT}
              </p>
            </div>

            <div>
              <label className="block text-sm font-sans font-medium text-fl-black mb-1.5">
                Confirm password
              </label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                autoComplete="new-password"
                placeholder="••••••••••••"
                className={INPUT_CLASS}
              />
              {mismatch && (
                <p className="mt-1.5 text-xs font-sans text-fl-red">
                  Those passwords don't match.
                </p>
              )}
            </div>

            {error && <p className="text-sm text-fl-red font-sans">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="btn-press w-full py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold disabled:opacity-60 transition-colors mt-2"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
                  Saving…
                </span>
              ) : "Set new password"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-fl-muted font-sans">
            Link expired?{" "}
            <Link
              to="/forgot-password"
              className="text-fl-black font-semibold underline underline-offset-2 hover:opacity-70 transition-opacity"
            >
              Request a new one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
