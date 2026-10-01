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
          rail: "#1e7a55",
          void: "#04140e",
          fog: "#9dc7b2",
        },
        wood: "#3b2519",
        gold: {
          DEFAULT: "#facc15",
          200: "#fef3c7",
          300: "#fde68a",
          600: "#d9a406",
          800: "#8a6604",
        },
        ivory: "#f8f4e9",
        ink: "#14261e",
        lie: "#e5484d",
        truth: "#34d399",
        seat: {
          1: "#e11d48", // rose-600
          2: "#0284c7", // sky-600
          3: "#d97706", // amber-600
          4: "#7c3aed", // violet-600
        },
      },
      fontFamily: {
        display: ["Alegreya", "Georgia", "serif"],
        sans: ["'Work Sans'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 2px 4px rgba(0,0,0,0.35), 0 1px 1px rgba(0,0,0,0.2)",
        "card-lg": "0 8px 20px rgba(0,0,0,0.45)",
        gold: "0 0 0 1px rgba(250,204,21,0.5), 0 8px 28px rgba(250,204,21,0.22)",
      },
      backgroundImage: {
        // The felt surface: a 4px 45-degree weave over a radial vignette that darkens
        // to felt-void at the edges. Named `felt-table` rather than `felt` so it can
        // never collide with the `felt` colour's own bg- utility.
        "felt-table":
          "repeating-linear-gradient(45deg, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 2px, transparent 2px, transparent 4px), radial-gradient(120% 90% at 50% 18%, #155a3f 0%, #0b3d2e 42%, #062219 78%, #04140e 100%)",
        weave:
          "repeating-linear-gradient(45deg, rgba(255,255,255,0.06) 0px, rgba(255,255,255,0.06) 2px, transparent 2px, transparent 4px)",
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
          "70%": { boxShadow: "0 0 0 12px rgba(250, 204, 21, 0)" },
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
        dealIn: {
          "0%": { transform: "translateY(40px) rotate(-8deg) scale(0.9)", opacity: "0" },
          "100%": { transform: "translateY(0) rotate(0) scale(1)", opacity: "1" },
        },
        hover3: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        goldSweep: {
          "0%": { backgroundPosition: "-220% 0" },
          "100%": { backgroundPosition: "220% 0" },
        },
        tick: {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.06)" },
        },
        shake: {
          "0%, 100%": { transform: "translateX(0)" },
          "20%": { transform: "translateX(-5px)" },
          "40%": { transform: "translateX(5px)" },
          "60%": { transform: "translateX(-3px)" },
          "80%": { transform: "translateX(3px)" },
        },
        slowSpin: {
          "0%": { transform: "rotate(0)" },
          "100%": { transform: "rotate(360deg)" },
        },
        riseFade: {
          "0%": { transform: "translateY(0)", opacity: "0.9" },
          "100%": { transform: "translateY(-70px)", opacity: "0" },
        },
        revealFlip: {
          "0%": { transform: "rotateY(180deg)" },
          "55%": { transform: "rotateY(180deg)" },
          "100%": { transform: "rotateY(0)" },
        },
        stampIn: {
          "0%": { transform: "scale(2.4) rotate(-14deg)", opacity: "0" },
          "60%": { transform: "scale(0.92) rotate(-4deg)", opacity: "1" },
          "100%": { transform: "scale(1) rotate(-4deg)", opacity: "1" },
        },
        breathe: {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
        fallGold: {
          "0%": { transform: "translateY(-10px) scale(1)", opacity: "0" },
          "20%": { opacity: "0.9" },
          "100%": { transform: "translateY(120px) scale(0.6)", opacity: "0" },
        },
      },
      animation: {
        "pop-in": "popIn 0.2s ease-out",
        "flip-in": "flipIn 0.35s ease-out",
        "pulse-ring": "pulseRing 1.6s ease-out infinite",
        "shrink-bar": "shrinkBar 5000ms linear forwards",
        "slide-up": "slideUp 0.2s ease-out",
        "deal-in": "dealIn 0.35s ease-out backwards",
        hover3: "hover3 3s ease-in-out infinite",
        "gold-sweep": "goldSweep 2.2s linear infinite",
        tick: "tick 0.25s ease-out",
        shake: "shake 0.4s ease-in-out",
        "slow-spin": "slowSpin 1.4s linear infinite",
        "rise-fade": "riseFade 0.9s ease-out forwards",
        "reveal-flip": "revealFlip 0.6s ease-out backwards",
        "stamp-in": "stampIn 0.5s cubic-bezier(0.2, 1.4, 0.4, 1) backwards",
        breathe: "breathe 1.8s ease-in-out infinite",
        "fall-gold": "fallGold 2.4s ease-in infinite",
      },
    },
  },
  plugins: [],
};
