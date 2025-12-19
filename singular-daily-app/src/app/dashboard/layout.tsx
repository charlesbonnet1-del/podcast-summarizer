import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { DashboardNav } from "@/components/dashboard/nav";
import { FloatingOrbs } from "@/components/floating-orbs";

// Force dynamic rendering - requires Supabase auth
export const dynamic = 'force-dynamic';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  // Fetch user profile
  const { data: profile } = await supabase
    .from("users")
    .select("*")
    .eq("id", user.id)
    .single();

  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Floating Orbs Background - Light mode only */}
      <FloatingOrbs />
      
      {/* Content */}
      <div className="relative z-10">
        <DashboardNav user={user} profile={profile} />
        <main className="pt-24 pb-32 px-6">
          {children}
        </main>
      </div>
    </div>
  );
}
