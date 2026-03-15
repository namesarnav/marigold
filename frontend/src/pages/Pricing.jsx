import { useState } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import Footer from "../components/Footer.jsx";

const PLANS = [
  {
    name: "Free",
    monthlyPrice: 0,
    yearlyPrice: 0,
    description: "Perfect for getting started",
    features: [
      "5 PDFs per month",
      "Up to 20 flashcards per deck",
      "Unlimited quizzes",
      "Basic quiz history",
    ],
    cta: "Get started free",
    ctaLink: "/register",
    elevated: false,
  },
  {
    name: "Pro",
    monthlyPrice: 9,
    yearlyPrice: 7,
    description: "For serious students",
    features: [
      "Unlimited PDFs",
      "Unlimited flashcards",
      "Unlimited quizzes",
      "Full quiz history & analytics",
      "AI regeneration",
      "Priority processing",
    ],
    cta: "Start Pro",
    ctaLink: "/register",
    elevated: true,
  },
  {
    name: "Team",
    monthlyPrice: 19,
    yearlyPrice: 15,
    description: "For study groups & classes",
    features: [
      "Everything in Pro",
      "Up to 10 members",
      "Shared decks",
      "Team analytics",
      "Admin dashboard",
    ],
    cta: "Start Team",
    ctaLink: "/register",
    elevated: false,
  },
];

const FAQ = [
  {
    q: "Can I cancel anytime?",
    a: "Yes. You can cancel your subscription at any time. You'll continue to have access until the end of your billing period.",
  },
  {
    q: "What happens to my flashcards if I downgrade?",
    a: "Your existing decks are preserved. You just won't be able to create new ones beyond the free plan limits.",
  },
  {
    q: "Is there a student discount?",
    a: "We're working on it. Sign up for the free plan and we'll notify you when student pricing is available.",
  },
  {
    q: "What file types do you support?",
    a: "We currently support PDF files. More formats (DOCX, PPTX) are coming soon.",
  },
];

function FaqItem({ q, a }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-fl-border last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between py-5 text-left gap-4"
      >
        <span className="text-base font-sans font-medium text-fl-black">{q}</span>
        <span className={`text-fl-muted text-xl transition-transform duration-200 shrink-0 ${open ? "rotate-45" : ""}`}>+</span>
      </button>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: open ? "200px" : "0px" }}
      >
        <p className="text-sm font-sans text-fl-muted leading-relaxed pb-5">{a}</p>
      </div>
    </div>
  );
}

export default function Pricing() {
  const [yearly, setYearly] = useState(false);

  return (
    <div className="min-h-screen bg-cream font-sans">
      <Navbar />

      {/* Header */}
      <section className="px-6 md:px-12 pt-20 pb-12 text-center max-w-3xl mx-auto">
        <h1 className="text-4xl md:text-5xl font-serif text-fl-black mb-4">Simple, honest pricing</h1>
        <p className="text-base text-fl-muted font-sans mb-8">
          Start free. Upgrade when you're ready.
        </p>

        {/* Toggle */}
        <div className="inline-flex items-center gap-3 bg-fl-card border border-fl-border rounded-full px-2 py-1.5">
          <button
            onClick={() => setYearly(false)}
            className={`px-4 py-1.5 rounded-full text-sm font-sans font-semibold transition-all ${
              !yearly ? "bg-fl-yellow text-fl-black" : "text-fl-muted hover:text-fl-black"
            }`}
          >
            Monthly
          </button>
          <button
            onClick={() => setYearly(true)}
            className={`px-4 py-1.5 rounded-full text-sm font-sans font-semibold transition-all ${
              yearly ? "bg-fl-yellow text-fl-black" : "text-fl-muted hover:text-fl-black"
            }`}
          >
            Yearly
            <span className="ml-1.5 text-[10px] font-sans font-semibold text-fl-black bg-fl-yellow/60 rounded-full px-1.5 py-0.5">
              Save 20%
            </span>
          </button>
        </div>
      </section>

      {/* Plan cards */}
      <section className="px-6 md:px-12 pb-20">
        <div className="max-w-5xl mx-auto grid md:grid-cols-3 gap-5 items-start">
          {PLANS.map((plan) => {
            const price = yearly ? plan.yearlyPrice : plan.monthlyPrice;
            return (
              <div
                key={plan.name}
                className={`rounded-2xl border p-7 flex flex-col ${
                  plan.elevated
                    ? "bg-fl-black border-fl-black shadow-xl scale-[1.02] md:scale-105"
                    : "bg-fl-card border-fl-border"
                }`}
                style={plan.elevated ? { boxShadow: "0 12px 40px rgba(40,40,40,0.18)" } : { boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}
              >
                {plan.elevated && (
                  <span className="inline-block mb-4 px-3 py-1 rounded-full bg-fl-yellow text-fl-black text-[11px] font-sans font-semibold uppercase tracking-wider self-start">
                    Most popular
                  </span>
                )}
                <h2 className={`text-xl font-serif mb-1 ${plan.elevated ? "text-cream" : "text-fl-black"}`}>{plan.name}</h2>
                <p className={`text-sm font-sans mb-5 ${plan.elevated ? "text-cream/60" : "text-fl-muted"}`}>{plan.description}</p>

                <div className="mb-6">
                  <span className={`text-4xl font-serif ${plan.elevated ? "text-cream" : "text-fl-black"}`}>
                    {price === 0 ? "Free" : `$${price}`}
                  </span>
                  {price > 0 && (
                    <span className={`text-sm font-sans ml-1 ${plan.elevated ? "text-cream/50" : "text-fl-muted"}`}>
                      / mo{yearly ? ", billed yearly" : ""}
                    </span>
                  )}
                </div>

                <ul className="space-y-2.5 flex-1 mb-7">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5">
                      <span className={`mt-0.5 text-sm ${plan.elevated ? "text-fl-yellow" : "text-fl-green"}`}>✓</span>
                      <span className={`text-sm font-sans ${plan.elevated ? "text-cream/80" : "text-fl-black"}`}>{f}</span>
                    </li>
                  ))}
                </ul>

                <Link
                  to={plan.ctaLink}
                  className={`btn-press text-center py-2.5 rounded-lg text-sm font-sans font-semibold transition-colors ${
                    plan.elevated
                      ? "bg-fl-yellow text-fl-black hover:bg-fl-yellow-h"
                      : "border border-fl-black text-fl-black hover:bg-fl-black hover:text-cream"
                  }`}
                >
                  {plan.cta}
                </Link>
              </div>
            );
          })}
        </div>
      </section>

      {/* FAQ */}
      <section className="px-6 md:px-12 py-16 border-t border-fl-border">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl font-serif text-fl-black mb-10">Frequently asked questions</h2>
          {FAQ.map((item) => (
            <FaqItem key={item.q} q={item.q} a={item.a} />
          ))}
        </div>
      </section>

      {/* CTA banner */}
      <section className="mx-6 md:mx-12 my-16 rounded-2xl bg-fl-yellow px-10 py-12 flex flex-col md:flex-row items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-serif text-fl-black mb-1">Start studying today.</h2>
          <p className="text-sm font-sans text-fl-black/60">No credit card required. Cancel anytime.</p>
        </div>
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
