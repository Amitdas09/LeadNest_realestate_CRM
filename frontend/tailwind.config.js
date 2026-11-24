/** @type {import('tailwindcss').Config} */
// Design tokens — "WhatsApp-native" look (inspired by AiSensy): vivid green accents on white,
// soft mint gradients, deep-green feature surfaces and navigation rail.
// brand-700 is the button colour: deep enough for white text to pass WCAG AA (4.7:1);
// brand-500 is the vivid accent for dots, highlights and decoration.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#ECFDF3", 100: "#D1FADF", 200: "#A6F4C5", 400: "#4ADE80", 500: "#22C55E", 600: "#16A34A", 700: "#0D8442", 800: "#0A6B35", 900: "#0A3D25" },
        forest: { DEFAULT: "#0B2A20", 2: "#0F3A2C", 3: "#14513D", deep: "#07170F" },
        accent: { 50: "#F0F9FF", 600: "#0284C7", 700: "#0369A1" },
        ink: { DEFAULT: "#101828", 2: "#344054", 3: "#667085", 4: "#98A2B3" },
        canvas: "#F6F9F7",
        line: { DEFAULT: "#E4EAE6", strong: "#D0D9D3" },
        sidebar: { DEFAULT: "#0B2A20", fg: "#A3BFB1", border: "rgba(255,255,255,0.06)" },
        wa: { bubble: "#D9FDD3", chat: "#EFEAE2", green: "#00A884", header: "#075E54" },
        // Legacy aliases used by older screens.
        navy: { DEFAULT: "#101828", 700: "#1D2939", 600: "#344054" },
        teal: { DEFAULT: "#0D8442", 50: "#ECFDF3", 100: "#D1FADF", 400: "#4ADE80", 500: "#22C55E", 600: "#16A34A", 700: "#0D8442" },
      },
      fontFamily: {
        // Geist: one clean, modern typeface for the whole product (with Inter as fallback).
        sans: ["Geist", "Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        display: ["Geist", "Inter", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: { "2xs": ["11px", "16px"] },
      borderRadius: { lg: "0.625rem", md: "0.5rem", sm: "0.375rem" },
      boxShadow: {
        xs: "0 1px 2px rgba(16,24,40,0.05)",
        card: "0 1px 2px rgba(16,24,40,0.04), 0 4px 16px -8px rgba(16,24,40,0.08)",
        hover: "0 2px 4px rgba(16,24,40,0.04), 0 12px 28px -10px rgba(16,24,40,0.14)",
        glow: "0 8px 20px -8px rgba(13,132,66,0.55)",
        pop: "0 16px 40px -12px rgba(16,24,40,0.22), 0 4px 10px -4px rgba(16,24,40,0.08)",
      },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "pulse-dot": { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
      },
      animation: { "fade-up": "fade-up 180ms ease-out both", shimmer: "shimmer 1.4s infinite", "pulse-dot": "pulse-dot 2s ease-in-out infinite" },
    },
  },
  plugins: [],
};
