import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

// Valid topic slugs (V19 - same as cluster_pipeline.py)
const VALID_TOPICS = [
  // Tech
  "ia", "cyber", "deep_tech",
  // Science
  "health", "space", "energy",
  // Economics
  "crypto", "macro", "deals",
  // World
  "asia", "regulation", "resources",
  // Influence
  "info", "attention", "persuasion",
  // General (requires authority validation)
  "general"
];

// GET - Retrieve user's selected topics
export async function GET() {
  const supabase = await createClient();

  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { data, error } = await supabase
      .from("users")
      .select("selected_topics, onboarding_completed")
      .eq("id", user.id)
      .single();

    if (error && error.code !== "PGRST116") {
      throw error;
    }

    return NextResponse.json({
      selectedTopics: data?.selected_topics || [],
      onboardingCompleted: data?.onboarding_completed || false
    });
  } catch (error) {
    console.error("Error fetching selected topics:", error);
    return NextResponse.json({ error: "Failed to fetch topics" }, { status: 500 });
  }
}

// POST - Save user's selected topics (minimum 5)
export async function POST(request: Request) {
  const supabase = await createClient();

  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { topics } = await request.json();

    if (!topics || !Array.isArray(topics)) {
      return NextResponse.json({ error: "Invalid topics format" }, { status: 400 });
    }

    // Validate minimum 5 topics
    if (topics.length < 5) {
      return NextResponse.json({
        error: "Minimum 5 topics required"
      }, { status: 400 });
    }

    // Validate all topics are valid slugs
    const invalidTopics = topics.filter((t: string) => !VALID_TOPICS.includes(t));
    if (invalidTopics.length > 0) {
      return NextResponse.json({
        error: `Invalid topics: ${invalidTopics.join(", ")}`
      }, { status: 400 });
    }

    // Save to users.selected_topics and mark onboarding complete
    const { error } = await supabase
      .from("users")
      .update({
        selected_topics: topics,
        onboarding_completed: true,
        updated_at: new Date().toISOString(),
      })
      .eq("id", user.id);

    if (error) throw error;

    return NextResponse.json({
      success: true,
      message: `${topics.length} topics saved`
    });
  } catch (error) {
    console.error("Error saving selected topics:", error);
    return NextResponse.json({ error: "Failed to save topics" }, { status: 500 });
  }
}
