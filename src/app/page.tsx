import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Headphones, Zap, Bot, Rss } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 glass border-b border-border/50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-primary flex items-center justify-center">
              <Headphones className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="font-semibold text-lg">Singular Daily</span>
          </div>
          <nav className="flex items-center gap-4">
            <Link href="/login">
              <Button variant="ghost" className="rounded-xl">
                Sign in
              </Button>
            </Link>
            <Link href="/login">
              <Button className="rounded-xl">
                Get Started
              </Button>
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <main className="pt-32 pb-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-secondary text-sm text-muted-foreground mb-8">
            <Zap className="w-4 h-4" />
            AI-Powered Personal Podcast
          </div>
          
          <h1 className="text-5xl md:text-6xl font-semibold tracking-tight text-balance mb-6">
            Your content queue,
            <br />
            <span className="gradient-text">transformed into audio</span>
          </h1>
          
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-12 text-balance">
            Save YouTube videos, articles, and podcasts. Get a personalized audio digest 
            delivered to your podcast app every morning.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-20">
            <Link href="/login">
              <Button size="lg" className="rounded-xl text-lg px-8 h-14 shadow-zen hover-lift">
                Start for free
              </Button>
            </Link>
            <Button 
              size="lg" 
              variant="outline" 
              className="rounded-xl text-lg px-8 h-14"
            >
              Watch demo
            </Button>
          </div>

          {/* Preview */}
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-t from-background to-transparent z-10 pointer-events-none h-32 bottom-0 top-auto" />
            <div className="bg-card rounded-3xl shadow-zen-lg border border-border p-8">
              <div className="aspect-video bg-secondary rounded-2xl flex items-center justify-center">
                <div className="text-center">
                  <Headphones className="w-16 h-16 text-muted-foreground/50 mx-auto mb-4" />
                  <p className="text-muted-foreground">Dashboard Preview</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Features */}
      <section className="py-20 px-6 bg-secondary/50">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-semibold text-center mb-16">
            How it works
          </h2>
          
          <div className="grid md:grid-cols-3 gap-8">
            <FeatureCard
              icon={<Bot className="w-6 h-6" />}
              title="1. Share via Telegram"
              description="Send any YouTube video, article, or podcast link to our Telegram bot. No app to install."
            />
            <FeatureCard
              icon={<Zap className="w-6 h-6" />}
              title="2. AI Processing"
              description="Our AI extracts key insights, creates a script, and generates natural-sounding audio."
            />
            <FeatureCard
              icon={<Rss className="w-6 h-6" />}
              title="3. Listen Anywhere"
              description="Get your personal RSS feed. Subscribe in Apple Podcasts, Spotify, or any podcast app."
            />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 border-t border-border">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-primary flex items-center justify-center">
              <Headphones className="w-3 h-3 text-primary-foreground" />
            </div>
            <span className="font-medium">Singular Daily</span>
          </div>
          <p className="text-sm text-muted-foreground">
            © 2024 Singular Daily. Built with ♥ for curious minds.
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
    <div className="bg-card rounded-2xl p-8 shadow-zen hover-lift border border-border">
      <div className="w-12 h-12 rounded-xl bg-secondary flex items-center justify-center mb-6">
        {icon}
      </div>
      <h3 className="text-xl font-semibold mb-3">{title}</h3>
      <p className="text-muted-foreground">{description}</p>
    </div>
  );
}
