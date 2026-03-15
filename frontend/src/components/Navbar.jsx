import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { logout } from "../api.js";

export default function Navbar() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    setUser(null);
    navigate("/");
    setMenuOpen(false);
  };

  const isActive = (path) => location.pathname === path;

  return (
    <nav
      className="sticky top-0 z-30 h-16 flex items-center px-6 md:px-12 border-b border-fl-border"
      style={{ backdropFilter: "blur(12px)", backgroundColor: "rgba(248,243,236,0.85)" }}
    >
      {/* Logo */}
      <Link to="/" className="flex items-center gap-2 mr-8 shrink-0">
        <div className="h-7 w-7 rounded-lg bg-fl-yellow flex items-center justify-center text-fl-black text-xs font-bold font-sans">M</div>
        <span className="font-serif text-lg text-fl-black">Marigold</span>
      </Link>

      {/* Center nav */}
      <div className="hidden md:flex items-center gap-1 flex-1">
        <Link
          to="/pricing"
          className={`px-3 py-1.5 text-sm font-sans font-medium transition-colors rounded-lg ${
            isActive("/pricing")
              ? "text-fl-black border-b-2 border-fl-yellow rounded-none"
              : "text-fl-muted hover:text-fl-black"
          }`}
        >
          Pricing
        </Link>
      </div>

      {/* Right: auth */}
      <div className="hidden md:flex items-center gap-3 ml-auto">
        {user ? (
          <>
            <Link
              to="/dashboard"
              className={`text-sm font-sans font-medium transition-colors ${
                isActive("/dashboard") ? "text-fl-black" : "text-fl-muted hover:text-fl-black"
              }`}
            >
              Dashboard
            </Link>
            <span className="text-sm font-sans text-fl-muted">{user.name}</span>
            <button
              onClick={handleLogout}
              className="px-4 py-1.5 text-sm font-sans font-semibold text-fl-black border border-fl-border rounded-lg hover:border-fl-black transition-all"
            >
              Log out
            </button>
          </>
        ) : (
          <>
            <Link
              to="/login"
              className="px-4 py-1.5 text-sm font-sans font-semibold text-fl-black border border-fl-border rounded-lg hover:border-fl-black transition-all"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className="btn-press px-4 py-1.5 text-sm font-sans font-semibold text-fl-black bg-fl-yellow rounded-lg hover:bg-fl-yellow-h transition-colors"
            >
              Get started
            </Link>
          </>
        )}
      </div>

      {/* Mobile hamburger */}
      <button
        className="md:hidden ml-auto flex flex-col gap-1 p-2"
        onClick={() => setMenuOpen((o) => !o)}
        aria-label="Toggle menu"
      >
        <span className={`block h-0.5 w-5 bg-fl-black transition-all ${menuOpen ? "rotate-45 translate-y-1.5" : ""}`} />
        <span className={`block h-0.5 w-5 bg-fl-black transition-all ${menuOpen ? "opacity-0" : ""}`} />
        <span className={`block h-0.5 w-5 bg-fl-black transition-all ${menuOpen ? "-rotate-45 -translate-y-1.5" : ""}`} />
      </button>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="md:hidden absolute top-16 inset-x-0 bg-cream border-b border-fl-border shadow-lg py-3 px-6 flex flex-col gap-2 z-40">
          <Link to="/pricing" onClick={() => setMenuOpen(false)} className="py-2 text-sm font-sans text-fl-black">Pricing</Link>
          {user ? (
            <>
              <Link to="/dashboard" onClick={() => setMenuOpen(false)} className="py-2 text-sm font-sans text-fl-black">Dashboard</Link>
              <span className="py-2 text-sm font-sans text-fl-muted">{user.name}</span>
              <button onClick={handleLogout} className="py-2 text-sm font-sans text-fl-red text-left">Log out</button>
            </>
          ) : (
            <>
              <Link to="/login" onClick={() => setMenuOpen(false)} className="py-2 text-sm font-sans text-fl-black">Sign in</Link>
              <Link to="/register" onClick={() => setMenuOpen(false)} className="py-2 text-sm font-sans font-semibold text-fl-black">Get started</Link>
            </>
          )}
        </div>
      )}
    </nav>
  );
}
