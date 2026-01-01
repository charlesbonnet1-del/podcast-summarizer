import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { LayoutDashboard } from "lucide-react";

// Force dynamic rendering - requires Supabase auth
export const dynamic = 'force-dynamic';

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Aurora Background - CSS only version for server component */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div 
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 240, 255, 0.1), transparent)'
          }}
        />
        <div
          className="absolute w-[600px] h-[600px] rounded-full animate-pulse"
          style={{
            background: 'radial-gradient(circle, rgba(0, 240, 255, 0.12) 0%, transparent 70%)',
            filter: 'blur(80px)',
            top: '-10%',
            right: '-5%',
          }}
        />
        <div
          className="absolute w-[500px] h-[500px] rounded-full animate-pulse"
          style={{
            background: 'radial-gradient(circle, rgba(120, 0, 255, 0.1) 0%, transparent 70%)',
            filter: 'blur(60px)',
            bottom: '10%',
            left: '-5%',
            animationDelay: '1s',
          }}
        />
      </div>

      {/* Dashboard button - top left, premium style */}
      <div className="fixed top-6 left-6 z-50">
        <Link href="/dashboard">
          <button className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-card/60 backdrop-blur-xl border border-border/30 text-foreground hover:bg-card/80 hover:border-primary/30 transition-all font-display font-medium text-sm shadow-lg">
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </button>
        </Link>
      </div>

      {/* Main content */}
      <main className="relative z-10 py-16 px-6">
        <div className="max-w-6xl mx-auto pt-8">
          {children}
        </div>
      </main>
    </div>
  );
}
