import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api.js";
import { checkPassword, PASSWORD_HINT } from "../passwordPolicy.js";
import AuthLayout from "../components/AuthLayout.jsx";

/**
 * Choose a new password from an emailed reset link.
 *
 * Unlike /verify-email nothing happens on mount: the token is only spent when
 * the form is submitted. Landing here must not consume the link, or previewing
 * the email — or any scanner that follows links in it — would burn the reset
 * before the user typed anything.
 *
 * There is no session at the end. The backend revokes every refresh token as
 * part of the reset, so this finishes at the login form.
 */
export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const policyError = password ? checkPassword(password) : "";
  const mismatch = confirm.length > 0 && confirm !== password;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

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
      <AuthLayout
        title="This link is incomplete"
        subtitle="It's missing its token. Open the most recent link from your inbox, or ask for a new one."
      >
        <Link to="/forgot-password" className="btn btn-primary w-full">
          Request a new link
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="You'll sign in with it straight after."
      footer={
        <>
          Link expired?{" "}
          <Link to="/forgot-password" className="link link-hover font-medium text-base-content">
            Request a new one
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="form-control w-full">
          <div className="label pb-1.5 pt-0">
            <span className="label-text font-medium">New password</span>
          </div>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoFocus
            autoComplete="new-password"
            placeholder="••••••••••••"
            className={`input input-bordered w-full ${policyError ? "input-error" : ""}`}
          />
          <div className="label pb-0">
            <span className={`label-text-alt ${policyError ? "text-error" : "text-base-content/50"}`}>
              {policyError || PASSWORD_HINT}
            </span>
          </div>
        </label>

        <label className="form-control w-full">
          <div className="label pb-1.5 pt-0">
            <span className="label-text font-medium">Confirm password</span>
          </div>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            autoComplete="new-password"
            placeholder="••••••••••••"
            className={`input input-bordered w-full ${mismatch ? "input-error" : ""}`}
          />
          {mismatch && (
            <div className="label pb-0">
              <span className="label-text-alt text-error">Those passwords don't match.</span>
            </div>
          )}
        </label>

        {error && (
          <div role="alert" className="alert alert-error py-2.5">
            <span className="text-sm">{error}</span>
          </div>
        )}

        <button type="submit" disabled={loading} className="btn btn-primary w-full">
          {loading && <span className="loading loading-spinner loading-sm" />}
          {loading ? "Saving…" : "Set new password"}
        </button>
      </form>
    </AuthLayout>
  );
}
