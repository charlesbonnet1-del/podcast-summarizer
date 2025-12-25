import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const supabase = await createClient();
  
  const { searchParams } = new URL(request.url);
  const episodeId = searchParams.get("episode_id");
  const limit = parseInt(searchParams.get("limit") || "50");
  const offset = parseInt(searchParams.get("offset") || "0");
  const search = searchParams.get("search") || "";

  try {
    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    let query = supabase
      .from("episode_digests")
      .select(`
        id,
        episode_id,
        source_url,
        title,
        author,
        published_date,
        summary,
        key_insights,
        historical_context,
        created_at,
        episodes!inner(user_id, title, created_at)
      `)
      .eq("episodes.user_id", user.id)
      .order("created_at", { ascending: false });

    // Filter by episode if provided
    if (episodeId) {
      query = query.eq("episode_id", episodeId);
    }

    // Search in title or summary
    if (search) {
      query = query.or(`title.ilike.%${search}%,summary.ilike.%${search}%`);
    }

    // Pagination
    query = query.range(offset, offset + limit - 1);

    const { data, error } = await query;

    if (error) {
      console.error("Error fetching digests:", error);
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ digests: data || [] });

  } catch (error) {
    console.error("Digests API error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
