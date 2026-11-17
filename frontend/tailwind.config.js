/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        gothic: ["var(--font-gothic)", "system-ui", "sans-serif"],
      },
      colors: {
        herald: {
          bg: "#f5f5f7",
          surface: "#ffffff",
          "surface-soft": "#f9fafb",
          text: "#0f172a",
          muted: "#6b7280",
          "muted-soft": "#d1d5db",
          "muted-hard": "#374151",
          accent: "#2563eb",
          "accent-soft": "#e0edff",
          "accent-warm": "#f97316",
          "accent-warm-soft": "#ffedd5",
          navy: "#023047",
          danger: "#b91c1c",
          "danger-soft": "#fef2f2",
        },
      },
      borderRadius: {
        herald: "24px",
        "herald-md": "18px",
        "herald-sm": "14px",
      },
      boxShadow: {
        "herald-soft": "0 18px 40px rgba(15, 23, 42, 0.14)",
        "herald-card": "0 12px 30px rgba(15, 23, 42, 0.10)",
        "herald-btn": "0 12px 24px rgba(2, 48, 71, 0.18)",
      },
    },
  },
  plugins: [],
};
