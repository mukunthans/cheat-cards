/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        felt: {
          DEFAULT: "#0b3d2e",
          dark: "#062219",
          light: "#155a3f",
        },
      },
      fontFamily: {
        display: ["'Georgia'", "'Times New Roman'", "serif"],
      },
      boxShadow: {
        card: "0 2px 4px rgba(0,0,0,0.35), 0 1px 1px rgba(0,0,0,0.2)",
        "card-lg": "0 8px 20px rgba(0,0,0,0.45)",
      },
      keyframes: {
        popIn: {
          "0%": { transform: "scale(0.6)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
        flipIn: {
          "0%": { transform: "rotateY(90deg)", opacity: "0" },
          "100%": { transform: "rotateY(0deg)", opacity: "1" },
        },
        pulseRing: {
          "0%": { boxShadow: "0 0 0 0 rgba(250, 204, 21, 0.55)" },
          "70%": { boxShadow: "0 0 0 10px rgba(250, 204, 21, 0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(250, 204, 21, 0)" },
        },
        shrinkBar: {
          "0%": { width: "100%" },
          "100%": { width: "0%" },
        },
        slideUp: {
          "0%": { transform: "translateY(12px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
      animation: {
        "pop-in": "popIn 0.2s ease-out",
        "flip-in": "flipIn 0.35s ease-out",
        "pulse-ring": "pulseRing 1.6s ease-out infinite",
        "shrink-bar": "shrinkBar 5000ms linear forwards",
        "slide-up": "slideUp 0.2s ease-out",
      },
    },
  },
  plugins: [],
};
