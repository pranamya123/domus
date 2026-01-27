/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Custom color palette for Domus
        domus: {
          primary: '#3B82F6',    // Blue
          secondary: '#10B981',  // Green
          accent: '#8B5CF6',     // Purple
          warning: '#F59E0B',    // Amber
          danger: '#EF4444',     // Red
          dark: {
            100: '#1E293B',
            200: '#0F172A',
            300: '#020617',
          }
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
