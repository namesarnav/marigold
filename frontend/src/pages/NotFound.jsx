import { Link, useLocation } from "react-router-dom";
import Footer from "../components/Footer.jsx";
import Navbar from "../components/Navbar.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * The catch-all route.
 *
 * This replaces a redirect to "/". The redirect was worse in two ways that
 * only show up when something is actually broken: a mistyped or dead link
 * dropped the visitor on the marketing page with no indication anything had
 * gone wrong, and because it rewrote the URL the path that failed was gone
 * before it could be reported. Rendering here keeps the address bar intact.
 *
 * Note this is a client-side 404 only — the server answers every unmatched
 * non-API path with the SPA shell and a 200, which is what makes deep links
 * work at all (see mount_frontend in backend/main.py). Unmatched /api/* still
 * gets a real JSON 404 from the backend.
 */
export default function NotFound() {
  const { pathname } = useLocation();
  const { user } = useAuth();

  return (
    <div className="flex min-h-screen flex-col bg-base-100">
      <Navbar />

      <main className="page flex flex-1 items-center justify-center py-20">
        <div className="animate-fade-up max-w-md text-center">
          <span className="block text-5xl" aria-hidden="true">🌼</span>

          <p className="mt-6 text-sm font-semibold tracking-wider text-primary">
            404
          </p>

          <h1 className="mt-2 text-3xl sm:text-4xl">This page doesn't exist</h1>

          <p className="mt-4 text-base leading-relaxed text-base-content/70">
            The link may be out of date, or the address mistyped.
            {/* Only reassuring if they have something to reassure them about.
                A signed-out visitor has no decks, and telling them theirs are
                safe reads as a message meant for somebody else. */}
            {user
              ? " Nothing has been lost — your decks are where you left them."
              : " Everything else is still where you'd expect."}
          </p>

          {/* The path that failed, so a bad link can be reported as something
              more useful than "it didn't work". Wrapped because a long URL
              would otherwise push the card wider than the column. */}
          <p className="mt-5 break-all rounded-lg bg-base-200 px-3 py-2 font-mono text-xs text-base-content/50">
            {pathname}
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-3">
            {user ? (
              <Link to="/dashboard" className="btn btn-primary">
                Back to dashboard
              </Link>
            ) : (
              <Link to="/" className="btn btn-primary">
                Back home
              </Link>
            )}
            <Link to="/pricing" className="btn btn-ghost">
              See what's included
            </Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
