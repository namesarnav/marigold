import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getMe, login } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout from "../components/AuthLayout.jsx";
import OAuthButtons from "../components/OAuthButtons.jsx";

export default function Login() {
  const [params] = useSearchParams();
  const [email, setEmail] = useState(() => params.get("email") ?? "");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  // A failed provider sign-in redirects here rather than rendering its own
  // page, carrying what went wrong in the query string. Without reading it the
  // user bounces back to an ordinary login form with no idea why.
  const [error, setError] = useState(() => params.get("message") ?? "");
  // ResetPassword sends the user here with ?reset=1 rather than logging them
  // in: the reset revokes every refresh token, so there is no session to hand
  // over and they sign in with the password they just chose.
  const justReset = params.get("reset") === "1";
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      setUser(await getMe());
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to pick up where you left off."
      footer={
        <>
          No account?{" "}
          <Link to="/register" className="link link-hover font-medium text-base-content">
            Create one
          </Link>
        </>
      }
    >
      {justReset && (
        <div role="status" className="alert alert-success mb-5 py-2.5">
          <span className="text-sm">Password updated. Sign in with your new one.</span>
        </div>
      )}

      <OAuthButtons disabled={loading} />

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="form-control w-full">
          <div className="label pb-1.5 pt-0">
            <span className="label-text font-medium">Email</span>
          </div>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            placeholder="you@example.com"
            className="input input-bordered w-full"
          />
        </label>

        <label className="form-control w-full">
          <div className="label pb-1.5 pt-0">
            <span className="label-text font-medium">Password</span>
            <Link to="/forgot-password" className="label-text-alt link link-hover">
              Forgot?
            </Link>
          </div>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            placeholder="••••••••••••"
            className="input input-bordered w-full"
          />
        </label>

        {error && (
          <div role="alert" className="alert alert-error py-2.5">
            <span className="text-sm">{error}</span>
          </div>
        )}

        <button type="submit" disabled={loading} className="btn btn-primary w-full">
          {loading && <span className="loading loading-spinner loading-sm" />}
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}
