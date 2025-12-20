import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const MAX_TOPICS_FREE = 4;
const MAX_TOPICS_PRO = 20;

// GET - Récupérer les topics de l'utilisateur
export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("user_interests")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ interests: data });
}

// POST - Ajouter un topic
export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Get user plan
  const { data: profile } = await supabase
    .from("users")
    .select("subscription_status")
    .eq("id", user.id)
    .single();

  const plan = profile?.subscription_status || "free";
  const maxTopics = plan === "pro" ? MAX_TOPICS_PRO : MAX_TOPICS_FREE;

  // Count current topics
  const { count } = await supabase
    .from("user_interests")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user.id);

  if ((count ?? 0) >= maxTopics) {
    return NextResponse.json(
      { error: `Limite de ${maxTopics} thèmes atteinte pour le plan ${plan}` },
      { status: 403 }
    );
  }

  const body = await request.json();
  const keyword = body.keyword?.trim()?.toLowerCase();
  const displayName = body.display_name || keyword;
  const searchKeywords = body.search_keywords || [keyword];

  if (!keyword || keyword.length < 2) {
    return NextResponse.json(
      { error: "Topic must be at least 2 characters" },
      { status: 400 }
    );
  }

  if (keyword.length > 50) {
    return NextResponse.json(
      { error: "Topic must be less than 50 characters" },
      { status: 400 }
    );
  }

  const { data, error } = await supabase
    .from("user_interests")
    .insert({
      user_id: user.id,
      keyword: keyword,
      display_name: displayName,
      search_keywords: searchKeywords,
    })
    .select()
    .single();

  if (error) {
    if (error.code === "23505") {
      return NextResponse.json(
        { error: "You're already following this topic" },
        { status: 409 }
      );
    }
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ interest: data }, { status: 201 });
}

// DELETE - Supprimer un topic
export async function DELETE(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const id = searchParams.get("id");
  const keyword = searchParams.get("keyword");

  // Support delete by ID or by keyword
  if (!id && !keyword) {
    return NextResponse.json({ error: "Missing topic ID or keyword" }, { status: 400 });
  }

  let query = supabase
    .from("user_interests")
    .delete()
    .eq("user_id", user.id);

  if (id) {
    query = query.eq("id", id);
  } else if (keyword) {
    query = query.eq("keyword", keyword);
  }

  const { error } = await query;

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
