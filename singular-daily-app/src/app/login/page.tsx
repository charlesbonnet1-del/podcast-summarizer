"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { motion } from "framer-motion";

// Pulsing Logo Component
function PulsingLogo({ size = 48 }: { size?: number }) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(0, 240, 255, 0.3) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(0, 122, 255, 0.2) 0%, transparent 70%)',
          filter: 'blur(10px)',
        }}
        animate={{
          scale: [1, 1.2, 1],
          opacity: [0.5, 0.8, 0.5],
        }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      />
      
      <svg viewBox="0 0 100 100" style={{ width: size * 0.8, height: size * 0.8 }} className="relative z-10">
        <defs>
          <linearGradient id="logoGradientLogin" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={isDark ? "#00F0FF" : "#007AFF"} />
            <stop offset="100%" stopColor={isDark ? "#00D4AA" : "#00C6FF"} />
          </linearGradient>
        </defs>
        
        {[40, 32, 24, 16].map((r, i) => (
          <motion.circle
            key={r}
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke="url(#logoGradientLogin)"
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
        
        <motion.circle
          cx="50"
          cy="50"
          r="12"
          fill="url(#logoGradientLogin)"
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          style={{ transformOrigin: '50px 50px' }}
        />
      </svg>
    </div>
  );
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [supabase, setSupabase] = useState<ReturnType<typeof import("@/lib/supabase/client").createClient> | null>(null);
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  
  const isDark = resolvedTheme === "dark";

  useEffect(() => {
    setMounted(true);
    const initSupabase = async () => {
      const { createClient } = await import("@/lib/supabase/client");
      setSupabase(createClient());
    };
    initSupabase();
  }, []);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!supabase) return;
    setLoading(true);

    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      toast.error(error.message);
      setLoading(false);
      return;
    }

    window.location.href = "/dashboard";
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!supabase) return;
    setLoading(true);

    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });

    if (error) {
      toast.error(error.message);
      setLoading(false);
      return;
    }

    toast.success("Check your email for the confirmation link!");
    setLoading(false);
  };

  const handleGoogleSignIn = async () => {
    if (!supabase) return;
    setLoading(true);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });

    if (error) {
      toast.error(error.message);
      setLoading(false);
    }
  };

  if (!mounted) return null;

  return (
    <div className="min-h-screen relative overflow-hidden flex flex-col items-center justify-center p-6">
      {/* Aurora Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div 
          className="absolute inset-0"
          style={{
            background: isDark 
              ? 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 240, 255, 0.15), transparent)'
              : 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 122, 255, 0.08), transparent)'
          }}
        />
        <motion.div
          className="absolute w-[600px] h-[600px] rounded-full"
          style={{
            background: isDark 
              ? 'radial-gradient(circle, rgba(0, 240, 255, 0.15) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(0, 122, 255, 0.1) 0%, transparent 70%)',
            filter: 'blur(80px)',
            top: '-20%',
            right: '-10%',
          }}
          animate={{ x: [0, 30, -20, 0], y: [0, -20, 30, 0], scale: [1, 1.1, 0.95, 1] }}
          transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute w-[500px] h-[500px] rounded-full"
          style={{
            background: isDark 
              ? 'radial-gradient(circle, rgba(120, 0, 255, 0.12) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(100, 0, 255, 0.06) 0%, transparent 70%)',
            filter: 'blur(60px)',
            bottom: '0%',
            left: '-10%',
          }}
          animate={{ x: [0, -30, 20, 0], y: [0, 30, -20, 0], scale: [1, 0.9, 1.1, 1] }}
          transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      {/* Logo */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <Link href="/" className="flex items-center gap-3 mb-8 relative z-10">
          <PulsingLogo size={48} />
          <span className="font-display text-2xl font-semibold">Keernel</span>
        </Link>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className="relative z-10 w-full max-w-md"
      >
        {/* Card glow */}
        <div 
          className="absolute -inset-4 rounded-3xl pointer-events-none"
          style={{
            background: isDark 
              ? 'radial-gradient(ellipse at center, rgba(0, 240, 255, 0.08) 0%, transparent 70%)'
              : 'radial-gradient(ellipse at center, rgba(0, 122, 255, 0.06) 0%, transparent 70%)',
            filter: 'blur(30px)',
          }}
        />
        
        <Card className="relative bg-card/60 backdrop-blur-2xl border-border/30 rounded-3xl shadow-2xl">
          <CardHeader className="text-center pb-2">
            <CardTitle className="text-2xl font-display">Welcome back</CardTitle>
            <CardDescription>Sign in to access your personal audio digest</CardDescription>
          </CardHeader>
          <CardContent className="pt-6">
            <Tabs defaultValue="signin" className="w-full">
              <TabsList className="grid w-full grid-cols-2 mb-6 rounded-xl bg-muted/50 p-1">
                <TabsTrigger value="signin" className="rounded-lg font-mono data-[state=active]:bg-card">Sign In</TabsTrigger>
                <TabsTrigger value="signup" className="rounded-lg font-mono data-[state=active]:bg-card">Sign Up</TabsTrigger>
              </TabsList>

              <TabsContent value="signin">
                <form onSubmit={handleSignIn} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email-signin" className="font-mono text-sm">Email</Label>
                    <Input
                      id="email-signin"
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="rounded-xl h-12 bg-background/50 border-border/50 font-mono focus:border-primary/50"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password-signin" className="font-mono text-sm">Password</Label>
                    <Input
                      id="password-signin"
                      type="password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="rounded-xl h-12 bg-background/50 border-border/50 font-mono focus:border-primary/50"
                    />
                  </div>
                  <motion.button 
                    type="submit" 
                    className="w-full rounded-xl h-12 text-base font-display font-semibold text-white"
                    style={{
                      background: isDark 
                        ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 100%)'
                        : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 100%)',
                    }}
                    disabled={loading}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {loading && <Loader2 className="w-4 h-4 animate-spin mr-2 inline" />}
                    Sign In
                  </motion.button>
                </form>
              </TabsContent>

              <TabsContent value="signup">
                <form onSubmit={handleSignUp} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email-signup" className="font-mono text-sm">Email</Label>
                    <Input
                      id="email-signup"
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="rounded-xl h-12 bg-background/50 border-border/50 font-mono focus:border-primary/50"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password-signup" className="font-mono text-sm">Password</Label>
                    <Input
                      id="password-signup"
                      type="password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      minLength={6}
                      className="rounded-xl h-12 bg-background/50 border-border/50 font-mono focus:border-primary/50"
                    />
                  </div>
                  <motion.button 
                    type="submit" 
                    className="w-full rounded-xl h-12 text-base font-display font-semibold text-white"
                    style={{
                      background: isDark 
                        ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 100%)'
                        : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 100%)',
                    }}
                    disabled={loading}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {loading && <Loader2 className="w-4 h-4 animate-spin mr-2 inline" />}
                    Create Account
                  </motion.button>
                </form>
              </TabsContent>
            </Tabs>

            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-border/30" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card/60 backdrop-blur px-2 text-muted-foreground font-mono">
                  Or continue with
                </span>
              </div>
            </div>

            <motion.button
              type="button"
              className="w-full rounded-xl h-12 border border-border/50 hover:bg-muted/50 font-mono flex items-center justify-center gap-2 transition-colors"
              onClick={handleGoogleSignIn}
              disabled={loading}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Google
            </motion.button>
          </CardContent>
        </Card>
      </motion.div>

      <motion.p 
        className="mt-8 text-sm text-muted-foreground font-mono relative z-10"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        By continuing, you agree to our{" "}
        <Link href="/terms" className="underline hover:text-primary transition-colors">Terms of Service</Link>
        {" "}and{" "}
        <Link href="/privacy" className="underline hover:text-primary transition-colors">Privacy Policy</Link>
      </motion.p>
    </div>
  );
}
