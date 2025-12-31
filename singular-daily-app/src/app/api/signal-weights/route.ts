import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

// GET - Retrieve user's signal weights
export async function GET() {
  const supabase = await createClient();
  
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    // V14.5: Read from users.topic_weights (not separate table)
    const { data, error } = await supabase
      .from("users")
      .select("topic_weights")
      .eq("id", user.id)
      .single();

    if (error && error.code !== "PGRST116") {
      throw error;
    }

    // Return weights or empty object if not found
    return NextResponse.json({ 
      weights: data?.topic_weights || {} 
    });
  } catch (error) {
    console.error("Error fetching signal weights:", error);
    return NextResponse.json({ error: "Failed to fetch weights" }, { status: 500 });
  }
}

// POST - Save user's signal weights
export async function POST(request: Request) {
  const supabase = await createClient();
  
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { weights } = await request.json();

    if (!weights || typeof weights !== "object") {
      return NextResponse.json({ error: "Invalid weights format" }, { status: 400 });
    }

    // Validate weights are numbers between 0-100
    for (const [key, value] of Object.entries(weights)) {
      if (typeof value !== "number" || value < 0 || value > 100) {
        return NextResponse.json({ 
          error: `Invalid weight for ${key}: must be 0-100` 
        }, { status: 400 });
      }
    }

    // V14.5: Save to users.topic_weights (not separate table)
    const { error } = await supabase
      .from("users")
      .update({
        topic_weights: weights,
        updated_at: new Date().toISOString(),
      })
      .eq("id", user.id);

    if (error) throw error;

    // Also sync user_interests to ensure all topics are tracked
    const topicIds = Object.keys(weights);
    for (const topicId of topicIds) {
      await supabase
        .from("user_interests")
        .upsert({
          user_id: user.id,
          keyword: topicId,
          display_name: topicId, // Will be overwritten if exists
        }, {
          onConflict: "user_id,keyword",
          ignoreDuplicates: true
        });
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error saving signal weights:", error);
    return NextResponse.json({ error: "Failed to save weights" }, { status: 500 });
  }
}
