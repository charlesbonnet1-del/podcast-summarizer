import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import TopicSelector from "@/components/onboarding/topic-selector";
import { Sparkles } from "lucide-react";

// Force dynamic rendering - requires Supabase auth
export const dynamic = 'force-dynamic';

export default async function OnboardingPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  // Check if user already completed onboarding
  const { data: profile } = await supabase
    .from("users")
    .select("selected_topics, onboarding_completed, first_name")
    .eq("id", user.id)
    .single();

  // If already completed, redirect to dashboard
  if (profile?.onboarding_completed) {
    redirect("/dashboard");
  }

  const firstName = profile?.first_name || "there";

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="fixed top-0 left-0 right-0 z-10 bg-gradient-to-b from-background via-background to-transparent pb-8">
        <div className="max-w-lg mx-auto px-4 pt-8">
          {/* Logo */}
          <div className="flex items-center gap-2 mb-8">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.2) 0%, rgba(0, 122, 255, 0.15) 100%)',
                boxShadow: '0 0 20px rgba(0, 240, 255, 0.15)',
              }}
            >
              <Sparkles className="w-5 h-5 text-cyan" />
            </div>
            <span className="font-display text-xl font-semibold tracking-tight">
              Keernel
            </span>
          </div>

          {/* Welcome text */}
          <div className="space-y-2">
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Bienvenue, {firstName} !
            </h1>
            <p className="text-muted-foreground text-lg">
              Choisissez les sujets qui vous intéressent pour personnaliser votre podcast quotidien.
            </p>
          </div>
        </div>
      </div>

      {/* Content with top padding for fixed header */}
      <div className="max-w-lg mx-auto px-4 pt-48 pb-8">
        <TopicSelector
          initialTopics={profile?.selected_topics || []}
          minTopics={5}
          isOnboarding={true}
        />
      </div>
    </div>
  );
}
