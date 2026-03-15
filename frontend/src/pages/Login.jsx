import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login, getMe } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import Navbar from "../components/Navbar.jsx";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      const user = await getMe();
      setUser(user);
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
          <h1 className="text-3xl font-serif text-fl-black mb-2">Welcome back.</h1>
          <p className="text-sm text-fl-muted font-sans mb-8">Sign in to your account to continue.</p>

          <form onSubmit={handleSubmit} className="space-y-4">
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
                placeholder="••••••••"
                className="w-full bg-fl-card border-[1.5px] border-fl-border rounded-lg px-4 py-3 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black transition-colors"
              />
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
                  Signing in…
                </span>
              ) : "Sign in"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-fl-muted font-sans">
            No account?{" "}
            <Link to="/register" className="text-fl-black font-semibold underline underline-offset-2 hover:opacity-70 transition-opacity">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
