import { Link, useParams } from "react-router-dom";
import Footer from "../components/Footer.jsx";
import Navbar from "../components/Navbar.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * Where "Start Pro" and "Start Team" lead, because payments don't exist yet.
 *
 * Styled after the real 404 so the joke reads instantly, but it is its own
 * route rather than the catch-all: a mistyped URL should still get the honest
 * "this page doesn't exist", not a pricing gag.
 */
const PLAN_NAMES = { pro: "Pro", team: "Team" };

export default function PlanNotReady() {
  const { plan } = useParams();
  const { user } = useAuth();
  const planName = PLAN_NAMES[plan] ?? "that plan";

  return (
    <div className="flex min-h-screen flex-col bg-base-100">
      <Navbar />

      <main className="page flex flex-1 items-center justify-center py-20">
        <div className="animate-fade-up max-w-md text-center">
          <span className="block text-5xl" aria-hidden="true">💸</span>

          <p className="mt-6 text-sm font-semibold tracking-wider text-primary">
            402 · Payment Not Found
          </p>

          <h1 className="mt-2 text-3xl sm:text-4xl">
            We haven't built the part where you pay us
          </h1>

          <p className="mt-4 text-base leading-relaxed text-base-content/70">
            You tried to buy {planName}, which is very kind. Sadly our checkout is
            still a sketch on a napkin. Until it's real, every feature is free.
            Go enjoy it before we figure out how money works.
          </p>

          <p className="mt-5 rounded-lg bg-base-200 px-3 py-2 text-xs text-base-content/60">
            Amount charged: <span className="font-mono">$0.00</span>. Your wallet
            says thanks.
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-3">
            {user ? (
              <Link to="/dashboard" className="btn btn-primary">
                Back to free studying
              </Link>
            ) : (
              <Link to="/register" className="btn btn-primary">
                Get it all free
              </Link>
            )}
            <Link to="/pricing" className="btn btn-ghost">
              Back to pricing
            </Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
