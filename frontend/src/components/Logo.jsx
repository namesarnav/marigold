import { Link } from "react-router-dom";

/**
 * The wordmark. One component so the mark can never drift between the navbar,
 * the footer, the dashboard rail and the auth screens.
 *
 * The flower is a plain emoji rather than an SVG or a lettermark: it is the
 * product's name made literal, it renders identically wherever the app runs,
 * and it costs nothing to load. `aria-hidden` because "Marigold" is already
 * beside it — a screen reader announcing "blossom Marigold" is noise.
 */
export default function Logo({ to = "/", size = "md", className = "" }) {
  const sizes = {
    sm: { mark: "text-lg", text: "text-base" },
    md: { mark: "text-xl", text: "text-lg" },
    lg: { mark: "text-2xl", text: "text-xl" },
  };
  const s = sizes[size] ?? sizes.md;

  const content = (
    <>
      <span className={`${s.mark} leading-none`} aria-hidden="true">🌼</span>
      <span className={`${s.text} font-semibold tracking-tight text-base-content`}>
        Marigold
      </span>
    </>
  );

  if (!to) {
    return <span className={`inline-flex items-center gap-2 ${className}`}>{content}</span>;
  }

  return (
    <Link to={to} className={`inline-flex items-center gap-2 ${className}`}>
      {content}
    </Link>
  );
}
