// filepath: /c:/Users/andre/Documents/Licenta-2025/Licenta-2025/Frontend/tailwind.config.js
import tailwindScrollbar from 'tailwind-scrollbar';

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'zinc-50-10': 'rgba(244, 244, 245, 0.1)',
        'zinc-50-15': 'rgba(244, 244, 245, 0.15)',
        'zinc-50-002': 'rgba(244, 244, 245, 0.02)',
      },
      fontFamily: {
        'sans': ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [tailwindScrollbar],
}