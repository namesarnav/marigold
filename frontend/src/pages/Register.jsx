import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register, getMe } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import Navbar from "../components/Navbar.jsx";
import OAuthButtons from "../components/OAuthButtons.jsx";
import { checkPassword, MIN_PASSWORD_LENGTH, PASSWORD_HINT } from "../passwordPolicy.js";

export default function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const policyError = password ? checkPassword(password) : "";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    // Saves a round trip that could only come back as a 422; the server
    // enforces the same policy regardless.
    const problem = checkPassword(password);
    if (problem) return setError(problem);

    setLoading(true);
    try {
      await register(email, password, name);
      const user = await getMe();
      setUser(user);
      // A new password account is unverified, so this lands on the
      // verification gate rather than the dashboard itself — that screen is
      // where "check your inbox" and the resend button live. Navigating to
      // /dashboard regardless keeps one destination for a successful signup.
      navigate("/dashboard");
    } catch (err) {
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
          <h1 className="text-3xl font-serif text-fl-black mb-2">Create your account.</h1>
          <p className="text-sm text-fl-muted font-sans mb-8">Start studying smarter in seconds.</p>

          <OAuthButtons disabled={loading} />

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-sans font-medium text-fl-black mb-1.5">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="Your name"
                className="w-full bg-fl-card border-[1.5px] border-fl-border rounded-lg px-4 py-3 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-sans font-medium text-fl-black mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full bg-fl-card border-[1.5px] border-fl-border rounded-lg px-4 py-3 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-sans font-medium text-fl-black mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={MIN_PASSWORD_LENGTH}
                autoComplete="new-password"
                placeholder="••••••••••••"
                className="w-full bg-fl-card border-[1.5px] border-fl-border rounded-lg px-4 py-3 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black transition-colors"
              />
              {/* The form used to advertise "Min. 8 characters" while the
                  server required 12 and three character classes, so a password
                  the form accepted came back as a 422 the user had been given
                  no way to anticipate. */}
              <p
                className={`mt-1.5 text-xs font-sans ${
                  policyError ? "text-fl-red" : "text-fl-muted"
                }`}
              >
                {policyError || PASSWORD_HINT}
              </p>
            </div>

            {error && (
              <p className="text-sm text-fl-red font-sans">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn-press w-full py-3 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-[15px] font-sans font-semibold disabled:opacity-60 transition-colors mt-2"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
                  Creating account…
                </span>
              ) : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-fl-muted font-sans">
            Already have an account?{" "}
            <Link to="/login" className="text-fl-black font-semibold underline underline-offset-2 hover:opacity-70 transition-opacity">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
