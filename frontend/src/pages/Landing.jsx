import { Link } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import Footer from "../components/Footer.jsx";

export default function Landing() {
  return (
    <div className="min-h-screen bg-cream font-sans">
      <Navbar />

      {/* Hero */}
      <section className="px-6 md:px-12 pt-24 pb-20 max-w-6xl mx-auto">
        <div className="max-w-2xl animate-fade-up">
          <h1 className="text-5xl md:text-6xl font-serif text-fl-black leading-tight mb-6">
            Turn your notes into<br />
            <span className="italic">knowledge.</span>
          </h1>
          <p className="text-base font-sans text-fl-muted mb-8 leading-relaxed max-w-lg">
            Upload any PDF — lecture slides, textbooks, notes —
            and Marigold instantly creates flashcards and
            quizzes so you can study smarter, not longer.
          </p>
          <Link
            to="/register"
            className="btn-press inline-flex items-center gap-2 px-6 py-3 text-[15px] font-sans font-semibold text-fl-black bg-fl-yellow rounded-lg hover:bg-fl-yellow-h transition-colors duration-200"
          >
            Start studying free
            <span>→</span>
          </Link>
        </div>

        {/* Mockup */}
        <div className="mt-16 animate-fade-up" style={{ animationDelay: "150ms" }}>
          <div className="grid grid-cols-3 gap-3 max-w-lg">
            {[
              { q: "What is the mitochondria?", a: "The powerhouse of the cell", topic: "Biology" },
              { q: "Define osmosis", a: "Movement of water across a semipermeable membrane", topic: "Biology" },
              { q: "Newton's 2nd Law", a: "F = ma", topic: "Physics" },
            ].map((card, i) => (
              <div
                key={i}
                className="bg-fl-card border border-fl-border rounded-xl p-4"
                style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
              >
                {card.topic && (
                  <span className="inline-block px-2 py-0.5 rounded-full bg-fl-yellow text-fl-black text-[10px] font-sans font-semibold uppercase tracking-wider mb-2">
                    {card.topic}
                  </span>
                )}
                <p className="text-xs text-fl-muted mb-1 font-sans">Question</p>
                <p className="text-xs text-fl-black font-sans leading-snug">{card.q}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="px-6 md:px-12 py-16 border-t border-fl-border">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-serif text-fl-black mb-12">How it works</h2>
          <div className="grid md:grid-cols-3 gap-8 stagger">
            {[
              {
                n: "01",
                title: "Upload your notes",
                body: "Drop in any PDF. Lecture slides, textbook chapters, handwritten scans. We handle the rest.",
              },
              {
                n: "02",
                title: "Get instant flashcards",
                body: "Our AI reads your material and pulls out the key concepts as clean, focused flashcards.",
              },
              {
                n: "03",
                title: "Test yourself",
                body: "Take a timed quiz, track your score, and revisit what you got wrong until you've got it down.",
              },
            ].map((step) => (
              <div key={step.n} className="animate-fade-up opacity-0">
                <p className="text-fl-muted text-sm font-sans font-semibold mb-3">{step.n}</p>
                <h3 className="text-xl font-serif text-fl-black mb-2">{step.title}</h3>
                <p className="text-sm text-fl-muted font-sans leading-relaxed">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-6 md:px-12 py-16 border-t border-fl-border">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-serif text-fl-black mb-12">Everything you need to study well</h2>
          <div className="grid md:grid-cols-3 gap-4 stagger">
            {[
              {
                title: "Flashcards that flip",
                body: "Review key concepts one by one. Tap to reveal the answer. Move at your own pace.",
              },
              {
                title: "Timed quizzes",
                body: "30 seconds per question. Multiple choice. Just enough pressure to make it stick.",
              },
              {
                title: "See your progress",
                body: "Every quiz is saved. Review wrong answers, retry, and watch your scores improve.",
              },
            ].map((f) => (
              <div
                key={f.title}
                className="card-hover animate-fade-up opacity-0 bg-fl-card border border-fl-border rounded-xl p-6"
                style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
              >
                <h3 className="text-lg font-serif text-fl-black mb-2">{f.title}</h3>
                <p className="text-sm text-fl-muted font-sans leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Banner */}
      <section className="mx-6 md:mx-12 my-16 rounded-2xl bg-fl-yellow px-10 py-12 flex flex-col md:flex-row items-center justify-between gap-6">
        <h2 className="text-3xl font-serif text-fl-black">Ready to study smarter?</h2>
        <Link
          to="/register"
          className="btn-press flex-shrink-0 px-6 py-3 text-[15px] font-sans font-semibold rounded-lg hover:opacity-90 transition-opacity"
          style={{ backgroundColor: "#282828", color: "#f8f3ec" }}
        >
          Get started free →
        </Link>
      </section>

      <Footer />
    </div>
  );
}
