import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { KernelDashboard } from "@/components/dashboard/keernel-dashboard";

// Force dynamic rendering
export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
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

  // Fetch latest episode
  const { data: latestEpisode } = await supabase
    .from("episodes")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(1)
    .single();

  // Fetch user interests (topics)
  const { data: interests } = await supabase
    .from("user_interests")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  // Fetch ONLY manual pending content
  const { data: manualContent } = await supabase
    .from("content_queue")
    .select("*")
    .eq("user_id", user.id)
    .eq("status", "pending")
    .eq("source", "manual")
    .order("created_at", { ascending: false });

  // Count all pending
  const { count: pendingCount } = await supabase
    .from("content_queue")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user.id)
    .eq("status", "pending");

  // Fetch signal weights
  const { data: signalWeightsData } = await supabase
    .from("user_signal_weights")
    .select("weights")
    .eq("user_id", user.id)
    .single();

  return (
    <KernelDashboard
      user={{
        firstName: profile?.first_name || "",
        email: user.email || "",
        avatarUrl: profile?.avatar_url,
      }}
      episode={latestEpisode}
      topics={interests || []}
      manualContent={manualContent || []}
      pendingCount={pendingCount ?? 0}
      signalWeights={signalWeightsData?.weights || {}}
    />
  );
}
