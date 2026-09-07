import { Link } from "react-router-dom";
import Logo from "./Logo.jsx";

export default function Footer() {
  return (
    <footer className="border-t border-base-300 bg-base-200/50">
      <div className="page py-12">
        <div className="grid gap-10 sm:grid-cols-3">
          <div>
            <Logo size="sm" />
            <p className="mt-3 text-sm text-base-content/60">
              Study smarter, not longer.
            </p>
          </div>

          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-base-content/40">
              Product
            </p>
            <ul className="space-y-2 text-sm">
              <li><Link to="/" className="link link-hover text-base-content/70">Home</Link></li>
              <li><Link to="/pricing" className="link link-hover text-base-content/70">Pricing</Link></li>
              <li><Link to="/dashboard" className="link link-hover text-base-content/70">Dashboard</Link></li>
            </ul>
          </div>

          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-base-content/40">
              Company
            </p>
            {/* Not links: these pages do not exist, and a link that goes
                nowhere is worse than plain text. */}
            <ul className="space-y-2 text-sm text-base-content/40">
              <li>About</li>
              <li>Contact</li>
              <li>Privacy</li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-base-300 pt-6">
          <p className="text-xs text-base-content/40">
            © {new Date().getFullYear()} Marigold
          </p>
        </div>
      </div>
    </footer>
  );
}
