/** @type {import('tailwindcss').Config} */

// DaisyUI's winter theme with every blue replaced by warm marigold shades.
// Spreading winter keeps everything that is not a color exactly as it was; only
// the tokens below change, and every component picks them up through them.
const winter = require("daisyui/src/theming/themes")["winter"];

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
      // Softer than DaisyUI's defaults. Tinted with the espresso text color
      // rather than slate, so shadows stay warm against the cream surfaces.
      boxShadow: {
        subtle: "0 1px 2px rgba(59, 42, 30, 0.05), 0 1px 8px rgba(59, 42, 30, 0.05)",
        lift: "0 4px 16px rgba(59, 42, 30, 0.10)",
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    // One light theme. `darkTheme: false` stops DaisyUI emitting a
    // prefers-color-scheme block that would otherwise repaint half the app dark
    // on a machine set to dark mode, against a palette nobody tested.
    //
    // Each content color is set explicitly and checked against WCAG AA:
    // primary works both as text on the page and behind white text, which is
    // why it is a deep burnt orange rather than a brighter marigold. The
    // brighter yellow lives in secondary, which only ever carries dark text
    // and tints the hero glow.
    themes: [
      {
        marigold: {
          ...winter,
          primary: "#B84E0C", // burnt orange
          "primary-content": "#FFFFFF",
          secondary: "#F2A516", // marigold yellow
          "secondary-content": "#3A2105",
          accent: "#9A3A12", // rust
          "accent-content": "#FFFFFF",
          neutral: "#3D2B1F", // warm dark brown
          "neutral-content": "#FAF3EA",
          "base-100": "#FFFDF9", // warm white
          "base-200": "#FBF4EA", // cream
          "base-300": "#EFE2CF", // sand, for borders
          "base-content": "#3B2A1E", // espresso
          info: "#8C5A1E", // bronze; winter's was cyan
          "info-content": "#FFFFFF",
          success: "#4F7A28", // olive; winter's was teal
          "success-content": "#FFFFFF",
          warning: "#B7791F", // amber
          "warning-content": "#2A1703",
          error: "#B42318", // brick
          "error-content": "#FFFFFF",
        },
      },
    ],
    darkTheme: false,
    logs: false,
  },
};
