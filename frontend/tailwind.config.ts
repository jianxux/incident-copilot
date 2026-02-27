import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        coral: { DEFAULT: "#e05a3a", light: "#e87a60", dark: "#c04428" },
        cream: { DEFAULT: "#faf6ef", dark: "#f0ebe0" },
        sidebar: { DEFAULT: "#1e1e2e", hover: "#2a2a3e" },
      },
      fontFamily: {
        serif: ['"Instrument Serif"', "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
