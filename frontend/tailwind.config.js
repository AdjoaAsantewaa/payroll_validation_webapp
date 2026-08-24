/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      colors: {
        ink: {
          950: "#0a0a0a",
          900: "#111111",
          800: "#1a1a1a",
        },
      },
      fontSize: {
        xs: ["0.72rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};
