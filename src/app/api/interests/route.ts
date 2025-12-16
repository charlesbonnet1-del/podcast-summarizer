import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

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

  const body = await request.json();
  const keyword = body.keyword?.trim()?.toLowerCase();

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
    })
    .select()
    .single();

  if (error) {
    if (error.code === "23505") {
      // Duplicate key error
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

  if (!id) {
    return NextResponse.json({ error: "Missing topic ID" }, { status: 400 });
  }

  const { error } = await supabase
    .from("user_interests")
    .delete()
    .eq("id", id)
    .eq("user_id", user.id);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
