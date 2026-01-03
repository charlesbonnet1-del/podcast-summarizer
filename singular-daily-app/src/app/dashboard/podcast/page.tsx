import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { PodcastPlayer } from "@/components/dashboard/podcast-player";

// Force dynamic rendering
export const dynamic = 'force-dynamic';

export default async function PodcastPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  // Fetch latest episode
  const { data: latestEpisode } = await supabase
    .from("episodes")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(1)
    .single();

  // Fetch episode history (last 10)
  const { data: episodeHistory } = await supabase
    .from("episodes")
    .select("id, title, audio_url, audio_duration, created_at, sources_data")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(10);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-foreground">
          🎙️ Podcast
        </h1>
        <p className="text-muted-foreground">
          Écoutez votre briefing audio personnalisé
        </p>
      </div>

      {/* Player */}
      <PodcastPlayer 
        episode={latestEpisode}
        history={episodeHistory || []}
        userId={user.id}
      />
    </div>
  );
}
