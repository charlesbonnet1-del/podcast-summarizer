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
    <div className="min-h-screen bg-background">
      {/* Dashboard button - top left, sand color */}
      <div className="fixed top-6 left-6 z-50">
        <Link href="/dashboard">
          <button className="flex items-center gap-2 px-4 py-2 rounded-full bg-[hsl(36_50%_92%)] text-[hsl(0_0%_10%)] hover:bg-[hsl(36_45%_88%)] transition-colors font-display font-medium text-sm shadow-sm">
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </button>
        </Link>
      </div>

      {/* NO NAVBAR - Zero UI like dashboard */}
      <main className="py-12 px-6">
        <div className="max-w-6xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
