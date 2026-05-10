/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{vue,ts}"] ,
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "rth-bg": "#0f1320",
        "rth-panel": "#1b2033",
        "rth-panel-muted": "#141828",
        "rth-border": "#252a3d",
        "rth-accent": "#4db6ff",
        "rth-text": "#e7ecf5",
        "rth-muted": "#a7b0c4",
        "rth-warning": "#f59e0b",
        "rth-danger": "#ef4444"
      }
    }
  },
  plugins: []
};
