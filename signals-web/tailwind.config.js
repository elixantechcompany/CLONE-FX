/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'gold-primary': '#f5c842',
        'bg-base': '#07080b',
        'bg-surface': 'rgba(15, 18, 26, 0.88)',
        'bg-card': 'rgba(22, 26, 38, 0.85)',
      },
      fontFamily: {
        ui: ['Outfit', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
