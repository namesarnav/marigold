import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getMe, register } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { checkPassword, MIN_PASSWORD_LENGTH, PASSWORD_HINT } from "../passwordPolicy.js";
import AuthLayout from "../components/AuthLayout.jsx";
import OAuthButtons from "../components/OAuthButtons.jsx";

export default function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { setUser } = useAuth();
  const navigate = useNavigate();

  // Shown under the field as the user types, but only once they have typed
  // something — an empty form should not open with a complaint.
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
      setUser(await getMe());
      // A new password account is unverified, so this lands on the
      // verification gate rather than the dashboard itself — that screen is
      // where "check your inbox" and the resend button live.
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Turn your notes into flashcards in a couple of minutes."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="link link-hover font-medium text-base-content">
            Sign in
          </Link>
        </>
      }
    >
      <OAuthButtons disabled={loading} />

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="form-control w-full">
          <div className="label pb-1.5 pt-0">
            <span className="label-text font-medium">Name</span>
          </div>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoComplete="name"
            placeholder="Your name"
            className="input input-bordered w-full"
          />
        </label>

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
          </div>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
            placeholder="••••••••••••"
            className={`input input-bordered w-full ${policyError ? "input-error" : ""}`}
          />
          {/* The form used to advertise "Min. 8 characters" while the server
              required 12 and three character classes, so a password the form
              accepted came back as a 422 the user could not have anticipated. */}
          <div className="label pb-0">
            <span className={`label-text-alt ${policyError ? "text-error" : "text-base-content/50"}`}>
              {policyError || PASSWORD_HINT}
            </span>
          </div>
        </label>

        {error && (
          <div role="alert" className="alert alert-error py-2.5">
            <span className="text-sm">{error}</span>
          </div>
        )}

        <button type="submit" disabled={loading} className="btn btn-primary w-full">
          {loading && <span className="loading loading-spinner loading-sm" />}
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>
    </AuthLayout>
  );
}
