import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Settings, User, Rss, Sliders, Clock, Bell } from "lucide-react";
import { ProfileForm } from "@/components/settings/profile-form";
import SignalMixer from "@/components/settings/signal-mixer";
import { FormatToggle } from "@/components/settings/format-toggle";
import { DangerZone } from "@/components/settings/danger-zone";
import { RssFeedLink } from "@/components/dashboard/rss-feed-link";
import NotificationSettings from "@/components/settings/notification-settings";

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

  // Fetch signal weights
  const { data: signalWeightsData } = await supabase
    .from("user_signal_weights")
    .select("weights")
    .eq("user_id", user.id)
    .single();

  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://singular.daily";

  return (
    <div className="max-w-2xl space-y-8">
      {/* Header - Premium style */}
      <div className="flex items-center gap-4">
        <div 
          className="w-14 h-14 rounded-2xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.15) 0%, rgba(0, 122, 255, 0.1) 100%)',
            boxShadow: '0 0 30px rgba(0, 240, 255, 0.15)',
          }}
        >
          <Settings className="w-7 h-7 text-[#00F0FF]" />
        </div>
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            Settings
          </h1>
          <p className="text-muted-foreground">
            Customize your Keernel experience
          </p>
        </div>
      </div>

      {/* Profile Info */}
      <Card className="bg-card/60 backdrop-blur-xl border-border/30 shadow-xl">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div 
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(0, 240, 255, 0.1)' }}
            >
              <User className="w-5 h-5 text-[#00F0FF]" />
            </div>
            <div>
              <CardTitle className="text-lg font-display">Your Profile</CardTitle>
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
          />
        </CardContent>
      </Card>

      {/* Format Toggle - Express / Deep Dive */}
      <Card className="bg-card/60 backdrop-blur-xl border-border/30 shadow-xl">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div 
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(0, 240, 255, 0.1)' }}
            >
              <Clock className="w-5 h-5 text-[#00F0FF]" />
            </div>
            <div>
              <CardTitle className="text-lg font-display">Format</CardTitle>
              <CardDescription>Choisissez la durée de votre briefing</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <FormatToggle 
            initialFormat={profile?.preferred_format || "digest"}
          />
        </CardContent>
      </Card>

      {/* Signal Mixer - Topic Weights */}
      <Card className="bg-card/60 backdrop-blur-xl border-border/30 shadow-xl">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div 
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(0, 240, 255, 0.1)' }}
            >
              <Sliders className="w-5 h-5 text-[#00F0FF]" />
            </div>
            <div>
              <CardTitle className="text-lg font-display">Signal Mixer</CardTitle>
              <CardDescription>Ajustez l'intensité de chaque thématique</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <SignalMixer 
            initialWeights={signalWeightsData?.weights || {}}
          />
        </CardContent>
      </Card>

      {/* Notifications */}
      <Card className="bg-card/60 backdrop-blur-xl border-border/30 shadow-xl">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div 
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(0, 240, 255, 0.1)' }}
            >
              <Bell className="w-5 h-5 text-[#00F0FF]" />
            </div>
            <div>
              <CardTitle className="text-lg font-display">Notifications</CardTitle>
              <CardDescription>Recevez une alerte quand votre podcast est prêt</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <NotificationSettings />
        </CardContent>
      </Card>

      {/* RSS Feed */}
      <Card className="bg-card/60 backdrop-blur-xl border-border/30 shadow-xl">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div 
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(0, 240, 255, 0.1)' }}
            >
              <Rss className="w-5 h-5 text-[#00F0FF]" />
            </div>
            <div>
              <CardTitle className="text-lg font-display">Podcast Feed</CardTitle>
              <CardDescription>Subscribe in your favorite podcast app</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <RssFeedLink 
            feedUrl={`${appUrl}/api/feed/${profile?.rss_token}`} 
          />
        </CardContent>
      </Card>

      <Separator className="bg-border/30" />

      {/* Danger Zone */}
      <DangerZone />
    </div>
  );
}
