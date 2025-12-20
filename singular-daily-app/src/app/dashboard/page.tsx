import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Separator } from "@/components/ui/separator";
import { MagicBar } from "@/components/dashboard/magic-bar";
import { ActiveTopics } from "@/components/dashboard/active-topics";
import { ManualAdds } from "@/components/dashboard/manual-adds";
import { PlayerPod } from "@/components/dashboard/player-pod";
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
  const firstName = profile?.first_name || "there";

  return (
    <>
      {/* Main Content - with bottom padding for player pod */}
      <div className="max-w-2xl mx-auto space-y-8 pb-32">
        {/* Greeting */}
        <div className="text-center pt-8">
          <h1 className="font-serif text-3xl font-medium">
            Bonjour, {firstName}
          </h1>
          <p className="text-muted-foreground mt-1">
            Votre podcast quotidien vous attend
          </p>
        </div>

        {/* Magic Bar - Hero Input */}
        <section className="pt-4">
          <MagicBar />
        </section>

        {/* Active Topics */}
        <section>
          <ActiveTopics topics={interests || []} />
        </section>

        {/* Manual Adds - Only visible when there are manual items */}
        <ManualAdds items={manualContent || []} />

        {/* Generate Button */}
        <div className="pt-4">
          <GenerateButton 
            pendingCount={pendingCount ?? 0} 
            hasTopics={hasTopics}
          />
        </div>

        <Separator className="opacity-30" />

        {/* Show Notes (when episode exists) */}
        {latestEpisode && sourcesData.length > 0 && (
          <section>
            <h2 className="font-serif text-xl font-medium mb-4">Notes du jour</h2>
            <ShowNotes 
              sources={sourcesData} 
              summary={latestEpisode.summary_text} 
            />
          </section>
        )}

        {/* Empty State - When no episode yet */}
        {!latestEpisode && (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-secondary/50 flex items-center justify-center">
              <span className="text-3xl">🎧</span>
            </div>
            <h2 className="font-serif text-xl font-medium mb-2">
              Votre premier Keernel
            </h2>
            <p className="text-muted-foreground text-sm max-w-sm mx-auto">
              Ajoutez des thèmes ou des liens, puis générez votre podcast personnalisé.
            </p>
          </div>
        )}
      </div>

      {/* Player Pod - Fixed at bottom */}
      {latestEpisode && (
        <PlayerPod episode={latestEpisode} />
      )}
    </>
  );
}
