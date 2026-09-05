/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#191A23",
        lime: "#B9FF66",
        white: "#FFFFFF",
        surface: "#F3F3F3",
        border: "#DADADB",
        coral: "#FF6B57",
      },
      fontFamily: {
        heading: ["Space Grotesk", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        card: "16px",
        "card-lg": "20px",
        pill: "999px",
      },
    },
  },
  plugins: [],
};
