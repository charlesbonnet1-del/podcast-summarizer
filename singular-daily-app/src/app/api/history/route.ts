import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const period = searchParams.get("period") || "week"; // week, month, all
    const limit = parseInt(searchParams.get("limit") || "10");

    let query = supabase
      .from("episodes")
      .select("id, title, audio_url, audio_duration, sources_data, report_url, created_at")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .limit(limit);

    // Filter by period
    if (period === "week") {
      const weekAgo = new Date();
      weekAgo.setDate(weekAgo.getDate() - 7);
      query = query.gte("created_at", weekAgo.toISOString());
    } else if (period === "month") {
      const monthAgo = new Date();
      monthAgo.setMonth(monthAgo.getMonth() - 1);
      query = query.gte("created_at", monthAgo.toISOString());
    }

    const { data: episodes, error } = await query;

    if (error) {
      console.error("Failed to fetch history:", error);
      return NextResponse.json({ error: "Failed to fetch history" }, { status: 500 });
    }

    // Format response
    const history = episodes?.map(ep => ({
      id: ep.id,
      title: ep.title,
      audioUrl: ep.audio_url,
      duration: ep.audio_duration,
      sourcesCount: ep.sources_data?.length || 0,
      reportUrl: ep.report_url,
      createdAt: ep.created_at,
      date: new Date(ep.created_at).toLocaleDateString('fr-FR', {
        weekday: 'short',
        day: 'numeric',
        month: 'short'
      })
    })) || [];

    return NextResponse.json({ history });

  } catch (error) {
    console.error("History API error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
