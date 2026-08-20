import type { Config } from "tailwindcss";

export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        panel: "rgb(var(--bg-panel) / <alpha-value>)",
        elevated: "rgb(var(--bg-elevated) / <alpha-value>)",
        hover: "rgb(var(--bg-hover) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        "fg-secondary": "rgb(var(--fg-secondary) / <alpha-value>)",
        "fg-muted": "rgb(var(--fg-muted) / <alpha-value>)",
        "fg-faint": "rgb(var(--fg-faint) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-deep": "rgb(var(--accent-deep) / <alpha-value>)",
        success: "rgb(var(--success) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
        // legacy aliases used in older pages
        card: "rgb(var(--bg-elevated) / <alpha-value>)",
        border: "rgba(255,255,255,0.08)",
        "muted-foreground": "rgb(var(--fg-muted) / <alpha-value>)",
      },
      borderRadius: {
        tile: "16px",
        chip: "9999px",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(113,112,255,0.35), 0 8px 24px rgba(0,0,0,0.35)",
        soft: "0 8px 24px rgba(0,0,0,0.35)",
      },
      fontSize: {
        micro: ["0.6875rem", { lineHeight: "1.2", letterSpacing: "0.02em" }],
      },
      maxWidth: {
        home: "72rem",
      },
    },
  },
  plugins: [],
} satisfies Config;
