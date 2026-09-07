/**
 * Where to send someone once they have signed in.
 *
 * ProtectedRoute stashes the location it bounced from in router state; this
 * reads it back. Shared by the two guards and the two auth forms so they can
 * never disagree about what counts as a valid destination.
 */
export function returnTo(location, fallback = "/dashboard") {
  const from = location.state?.from?.pathname;
  return isInternal(from) ? from : fallback;
}

/**
 * Only ever navigate to a path within this app.
 *
 * `from` arrives through router state, which lives on a history entry the user
 * can edit. A value like "//evil.example" is a protocol-relative URL that the
 * router would treat as a path and the browser as another origin — an open
 * redirect that costs one line to close.
 */
export function isInternal(path) {
  return typeof path === "string" && path.startsWith("/") && !path.startsWith("//");
}
