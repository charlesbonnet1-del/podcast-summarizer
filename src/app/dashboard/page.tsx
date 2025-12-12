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
import { EpisodesList } from "@/components/dashboard/episodes-list";
import { ContentQueue } from "@/components/dashboard/content-queue";

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

  // Fetch recent episodes
  const { data: episodes } = await supabase
    .from("episodes")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(5);

  // Fetch pending content
  const { data: pendingContent } = await supabase
    .from("content_queue")
    .select("*")
    .eq("user_id", user.id)
    .eq("status", "pending")
    .order("created_at", { ascending: false })
    .limit(10);

  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://singular.daily";

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

      {/* Quick Actions */}
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

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard 
          label="Episodes" 
          value={episodes?.length ?? 0} 
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

      {/* Content Queue */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold">Content Queue</h2>
            <p className="text-sm text-muted-foreground">
              Links waiting to be processed into your next episode
            </p>
          </div>
        </div>
        <ContentQueue items={pendingContent ?? []} />
      </section>

      <Separator />

      {/* Recent Episodes */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold">Recent Episodes</h2>
            <p className="text-sm text-muted-foreground">
              Your generated audio digests
            </p>
          </div>
        </div>
        <EpisodesList episodes={episodes ?? []} />
      </section>
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
