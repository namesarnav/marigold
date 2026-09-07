/**
 * The full-page wait shown while the session is being resolved.
 *
 * Shared by both route guards on purpose: they run the same check and must
 * look identical doing it, or a reload flashes one spinner and then a second,
 * differently-placed one as the guards hand over.
 */
export default function RouteSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-base-100">
      <span className="loading loading-spinner loading-lg text-primary" />
      <span className="sr-only">Loading</span>
    </div>
  );
}
