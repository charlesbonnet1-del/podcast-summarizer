import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Separator } from "@/components/ui/separator";
import { MagicBar } from "@/components/dashboard/magic-bar";
import { ActiveTopics } from "@/components/dashboard/active-topics";
import { ManualAdds } from "@/components/dashboard/manual-adds";
import { StickyPlayer } from "@/components/dashboard/sticky-player";
import { ShowNotes } from "@/components/dashboard/show-notes";
import { GenerateButton } from "@/components/dashboard/generate-button";

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

  // Fetch ONLY manual pending content (not auto-fetched news)
  const { data: manualContent } = await supabase
    .from("content_queue")
    .select("*")
    .eq("user_id", user.id)
    .eq("status", "pending")
    .eq("source", "manual")
    .order("created_at", { ascending: false });

  // Count all pending (for generate button)
  const { count: pendingCount } = await supabase
    .from("content_queue")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user.id)
    .eq("status", "pending");

  const sourcesData = latestEpisode?.sources_data || [];
  const hasTopics = (interests?.length ?? 0) > 0;

  return (
    <>
      {/* Main Content - with bottom padding for sticky player */}
      <div className="max-w-2xl mx-auto space-y-8 pb-32">
        {/* Empty State - When no episode yet */}
        {!latestEpisode && (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-secondary/50 flex items-center justify-center">
              <span className="text-3xl">🎧</span>
            </div>
            <h2 className="text-xl font-medium mb-2">Your daily podcast awaits</h2>
            <p className="text-muted-foreground text-sm max-w-sm mx-auto">
              Add topics you care about, and we&apos;ll create a personalized audio digest just for you.
            </p>
          </div>
        )}

        {/* Show Notes (when episode exists) */}
        {latestEpisode && sourcesData.length > 0 && (
          <section>
            <ShowNotes 
              sources={sourcesData} 
              summary={latestEpisode.summary_text} 
            />
          </section>
        )}

        <Separator className="opacity-50" />

        {/* Magic Bar - Main Input */}
        <section className="space-y-3">
          <MagicBar />
          
          {/* Active Topics - Small pills under Magic Bar */}
          <ActiveTopics topics={interests || []} />
        </section>

        {/* Manual Adds - Only visible when there are manual items */}
        <ManualAdds items={manualContent || []} />

        {/* Generate Button - Always visible at bottom */}
        <div className="pt-4">
          <GenerateButton 
            pendingCount={pendingCount ?? 0} 
            hasTopics={hasTopics}
          />
        </div>
      </div>

      {/* Sticky Player - Fixed at bottom */}
      {latestEpisode && (
        <StickyPlayer episode={latestEpisode} />
      )}
    </>
  );
}
