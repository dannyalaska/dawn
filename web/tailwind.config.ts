import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './context/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}'
  ],
  theme: {
    extend: {
      colors: {
        dawn: {
          background: '#050812',
          surface: '#0f1627',
          card: '#151e3a',
          accent: '#f59e0b',
          accentSoft: '#ec4899',
          aurora: '#0ea5e9',
          auroraSoft: '#6366f1',
          text: '#f1f5f9',
          dark: '#0a0e1a',
          lighter: '#1a2332'
        }
      },
      backgroundImage: {
        'dawn-gradient': 'radial-gradient(circle at 10% 20%, rgba(248,113,113,0.25), transparent 45%), radial-gradient(circle at 80% 0%, rgba(59,130,246,0.25), transparent 40%), radial-gradient(circle at 50% 80%, rgba(248,250,107,0.15), transparent 55%)'
      },
      boxShadow: {
        aurora: '0 20px 60px rgba(14,165,233,0.25)',
        ember: '0 20px 50px rgba(244,63,94,0.25)',
        'sm-glass': '0 4px 12px rgba(0,0,0,0.3)',
        'md-glass': '0 8px 24px rgba(0,0,0,0.4)',
        'lg-glass': '0 20px 60px rgba(0,0,0,0.5)'
      },
      keyframes: {
        'pulse-soft': {
          '0%, 100%': { opacity: 0.5 },
          '50%': { opacity: 1 }
        },
        'float-slow': {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-12px)' }
        },
        'slide-in': {
          'from': { transform: 'translateX(-20px)', opacity: '0' },
          'to': { transform: 'translateX(0)', opacity: '1' }
        },
        'slide-up': {
          'from': { transform: 'translateY(20px)', opacity: '0' },
          'to': { transform: 'translateY(0)', opacity: '1' }
        },
        'fade-in': {
          'from': { opacity: '0' },
          'to': { opacity: '1' }
        },
        'spin-slow': {
          'from': { transform: 'rotate(0deg)' },
          'to': { transform: 'rotate(360deg)' }
        }
      },
      animation: {
        'pulse-soft': 'pulse-soft 6s ease-in-out infinite',
        'float-slow': 'float-slow 8s ease-in-out infinite',
        'slide-in': 'slide-in 0.3s ease-out',
        'slide-up': 'slide-up 0.4s ease-out',
        'fade-in': 'fade-in 0.3s ease-out',
        'spin-slow': 'spin-slow 3s linear infinite'
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.875rem', { lineHeight: '1.25rem' }],
        base: ['1rem', { lineHeight: '1.5rem' }],
        lg: ['1.125rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
        '5xl': ['3rem', { lineHeight: '3.5rem' }]
      },
      spacing: {
        '0.5': '0.125rem',
        '1.5': '0.375rem',
        '2.5': '0.625rem',
        '3.5': '0.875rem'
      }
    }
  },
  plugins: []
};

export default config;
