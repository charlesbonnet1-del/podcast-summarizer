import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { IntelligenceFeed } from "@/components/dashboard/intelligence-feed";

// Force dynamic rendering
export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  // Fetch user's favorites
  const { data: favoritesData } = await supabase
    .from("user_favorites")
    .select("item_id")
    .eq("user_id", user.id)
    .eq("item_type", "summary");

  const favoriteIds = favoritesData?.map(f => f.item_id) || [];

  // We'll fetch summaries client-side to keep the page fast
  // The IntelligenceFeed component will fetch from the backend

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-foreground">
          Bonjour 👋
        </h1>
        <p className="text-muted-foreground">
          Voici votre briefing intelligence du {new Date().toLocaleDateString("fr-FR", { 
            weekday: "long", 
            day: "numeric", 
            month: "long" 
          })}
        </p>
      </div>

      {/* Intelligence Feed */}
      <IntelligenceFeed 
        userId={user.id}
        initialFavorites={favoriteIds}
      />
    </div>
  );
}
