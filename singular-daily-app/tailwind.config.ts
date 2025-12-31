import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        // Neo-Editorial Tech Brand Colors
        cyan: {
          DEFAULT: '#00F0FF',
          light: '#66F5FF',
          dark: '#00C8D4',
        },
        'tech-blue': {
          DEFAULT: '#007AFF',
          light: '#4DA3FF',
          dark: '#0055B3',
        },
        ink: {
          DEFAULT: '#050505',
          light: '#0F0F0F',
        },
        cloud: {
          DEFAULT: '#F5F5F7',
          dark: '#E5E5E7',
        },
        // Legacy mappings for backward compatibility
        brass: {
          DEFAULT: '#00F0FF',
          light: '#66F5FF',
          dark: '#00C8D4',
        },
        charcoal: {
          DEFAULT: '#1A1A1B',
          light: '#222222',
          dark: '#121212',
        },
        sand: {
          DEFAULT: '#F5F5F7',
          light: '#FFFFFF',
          dark: '#E5E5E7',
        },
        cream: {
          DEFAULT: '#F2F2F2',
        },
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      fontFamily: {
        display: ['Space Grotesk', '-apple-system', 'sans-serif'],
        body: ['Inter', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        serif: ['Space Grotesk', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(0, 240, 255, 0.25)',
        'glow-cyan-lg': '0 0 30px rgba(0, 240, 255, 0.4)',
        'glow-blue': '0 0 20px rgba(0, 122, 255, 0.3)',
        'glow-blue-lg': '0 0 30px rgba(0, 122, 255, 0.5)',
        'glow-brass': '0 0 20px rgba(0, 240, 255, 0.25)',
        'glow-brass-lg': '0 0 30px rgba(0, 240, 255, 0.4)',
        'glow-charcoal': '0 0 20px rgba(26, 26, 26, 0.2)',
      },
      backdropBlur: {
        'glass': '16px',
        'glass-lg': '24px',
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
