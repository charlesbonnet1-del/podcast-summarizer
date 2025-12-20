import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Settings, Volume2, User, Rss } from "lucide-react";
import { SettingsForm } from "@/components/settings/settings-form";
import { ProfileForm } from "@/components/settings/profile-form";
import { DangerZone } from "@/components/settings/danger-zone";
import { RssFeedLink } from "@/components/dashboard/rss-feed-link";

// Force dynamic rendering - requires Supabase auth
export const dynamic = 'force-dynamic';

export default async function SettingsPage() {
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

  const settings = profile?.settings || {};
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://singular.daily";

  return (
    <div className="max-w-2xl space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
          <Settings className="w-8 h-8" />
          Settings
        </h1>
        <p className="text-muted-foreground mt-1">
          Customize your podcast experience
        </p>
      </div>

      {/* Profile Info */}
      <Card className="shadow-zen rounded-2xl border-border">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center">
              <User className="w-5 h-5" />
            </div>
            <div>
              <CardTitle className="text-lg">Your Profile</CardTitle>
              <CardDescription>Personalize your podcast greeting</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <ProfileForm 
            email={user.email || ""}
            firstName={profile?.first_name || ""}
            lastName={profile?.last_name || ""}
            memberSince={profile?.created_at}
            plan={profile?.subscription_status || "free"}
            includeInternational={profile?.include_international || false}
            selectedVerticals={profile?.selected_verticals || {
              ai_tech: true,
              politics: true,
              finance: true,
              science: true,
              culture: true
            }}
          />
        </CardContent>
      </Card>

      {/* Podcast Settings */}
      <Card className="shadow-zen rounded-2xl border-border">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center">
              <Volume2 className="w-5 h-5" />
            </div>
            <div>
              <CardTitle className="text-lg">Podcast Preferences</CardTitle>
              <CardDescription>Configure your audio digest settings</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <SettingsForm 
            targetDuration={profile?.target_duration ?? 20}
            voiceId={settings.voice_id ?? "alloy"}
          />
        </CardContent>
      </Card>

      {/* RSS Feed */}
      <Card className="shadow-zen rounded-2xl border-border">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
              <Rss className="w-5 h-5 text-orange-500" />
            </div>
            <div>
              <CardTitle className="text-lg">Podcast Feed</CardTitle>
              <CardDescription>Subscribe in your favorite podcast app</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <RssFeedLink 
            feedUrl={`${appUrl}/api/feed/${profile?.rss_token}`} 
          />
          <p className="text-xs text-muted-foreground mt-4">
            Coming soon: Direct links for Spotify, Deezer, Apple Podcasts...
          </p>
        </CardContent>
      </Card>

      <Separator />

      {/* Danger Zone */}
      <DangerZone />
    </div>
  );
}
