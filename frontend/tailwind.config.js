/** @type {import('tailwindcss').Config} */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        page: v("page"),
        surface: v("surface"),
        raised: v("raised"),
        ink: v("ink"),
        ink2: v("ink2"),
        muted: v("muted"),
        line: v("line"),
        accent: v("accent"),
        good: v("good"),
        warn: v("warn"),
        serious: v("serious"),
        critical: v("critical"),
        hold: v("hold"),
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
