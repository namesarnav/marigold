/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        cream:           "#f8f3ec",
        "fl-black":      "#282828",
        "fl-yellow":     "#ffe459",
        "fl-yellow-h":   "#f5d800",
        "fl-card":       "#ffffff",
        "fl-border":     "#e8e1d6",
        "fl-muted":      "#9a9080",
        "fl-red":        "#e05c5c",
        "fl-green":      "#4caf87",
      },
      fontFamily: {
        serif: ["Instrument Serif", "Georgia", "serif"],
        sans:  ["Instrument Sans", "sans-serif"],
      },
    },
  },
  plugins: [],
};
