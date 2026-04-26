/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"DM Sans"', 'system-ui', 'sans-serif'],
        body: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        panel: {
          bg: '#0c0e14',
          surface: '#12151e',
          raised: '#181c28',
          border: '#1e2333',
          hover: '#232840',
        },
        haumea: {
          50: '#e8fce4',
          100: '#c5f5bc',
          200: '#8fea7a',
          300: '#5cdb45',
          400: '#3ec928',
          500: '#2ba31e',
          600: '#1f7a16',
          700: '#16570f',
        },
        txt: {
          primary: '#e4e7ef',
          secondary: '#8b92a8',
          muted: '#555d78',
        },
        danger: '#e04858',
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: 1 },
          '50%': { opacity: 0.4 },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
