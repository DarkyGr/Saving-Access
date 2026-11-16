/** @type {import('tailwindcss').Config} */

// Palettes read from CSS variables (src/theme.css, task 37.3): the same class
// names follow the light / dark theme, and `indigo` follows the accent colour
// chosen in Settings.
const SHADES = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"];
const fromVars = (name) =>
  Object.fromEntries(SHADES.map((s) => [s, `rgb(var(--c-${name}-${s}) / <alpha-value>)`]));

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        white: "rgb(var(--c-white) / <alpha-value>)",
        gray: fromVars("gray"),
        red: fromVars("red"),
        green: fromVars("green"),
        amber: fromVars("amber"),
        yellow: fromVars("yellow"),
        indigo: fromVars("accent"),
      },
    },
  },
  plugins: [],
};
