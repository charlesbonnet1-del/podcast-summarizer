"use client";

import Link from "next/link";
import Image from "next/image";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Zap, Bot, Rss } from "lucide-react";

export default function Home() {
  const { resolvedTheme } = useTheme();
  const logoSrc = resolvedTheme === "dark" ? "/logo-sable.svg" : "/logo-charcoal.svg";

  return (
    <div className="min-h-screen bg-background">
      {/* Header - Logo 50% bigger: 32 -> 48 */}
      <header className="fixed top-0 left-0 right-0 z-50 glass-card mx-4 mt-4">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Image 
              src={logoSrc}
              alt="Keernel"
              width={48}
              height={48}
              className="w-12 h-12"
            />
            <span className="title-keernel text-2xl">Keernel</span>
          </div>
          <nav className="flex items-center gap-4">
            <Link href="/login">
              <Button variant="ghost" className="rounded-full font-display font-medium">
                Sign in
              </Button>
            </Link>
            <Link href="/login">
              <Button className="btn-generate rounded-full">
                Get Started
              </Button>
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <main className="pt-36 pb-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-card border border-brass/30 text-sm text-muted-foreground mb-8 font-mono glow-brass">
            <Zap className="w-4 h-4 text-brass" />
            AI-Powered Dialogue Podcast
          </div>
          
          <h1 className="text-5xl md:text-6xl font-display font-semibold tracking-tight text-balance mb-6">
            Your content queue,
            <br />
            <span className="text-brass">transformed into dialogue</span>
          </h1>
          
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-12 text-balance font-body">
            Save YouTube videos, articles, and podcasts. Get a personalized audio dialogue 
            between two expert hosts delivered to your podcast app.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-20">
            <Link href="/login">
              <Button size="lg" className="btn-generate rounded-full text-lg px-8 h-14">
                Start for free
              </Button>
            </Link>
            <Button 
              size="lg" 
              variant="outline" 
              className="rounded-full text-lg px-8 h-14 border-brass/50 text-brass hover:bg-brass/10 font-display font-medium"
            >
              Watch demo
            </Button>
          </div>

          {/* Preview - Logo 50% bigger: 64 -> 96 */}
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-t from-background to-transparent z-10 pointer-events-none h-32 bottom-0 top-auto" />
            <div className="matte-card p-8 glow-brass">
              <div className="aspect-video bg-card rounded-2xl flex items-center justify-center border border-brass/20">
                <div className="text-center">
                  <Image 
                    src={logoSrc}
                    alt="Keernel"
                    width={96}
                    height={96}
                    className="w-24 h-24 mx-auto mb-4 opacity-50"
                  />
                  <p className="text-muted-foreground font-mono">Dashboard Preview</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Features */}
      <section className="py-20 px-6 bg-card/50">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-display font-semibold text-center mb-16">
            How it works
          </h2>
          
          <div className="grid md:grid-cols-3 gap-8">
            <FeatureCard
              icon={<Bot className="w-6 h-6 text-brass" />}
              title="1. Add your content"
              description="Paste any YouTube video, article, or podcast link. Or select topics to follow automatically."
            />
            <FeatureCard
              icon={<Zap className="w-6 h-6 text-brass" />}
              title="2. AI Dialogue"
              description="Breeze & Vale, our expert hosts, discuss and analyze your content in an engaging dialogue."
            />
            <FeatureCard
              icon={<Rss className="w-6 h-6 text-brass" />}
              title="3. Listen Anywhere"
              description="Get your personal RSS feed. Subscribe in Apple Podcasts, Spotify, or any podcast app."
            />
          </div>
        </div>
      </section>

      {/* Footer - Logo 50% bigger: 24 -> 36 */}
      <footer className="py-12 px-6 border-t border-border">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Image 
              src={logoSrc}
              alt="Keernel"
              width={36}
              height={36}
              className="w-9 h-9"
            />
            <span className="font-medium title-keernel text-xl">Keernel</span>
          </div>
          <p className="text-sm text-muted-foreground font-mono">
            © 2024 Keernel. Built with ♥ for curious minds.
          </p>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({ 
  icon, 
  title, 
  description 
}: { 
  icon: React.ReactNode; 
  title: string; 
  description: string;
}) {
  return (
    <div className="matte-card p-8 hover:glow-brass transition-shadow duration-300">
      <div className="w-12 h-12 rounded-xl bg-card border border-brass/30 flex items-center justify-center mb-6">
        {icon}
      </div>
      <h3 className="text-xl font-display font-semibold mb-3">{title}</h3>
      <p className="text-muted-foreground font-body">{description}</p>
    </div>
  );
}
