import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { 
  Bot, 
  Rss, 
  Clock, 
  Headphones,
  Plus
} from "lucide-react";
import { ConnectionCode } from "@/components/dashboard/connection-code";
import { RssFeedLink } from "@/components/dashboard/rss-feed-link";
import { ContentQueue } from "@/components/dashboard/content-queue";
import { TopicsManager } from "@/components/dashboard/topics-manager";
import { GenerateButton } from "@/components/dashboard/generate-button";
import { AddUrl } from "@/components/dashboard/add-url";
import { AudioPlayer } from "@/components/dashboard/audio-player";
import { ShowNotes } from "@/components/dashboard/show-notes";

// Force dynamic rendering - requires Supabase auth
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

  // Fetch latest episode (for player)
  const { data: latestEpisode } = await supabase
    .from("episodes")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(1)
    .single();

  // Fetch recent episodes count
  const { count: episodesCount } = await supabase
    .from("episodes")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user.id);

  // Fetch pending content
  const { data: pendingContent } = await supabase
    .from("content_queue")
    .select("*")
    .eq("user_id", user.id)
    .eq("status", "pending")
    .order("created_at", { ascending: false })
    .limit(20);

  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://singular.daily";

  // Parse sources_data safely
  const sourcesData = latestEpisode?.sources_data || [];

  return (
    <div className="space-y-8">
      {/* Welcome Header */}
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">
          Welcome back{profile?.email ? `, ${profile.email.split("@")[0]}` : ""}
        </h1>
        <p className="text-muted-foreground mt-1">
          Here&apos;s your personal podcast dashboard
        </p>
      </div>

      {/* Audio Player Section */}
      <section>
        <AudioPlayer episode={latestEpisode} />
        {latestEpisode && sourcesData.length > 0 && (
          <div className="mt-4">
            <ShowNotes 
              sources={sourcesData} 
              summary={latestEpisode.summary_text} 
            />
          </div>
        )}
      </section>

      <Separator />

      {/* Input Section - Topics & URL */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Add Content</h2>
        <div className="grid md:grid-cols-2 gap-6">
          {/* Topics Manager */}
          <TopicsManager />
          
          {/* Add URL */}
          <AddUrl />
        </div>
      </section>

      {/* Generate Button */}
      <GenerateButton pendingCount={pendingContent?.length ?? 0} />

      <Separator />

      {/* Content Queue */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold">Content Queue</h2>
            <p className="text-sm text-muted-foreground">
              {pendingContent?.length ?? 0} items waiting to be processed
            </p>
          </div>
        </div>
        <ContentQueue items={pendingContent ?? []} />
      </section>

      <Separator />

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard 
          label="Episodes" 
          value={episodesCount ?? 0} 
          icon={<Headphones className="w-4 h-4" />}
        />
        <StatCard 
          label="In Queue" 
          value={pendingContent?.length ?? 0}
          icon={<Plus className="w-4 h-4" />}
        />
        <StatCard 
          label="Duration" 
          value={`${profile?.default_duration ?? 15}min`}
          icon={<Clock className="w-4 h-4" />}
        />
        <StatCard 
          label="Plan" 
          value={profile?.subscription_status ?? "Free"}
          icon={<Badge variant="secondary" className="text-xs capitalize">{profile?.subscription_status ?? "free"}</Badge>}
          valueIsComponent
        />
      </div>

      <Separator />

      {/* Settings Row */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Telegram Connection */}
        <Card className="shadow-zen rounded-2xl border-border">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#0088cc]/10 flex items-center justify-center">
                <Bot className="w-5 h-5 text-[#0088cc]" />
              </div>
              <div>
                <CardTitle className="text-lg">Connect Telegram</CardTitle>
                <CardDescription>
                  Send content to your queue via bot
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <ConnectionCode 
              code={profile?.connection_code || "------"} 
              telegramConnected={!!profile?.telegram_chat_id}
            />
          </CardContent>
        </Card>

        {/* RSS Feed */}
        <Card className="shadow-zen rounded-2xl border-border">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
                <Rss className="w-5 h-5 text-orange-500" />
              </div>
              <div>
                <CardTitle className="text-lg">Your Podcast Feed</CardTitle>
                <CardDescription>
                  Add to any podcast app
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <RssFeedLink 
              feedUrl={`${appUrl}/api/feed/${profile?.rss_token}`} 
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatCard({ 
  label, 
  value, 
  icon,
  valueIsComponent = false
}: { 
  label: string; 
  value: string | number | React.ReactNode;
  icon: React.ReactNode;
  valueIsComponent?: boolean;
}) {
  return (
    <Card className="shadow-zen rounded-2xl border-border">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">{label}</span>
          <span className="text-muted-foreground">{icon}</span>
        </div>
        {valueIsComponent ? (
          value
        ) : (
          <p className="text-2xl font-semibold">{value}</p>
        )}
      </CardContent>
    </Card>
  );
}
