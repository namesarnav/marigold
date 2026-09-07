import { Link, useLocation, useNavigate } from "react-router-dom";
import { logout } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";
import Logo from "./Logo.jsx";

/**
 * The marketing and auth-screen header.
 *
 * The dashboard does not use this — it has its own rail — so this only ever
 * appears on pages a signed-out visitor can reach, plus the verification and
 * reset screens.
 */
export default function Navbar() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    setUser(null);
    navigate("/");
  };

  const isActive = (path) => location.pathname === path;

  return (
    // Sticky and translucent so content scrolls under it without the header
    // becoming a hard band across the page.
    <header className="sticky top-0 z-30 border-b border-base-300 bg-base-100/85 backdrop-blur">
      <div className="page flex h-16 items-center gap-4">
        <Logo />

        <nav className="ml-auto flex items-center gap-1 sm:gap-2">
          <Link
            to="/pricing"
            className={`btn btn-ghost btn-sm font-medium ${
              isActive("/pricing") ? "text-base-content" : "text-base-content/60"
            }`}
          >
            Pricing
          </Link>

          {user ? (
            <>
              <Link
                to="/dashboard"
                className={`btn btn-ghost btn-sm font-medium ${
                  isActive("/dashboard") ? "text-base-content" : "text-base-content/60"
                }`}
              >
                Dashboard
              </Link>
              <button onClick={handleLogout} className="btn btn-sm btn-outline">
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn btn-ghost btn-sm font-medium">
                Sign in
              </Link>
              <Link to="/register" className="btn btn-primary btn-sm">
                Get started
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
