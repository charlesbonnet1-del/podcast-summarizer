"use client";

import Link from "next/link";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Zap, Bot, Rss, Play } from "lucide-react";
import { motion } from "framer-motion";
import { useState, useEffect } from "react";

// ============================================
// AURORA BACKGROUND - Reused from dashboard
// ============================================

function AuroraBackground() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  const isDark = resolvedTheme === "dark";

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {/* Base gradient mesh */}
      <div 
        className="absolute inset-0"
        style={{
          background: isDark 
            ? 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 240, 255, 0.15), transparent)'
            : 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 122, 255, 0.08), transparent)'
        }}
      />
      
      {/* Animated aurora blobs */}
      <motion.div
        className="absolute w-[800px] h-[800px] rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(0, 240, 255, 0.2) 0%, rgba(0, 150, 255, 0.1) 40%, transparent 70%)'
            : 'radial-gradient(circle, rgba(0, 122, 255, 0.12) 0%, rgba(0, 200, 255, 0.06) 40%, transparent 70%)',
          filter: 'blur(80px)',
          top: '-20%',
          right: '-10%',
        }}
        animate={{
          x: [0, 50, -30, 0],
          y: [0, -30, 50, 0],
          scale: [1, 1.1, 0.95, 1],
          rotate: [0, 10, -5, 0],
        }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      
      <motion.div
        className="absolute w-[600px] h-[600px] rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(120, 0, 255, 0.15) 0%, rgba(0, 240, 255, 0.08) 40%, transparent 70%)'
            : 'radial-gradient(circle, rgba(100, 0, 255, 0.08) 0%, rgba(0, 200, 255, 0.04) 40%, transparent 70%)',
          filter: 'blur(60px)',
          bottom: '0%',
          left: '-10%',
        }}
        animate={{
          x: [0, -40, 30, 0],
          y: [0, 40, -20, 0],
          scale: [1, 0.9, 1.15, 1],
          rotate: [0, -15, 10, 0],
        }}
        transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
      />

      <motion.div
        className="absolute w-[500px] h-[500px] rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(0, 255, 200, 0.12) 0%, transparent 60%)'
            : 'radial-gradient(circle, rgba(0, 200, 150, 0.06) 0%, transparent 60%)',
          filter: 'blur(70px)',
          top: '40%',
          left: '50%',
          transform: 'translateX(-50%)',
        }}
        animate={{
          scale: [1, 1.2, 0.9, 1],
          opacity: [0.5, 0.8, 0.4, 0.5],
        }}
        transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Noise texture overlay */}
      <div 
        className="absolute inset-0 opacity-[0.015]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />
    </div>
  );
}

// ============================================
// PULSING LOGO - Animated concentric circles
// ============================================

function PulsingLogo({ size = 80 }: { size?: number }) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      {/* Glow behind logo */}
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(0, 240, 255, 0.3) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(0, 122, 255, 0.2) 0%, transparent 70%)',
          filter: 'blur(15px)',
        }}
        animate={{
          scale: [1, 1.2, 1],
          opacity: [0.5, 0.8, 0.5],
        }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      />
      
      {/* SVG Animated Logo */}
      <svg viewBox="0 0 100 100" style={{ width: size * 0.8, height: size * 0.8 }} className="relative z-10">
        <defs>
          <linearGradient id="logoGradientLanding" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={isDark ? "#00F0FF" : "#007AFF"} />
            <stop offset="100%" stopColor={isDark ? "#00D4AA" : "#00C6FF"} />
          </linearGradient>
        </defs>
        
        {/* Concentric circles with staggered pulse */}
        {[40, 32, 24, 16].map((r, i) => (
          <motion.circle
            key={r}
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke="url(#logoGradientLanding)"
            strokeWidth={i === 3 ? 0 : 2}
            initial={{ scale: 1, opacity: 0.8 }}
            animate={{ 
              scale: [1, 1.05, 1],
              opacity: [0.6 + i * 0.1, 0.9, 0.6 + i * 0.1],
            }}
            transition={{ 
              duration: 2,
              delay: i * 0.2,
              repeat: Infinity,
              ease: "easeInOut"
            }}
            style={{ transformOrigin: '50px 50px' }}
          />
        ))}
        
        {/* Center filled circle */}
        <motion.circle
          cx="50"
          cy="50"
          r="12"
          fill="url(#logoGradientLanding)"
          animate={{ 
            scale: [1, 1.1, 1],
          }}
          transition={{ 
            duration: 2,
            repeat: Infinity,
            ease: "easeInOut"
          }}
          style={{ transformOrigin: '50px 50px' }}
        />
      </svg>
    </div>
  );
}

// ============================================
// MAIN LANDING PAGE
// ============================================

export default function Home() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const isDark = resolvedTheme === "dark";

  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  return (
    <div className="min-h-screen relative overflow-hidden">
      <AuroraBackground />
      
      {/* Header */}
      <motion.header 
        className="fixed top-0 left-0 right-0 z-50 mx-4 mt-4"
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6 }}
      >
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between rounded-2xl bg-card/60 backdrop-blur-2xl border border-border/30">
          <div className="flex items-center gap-3">
            <PulsingLogo size={40} />
            <span className="font-display text-xl font-semibold">Keernel</span>
          </div>
          <nav className="flex items-center gap-4">
            <Link href="/login">
              <Button variant="ghost" className="rounded-full font-display font-medium">
                Sign in
              </Button>
            </Link>
            <Link href="/login">
              <motion.div
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <Button 
                  className="rounded-full font-display font-medium text-white"
                  style={{
                    background: isDark 
                      ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 100%)'
                      : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 100%)',
                  }}
                >
                  Get Started
                </Button>
              </motion.div>
            </Link>
          </nav>
        </div>
      </motion.header>

      {/* Hero */}
      <main className="relative z-10 pt-36 pb-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <motion.div 
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-card/60 backdrop-blur-xl border border-border/30 text-sm text-muted-foreground mb-8 font-mono"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Zap className="w-4 h-4" style={{ color: isDark ? '#00F0FF' : '#007AFF' }} />
            AI-Powered Dialogue Podcast
          </motion.div>
          
          {/* Title */}
          <motion.h1 
            className="text-5xl md:text-6xl font-display font-semibold tracking-tight text-balance mb-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            Your content queue,
            <br />
            <span 
              className="bg-clip-text text-transparent"
              style={{
                backgroundImage: isDark 
                  ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 50%, #7B00FF 100%)'
                  : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 50%, #0066FF 100%)',
              }}
            >
              transformed into dialogue
            </span>
          </motion.h1>
          
          {/* Subtitle */}
          <motion.p 
            className="text-xl text-muted-foreground max-w-2xl mx-auto mb-12 text-balance"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            Save YouTube videos, articles, and podcasts. Get a personalized audio dialogue 
            between two expert hosts delivered to your podcast app.
          </motion.p>

          {/* CTAs */}
          <motion.div 
            className="flex flex-col sm:flex-row gap-4 justify-center mb-20"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <Link href="/login">
              <motion.button
                className="relative px-8 h-14 rounded-full text-lg font-display font-semibold text-white overflow-hidden"
                style={{
                  background: isDark 
                    ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 100%)'
                    : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 100%)',
                  boxShadow: isDark 
                    ? '0 0 30px rgba(0, 240, 255, 0.3)'
                    : '0 0 30px rgba(0, 122, 255, 0.2)',
                }}
                whileHover={{ scale: 1.05, y: -2 }}
                whileTap={{ scale: 0.98 }}
              >
                {/* Shimmer effect */}
                <motion.div
                  className="absolute inset-0"
                  style={{
                    background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.2) 50%, transparent 100%)',
                  }}
                  animate={{ x: ['-100%', '100%'] }}
                  transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                />
                <span className="relative">Start for free</span>
              </motion.button>
            </Link>
            <motion.button
              className="px-8 h-14 rounded-full text-lg font-display font-medium border-2 flex items-center justify-center gap-2"
              style={{
                borderColor: isDark ? 'rgba(0, 240, 255, 0.3)' : 'rgba(0, 122, 255, 0.3)',
                color: isDark ? '#00F0FF' : '#007AFF',
              }}
              whileHover={{ 
                scale: 1.05,
                borderColor: isDark ? 'rgba(0, 240, 255, 0.6)' : 'rgba(0, 122, 255, 0.6)',
              }}
              whileTap={{ scale: 0.98 }}
            >
              <Play className="w-5 h-5" />
              Watch demo
            </motion.button>
          </motion.div>

          {/* Preview Card */}
          <motion.div 
            className="relative"
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6, duration: 0.8 }}
          >
            {/* Glow behind card */}
            <div 
              className="absolute -inset-10 rounded-3xl pointer-events-none"
              style={{
                background: isDark 
                  ? 'radial-gradient(ellipse at center, rgba(0, 240, 255, 0.1) 0%, transparent 70%)'
                  : 'radial-gradient(ellipse at center, rgba(0, 122, 255, 0.08) 0%, transparent 70%)',
                filter: 'blur(40px)',
              }}
            />
            
            <div className="relative rounded-3xl bg-card/60 backdrop-blur-2xl border border-border/30 p-8 shadow-2xl">
              <div className="aspect-video bg-background/50 rounded-2xl flex items-center justify-center border border-border/20">
                <div className="text-center">
                  <PulsingLogo size={80} />
                  <p className="text-muted-foreground font-mono mt-4">Dashboard Preview</p>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </main>

      {/* Features */}
      <section className="relative z-10 py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.h2 
            className="text-3xl font-display font-semibold text-center mb-16"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            How it works
          </motion.h2>
          
          <div className="grid md:grid-cols-3 gap-8">
            <FeatureCard
              icon={<Bot className="w-6 h-6" />}
              title="1. Add your content"
              description="Paste any YouTube video, article, or podcast link. Or select topics to follow automatically."
              delay={0}
            />
            <FeatureCard
              icon={<Zap className="w-6 h-6" />}
              title="2. AI Dialogue"
              description="Breeze & Vale, our expert hosts, discuss and analyze your content in an engaging dialogue."
              delay={0.1}
            />
            <FeatureCard
              icon={<Rss className="w-6 h-6" />}
              title="3. Listen Anywhere"
              description="Get your personal RSS feed. Subscribe in Apple Podcasts, Spotify, or any podcast app."
              delay={0.2}
            />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 py-12 px-6 border-t border-border/30">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <PulsingLogo size={32} />
            <span className="font-display font-medium text-xl">Keernel</span>
          </div>
          <p className="text-sm text-muted-foreground font-mono">
            © 2025 Keernel. Built with ♥ for curious minds.
          </p>
        </div>
      </footer>
    </div>
  );
}

// ============================================
// FEATURE CARD
// ============================================

function FeatureCard({ 
  icon, 
  title, 
  description,
  delay = 0
}: { 
  icon: React.ReactNode; 
  title: string; 
  description: string;
  delay?: number;
}) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    <motion.div 
      className="relative group"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay }}
    >
      {/* Hover glow */}
      <motion.div
        className="absolute -inset-4 rounded-3xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{
          background: isDark 
            ? 'radial-gradient(ellipse at center, rgba(0, 240, 255, 0.1) 0%, transparent 70%)'
            : 'radial-gradient(ellipse at center, rgba(0, 122, 255, 0.08) 0%, transparent 70%)',
          filter: 'blur(20px)',
        }}
      />
      
      <div className="relative rounded-2xl bg-card/60 backdrop-blur-xl border border-border/30 p-8 h-full transition-all duration-300 group-hover:border-primary/30">
        <div 
          className="w-12 h-12 rounded-xl flex items-center justify-center mb-6"
          style={{
            background: isDark 
              ? 'rgba(0, 240, 255, 0.1)'
              : 'rgba(0, 122, 255, 0.1)',
            color: isDark ? '#00F0FF' : '#007AFF',
          }}
        >
          {icon}
        </div>
        <h3 className="text-xl font-display font-semibold mb-3">{title}</h3>
        <p className="text-muted-foreground">{description}</p>
      </div>
    </motion.div>
  );
}
