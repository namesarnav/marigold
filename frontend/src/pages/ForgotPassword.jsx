import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../api.js";
import Navbar from "../components/Navbar.jsx";

/**
 * Ask for a reset link.
 *
 * The success copy is careful: the endpoint answers the same way whether or
 * not an account exists, precisely so it cannot be used to discover who has
 * registered. Saying "we've emailed you" would leak exactly what the backend
 * refuses to — so this says what is actually true.
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (err) {
      // In practice the 429 from the hourly per-address limit.
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream flex flex-col">
      <Navbar />

      <div className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-sm animate-fade-up">
          {sent ? (
            <div className="text-center">
              <div className="text-4xl mb-5">✉️</div>
              <h1 className="text-3xl font-serif text-fl-black mb-3">
                Check your inbox.
              </h1>
              <p className="text-sm text-fl-muted font-sans mb-8 leading-relaxed">
                If an account exists for{" "}
                <span className="text-fl-black font-semibold">{email}</span>,
                we've sent a link to reset its password. It expires in 30
                minutes.
              </p>
              <Link
                to="/login"
                className="btn-press inline-block px-6 py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold transition-colors"
              >
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
              <h1 className="text-3xl font-serif text-fl-black mb-2">
                Reset your password.
              </h1>
              <p className="text-sm text-fl-muted font-sans mb-8">
                Enter your email and we'll send you a link.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-sans font-medium text-fl-black mb-1.5">
                    Email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoFocus
                    placeholder="you@example.com"
                    className="w-full bg-fl-card border-[1.5px] border-fl-border rounded-lg px-4 py-3 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black transition-colors"
                  />
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
                      Sending…
                    </span>
                  ) : "Send reset link"}
                </button>
              </form>

              <p className="mt-6 text-center text-sm text-fl-muted font-sans">
                Remembered it?{" "}
                <Link
                  to="/login"
                  className="text-fl-black font-semibold underline underline-offset-2 hover:opacity-70 transition-opacity"
                >
                  Sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
