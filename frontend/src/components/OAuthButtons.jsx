import { useEffect, useState } from "react";
import { getOAuthProviders, oauthLoginUrl } from "../api.js";

// Marks and labels for everything the backend supports, keyed by the provider
// string the API returns — an unknown value is simply not rendered rather than
// producing a button with no icon.
const PROVIDERS = {
  google: {
    label: "Continue with Google",
    icon: (
      <svg viewBox="0 0 18 18" className="h-[18px] w-[18px]" aria-hidden="true">
        <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.91c1.7-1.57 2.69-3.88 2.69-6.62Z" />
        <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.84.86-3.05.86-2.35 0-4.34-1.58-5.05-3.71H.93v2.33A9 9 0 0 0 9 18Z" />
        <path fill="#FBBC05" d="M3.95 10.71a5.41 5.41 0 0 1 0-3.42V4.96H.93a9 9 0 0 0 0 8.08l3.02-2.33Z" />
        <path fill="#EA4335" d="M9 3.58c1.32 0 2.51.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .93 4.96l3.02 2.33C4.66 5.16 6.65 3.58 9 3.58Z" />
      </svg>
    ),
  },
  github: {
    label: "Continue with GitHub",
    icon: (
      <svg viewBox="0 0 16 16" className="h-[18px] w-[18px]" fill="currentColor" aria-hidden="true">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.42 7.42 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
      </svg>
    ),
  },
};

/**
 * Provider sign-in buttons, or nothing at all.
 *
 * The list comes from `/api/auth/oauth/providers`, which reports only the
 * providers the server actually holds credentials for. Rendering a fixed pair
 * would offer a sign-in that answers 503 the moment it is clicked — with no
 * OAuth configured, which is the default, this renders nothing and the page is
 * just the password form.
 *
 * Signing in is a full page navigation, not a fetch: the flow leaves the origin
 * for the provider's consent screen and comes back to /oauth/callback.
 */
export default function OAuthButtons({ disabled = false }) {
  const [providers, setProviders] = useState([]);

  useEffect(() => {
    let cancelled = false;
    getOAuthProviders()
      // Not worth a visible error: the password form still works, so the
      // buttons simply do not appear.
      .catch(() => [])
      .then((list) => {
        if (!cancelled) setProviders(list);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const available = providers.filter((name) => PROVIDERS[name]);
  if (available.length === 0) return null;

  return (
    <div className="mb-6">
      <div className="space-y-2">
        {available.map((name) => {
          const { label, icon } = PROVIDERS[name];
          return (
            <a
              key={name}
              href={disabled ? undefined : oauthLoginUrl(name)}
              aria-disabled={disabled}
              className={`btn btn-outline w-full justify-center gap-2.5 font-medium ${
                disabled ? "pointer-events-none opacity-60" : ""
              }`}
            >
              {icon}
              {label}
            </a>
          );
        })}
      </div>

      <div className="divider my-6 text-xs uppercase tracking-wider text-base-content/40">
        or
      </div>
    </div>
  );
}
