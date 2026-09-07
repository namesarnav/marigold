/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        // One typeface throughout. The previous design paired a serif for
        // headings with a sans for everything else; a single family with real
        // weight contrast is quieter and reads as more deliberate at this size.
        sans: ["Instrument Sans", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      // Softer than DaisyUI's defaults, applied through the theme tokens below
      // so components pick them up without per-element overrides.
      boxShadow: {
        subtle: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 8px rgba(15, 23, 42, 0.04)",
        lift: "0 4px 16px rgba(15, 23, 42, 0.08)",
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    // Winter only, and light only. `darkTheme: false` stops DaisyUI emitting a
    // prefers-color-scheme block that would otherwise repaint half the app dark
    // on a machine set to dark mode, against a light palette we never tested.
    themes: ["winter"],
    darkTheme: false,
    logs: false,
  },
};
