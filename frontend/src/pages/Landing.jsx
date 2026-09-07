import { Link } from "react-router-dom";
import Footer from "../components/Footer.jsx";
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

const SAMPLE_CARDS = [
  { topic: "Biology", q: "What do mitochondria do?" },
  { topic: "Biology", q: "Define osmosis" },
  { topic: "Physics", q: "State Newton's second law" },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-base-100">
      <Navbar />

      {/* Hero */}
      <section className="page pb-16 pt-20 sm:pt-28">
        <div className="max-w-2xl animate-fade-up">
          <span className="badge badge-ghost badge-sm mb-5 gap-1.5 font-medium">
            <span aria-hidden="true">🌼</span> Spaced repetition, without the setup
          </span>

          <h1 className="text-4xl leading-[1.1] sm:text-5xl md:text-6xl">
            Turn your notes into knowledge.
          </h1>

          <p className="mt-5 max-w-lg text-base leading-relaxed text-base-content/70">
            Upload a PDF and Marigold builds the flashcards and quizzes for you —
            then keeps track of what you're forgetting, so revision starts with
            whatever needs it most.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link to="/register" className="btn btn-primary">
              Start studying free
            </Link>
            <Link to="/login" className="btn btn-ghost">
              I have an account
            </Link>
          </div>
        </div>

        {/* A glance at the product rather than a stock illustration. */}
        <div
          className="mt-14 grid max-w-2xl gap-3 sm:grid-cols-3"
          style={{ animationDelay: "120ms" }}
        >
          {SAMPLE_CARDS.map((c) => (
            <div key={c.q} className="surface animate-fade-up p-4 opacity-0 shadow-subtle">
              <span className="badge badge-primary badge-sm font-medium">{c.topic}</span>
              <p className="mt-3 text-sm leading-snug text-base-content/80">{c.q}</p>
            </div>
          ))}
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
