import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Toaster } from "sonner";

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

  return (
    <div className="min-h-screen bg-background">
      {/* Main content - no navbar (Zero-UI) */}
      <main>
        {children}
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
