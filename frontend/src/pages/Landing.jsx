import { Link } from "react-router-dom";
import Footer from "../components/Footer.jsx";
import HeroDemo from "../components/HeroDemo.jsx";
import Navbar from "../components/Navbar.jsx";

const STEPS = [
  {
    n: "01",
    title: "Upload your notes",
    body: "Drop in any PDF — lecture slides, a textbook chapter, your own notes.",
  },
  {
    n: "02",
    title: "Get flashcards back",
    body: "Marigold reads the material and pulls out the key concepts as focused cards.",
  },
  {
    n: "03",
    title: "Study what's slipping",
    body: "Review, take timed quizzes, and let Marigold tell you what you're forgetting.",
  },
];

const FEATURES = [
  {
    icon: "🃏",
    title: "Flashcards that flip",
    body: "One concept at a time. Tap to reveal, mark what you knew, move at your own pace.",
  },
  {
    icon: "⏱",
    title: "Timed quizzes",
    body: "Multiple choice against the clock — just enough pressure to make it stick.",
  },
  {
    icon: "🎯",
    title: "Knows what you forget",
    body: "Every answer is recorded, so your review queue is ranked by what's actually fading.",
  },
];


export default function Landing() {
  return (
    <div className="min-h-screen bg-base-100">
      <Navbar />

      {/* Hero */}
      {/* Full-bleed wrapper so the background wash can span the viewport; the
          content stays in the usual centred `.page` column inside it. */}
      <section className="hero-glow">
        <div className="page pb-16 pt-20 sm:pt-28">
          {/* Two columns from lg up: the pitch, and the thing itself running
              beside it. Below that the card drops under the copy rather than
              shrinking, because a flashcard narrower than its own question is
              not a demonstration of anything.

              The card track is a fixed 24rem, not `auto`. The card's faces are
              absolutely positioned, so they contribute nothing to min-content
              and an auto track collapses to the width of the progress dots —
              which is exactly what it did. */}
          <div className="relative grid items-center gap-14 lg:grid-cols-[minmax(0,1fr)_24rem]">
            {/* Each element rises in just behind the one above it. The delays
                are inline because they are positional, not reusable. */}
            <div className="max-w-xl">
              <span
                className="badge badge-ghost badge-sm mb-5 animate-fade-up gap-1.5 font-medium opacity-0"
                style={{ animationDelay: "0ms" }}
              >
                <span aria-hidden="true">🌼</span> Spaced repetition, without the setup
              </span>

              <h1
                className="animate-fade-up text-4xl leading-[1.1] opacity-0 sm:text-5xl md:text-6xl"
                style={{ animationDelay: "70ms" }}
              >
                Turn your notes into knowledge.
              </h1>

              <p
                className="mt-5 max-w-lg animate-fade-up text-base leading-relaxed text-base-content/70 opacity-0"
                style={{ animationDelay: "140ms" }}
              >
                Upload a PDF and Marigold builds the flashcards and quizzes for
                you — then keeps track of what you're forgetting, so revision
                starts with whatever needs it most.
              </p>

              <div
                className="mt-8 flex animate-fade-up flex-wrap items-center gap-3 opacity-0"
                style={{ animationDelay: "210ms" }}
              >
                <Link to="/register" className="btn btn-primary">
                  Start studying free
                </Link>
                <Link to="/login" className="btn btn-ghost">
                  I have an account
                </Link>
              </div>
            </div>

            {/* No justify-self here: it shrink-wraps the grid item to
                min-content, which for a card of absolutely-positioned faces is
                nothing at all. Stretching to fill the track and centring inside
                it is what actually puts the card where the track is. */}
            <div
              className="animate-fade-up opacity-0"
              style={{ animationDelay: "280ms" }}
            >
              <HeroDemo />
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-base-300 bg-base-200/40">
        <div className="page py-16">
          <h2 className="text-2xl sm:text-3xl">How it works</h2>

          <div className="stagger mt-10 grid gap-8 sm:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.n} className="animate-fade-up opacity-0">
                <p className="mb-2 text-sm font-semibold text-primary">{s.n}</p>
                <h3 className="text-lg">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-base-content/60">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-base-300">
        <div className="page py-16">
          <h2 className="text-2xl sm:text-3xl">Everything you need to study well</h2>

          <div className="stagger mt-10 grid gap-4 sm:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="surface animate-fade-up p-6 opacity-0">
                <span className="text-2xl" aria-hidden="true">{f.icon}</span>
                <h3 className="mt-3 text-lg">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-base-content/60">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="page py-16">
        <div className="rounded-2xl bg-primary px-8 py-12 text-center sm:px-12">
          <h2 className="text-2xl text-primary-content sm:text-3xl">
            Ready to study smarter?
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-primary-content/80">
            Free to start. Upload your first PDF and see what comes back.
          </p>
          <Link to="/register" className="btn mt-7 border-0 bg-base-100 text-base-content hover:bg-base-200">
            Get started free
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  );
}
