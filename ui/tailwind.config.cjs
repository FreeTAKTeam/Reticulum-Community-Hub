/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{vue,ts}"] ,
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "rth-bg": "#0b1120",
        "rth-panel": "#111827",
        "rth-border": "#1f2937",
        "rth-accent": "#38bdf8",
        "rth-text": "#e5e7eb"
      }
    }
  },
  plugins: []
};
