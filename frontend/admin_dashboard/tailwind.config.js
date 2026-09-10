/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // The families are declared in src/index.css with @font-face pointing
        // at public/fonts — self-hosted, because printed admission forms and
        // fee receipts have to render identically on an office machine with no
        // internet. Each stack ends in a system font so a missing binary
        // degrades to something readable rather than to Times.
        sans: ['"SolaimanLipi"', '"Kalpurush"', '"Noto Sans Bengali"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        // Qur'anic text, du'a lines and an institution's Arabic name. A Bangla
        // face renders Arabic script without ligatures or proper joining, so
        // these need their own stack rather than a fallback inside `sans`.
        arabic: ['"Amiri"', '"Scheherazade New"', '"Noto Naskh Arabic"', 'serif'],
      },
    },
  },
  plugins: [],
}
