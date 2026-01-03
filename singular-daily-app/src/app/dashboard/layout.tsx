import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Toaster } from "sonner";
import { DashboardNav } from "@/components/dashboard/dashboard-nav";

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
    .select("first_name, avatar_url")
    .eq("id", user.id)
    .single();

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <DashboardNav 
        user={{
          firstName: profile?.first_name || "",
          email: user.email || "",
          avatarUrl: profile?.avatar_url,
        }}
      />
      
      {/* Main content - with left padding for sidebar on desktop */}
      <main className="md:ml-64 pt-16 md:pt-0 pb-20 md:pb-0 min-h-screen">
        <div className="max-w-5xl mx-auto p-4 md:p-8">
          {children}
        </div>
      </main>
      
      {/* Toaster */}
      <Toaster 
        position="top-center" 
        richColors 
        toastOptions={{
          className: "font-sans",
        }}
      />
    </div>
  );
}
