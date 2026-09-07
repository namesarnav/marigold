import { useState } from "react";
import { Link } from "react-router-dom";
import Footer from "../components/Footer.jsx";
import Navbar from "../components/Navbar.jsx";

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


export default function Pricing() {
  const [yearly, setYearly] = useState(false);

  return (
    <div className="min-h-screen bg-base-100">
      <Navbar />

      <section className="page py-16 sm:py-20">
        <div className="mx-auto max-w-2xl text-center animate-fade-up">
          <h1 className="text-3xl sm:text-4xl">Simple pricing</h1>
          <p className="mt-3 text-base-content/60">
            Start free. Upgrade when your library outgrows it.
          </p>

          {/* Billing toggle. A label wrapping the input so the whole control is
              clickable and the checkbox stays the accessible element. */}
          <label className="mt-8 inline-flex cursor-pointer items-center gap-3">
            <span className={`text-sm ${yearly ? "text-base-content/50" : "font-medium"}`}>
              Monthly
            </span>
            <input
              type="checkbox"
              className="toggle toggle-primary toggle-sm"
              checked={yearly}
              onChange={(e) => setYearly(e.target.checked)}
            />
            <span className={`text-sm ${yearly ? "font-medium" : "text-base-content/50"}`}>
              Yearly
            </span>
            <span className="badge badge-primary badge-sm font-medium">Save 20%</span>
          </label>
        </div>

        <div className="stagger mt-12 grid items-start gap-5 lg:grid-cols-3">
          {PLANS.map((plan) => {
            const price = yearly ? plan.yearlyPrice : plan.monthlyPrice;
            return (
              <div
                key={plan.name}
                className={`animate-fade-up rounded-xl p-6 opacity-0 ${
                  plan.elevated
                    ? "border-2 border-primary bg-base-100 shadow-lift"
                    : "surface"
                }`}
              >
                <div className="flex items-baseline justify-between">
                  <h2 className="text-lg">{plan.name}</h2>
                  {plan.elevated && (
                    <span className="badge badge-primary badge-sm font-medium">
                      Most popular
                    </span>
                  )}
                </div>

                <p className="mt-1 text-sm text-base-content/60">{plan.description}</p>

                <p className="mt-5 flex items-baseline gap-1">
                  <span className="text-4xl font-semibold tracking-tight">${price}</span>
                  <span className="text-sm text-base-content/50">
                    {price === 0 ? "forever" : "/ month"}
                  </span>
                </p>
                {yearly && price > 0 && (
                  <p className="mt-1 text-xs text-base-content/50">billed annually</p>
                )}

                <Link
                  to={plan.ctaLink}
                  className={`btn mt-6 w-full ${plan.elevated ? "btn-primary" : "btn-outline"}`}
                >
                  {plan.cta}
                </Link>

                <ul className="mt-6 space-y-2.5">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm">
                      <span className="mt-0.5 text-primary" aria-hidden="true">✓</span>
                      <span className="text-base-content/70">{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      <section className="border-t border-base-300 bg-base-200/40">
        <div className="page py-16">
          <h2 className="text-2xl">Questions</h2>

          <div className="mt-6 max-w-2xl space-y-2">
            {FAQ.map((item) => (
              // DaisyUI's collapse handles the open/closed state itself, so the
              // page no longer needs a component and a piece of state per row.
              <div key={item.q} className="collapse collapse-arrow surface">
                <input type="checkbox" />
                <div className="collapse-title text-sm font-medium">{item.q}</div>
                <div className="collapse-content">
                  <p className="text-sm leading-relaxed text-base-content/60">{item.a}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
