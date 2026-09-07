import Logo from "./Logo.jsx";
import Navbar from "./Navbar.jsx";

/**
 * The frame every auth screen shares: sign in, register, verify, reset.
 *
 * Extracted because six screens were repeating the same centred column with
 * slightly different padding and heading sizes, which is exactly how a set of
 * pages stops looking like one product.
 */
export default function AuthLayout({ title, subtitle, children, footer, narrow = false }) {
  return (
    <div className="flex min-h-screen flex-col bg-base-200/40">
      <Navbar />

      <main className="flex flex-1 items-center justify-center px-5 py-12">
        <div className={`w-full animate-fade-up ${narrow ? "max-w-sm" : "max-w-md"}`}>
          <div className="surface p-7 shadow-subtle sm:p-8">
            <div className="mb-7 text-center">
              <Logo to={null} size="lg" className="mb-5" />
              <h1 className="text-2xl">{title}</h1>
              {subtitle && (
                <p className="mt-2 text-sm text-base-content/60">{subtitle}</p>
              )}
            </div>

            {children}
          </div>

          {footer && (
            <p className="mt-5 text-center text-sm text-base-content/60">{footer}</p>
          )}
        </div>
      </main>
    </div>
  );
}
