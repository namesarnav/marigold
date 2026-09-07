import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../api.js";
import AuthLayout from "../components/AuthLayout.jsx";

/**
 * Ask for a reset link.
 *
 * The success copy is careful: the endpoint answers the same way whether or not
 * an account exists, precisely so it cannot be used to discover who has
 * registered. Saying "we've emailed you" would leak exactly what the backend
 * refuses to, so this says what is actually true.
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

  if (sent) {
    return (
      <AuthLayout
        title="Check your inbox"
        subtitle={
          <>
            If an account exists for{" "}
            <span className="font-medium text-base-content">{email}</span>, we've
            sent a link to reset its password. It expires in 30 minutes.
          </>
        }
      >
        <Link to="/login" className="btn btn-primary w-full">
          Back to sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your email and we'll send you a link."
      footer={
        <>
          Remembered it?{" "}
          <Link to="/login" className="link link-hover font-medium text-base-content">
            Sign in
          </Link>
        </>
      }
    >
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
            autoFocus
            autoComplete="email"
            placeholder="you@example.com"
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
          {loading ? "Sending…" : "Send reset link"}
        </button>
      </form>
    </AuthLayout>
  );
}
