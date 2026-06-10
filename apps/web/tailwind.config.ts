import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17201b",
        field: "#f5f6f1",
        line: "#d7dbcf",
        pine: "#21513c",
        signal: "#b85c38",
      },
    },
  },
  plugins: [],
};

export default config;
