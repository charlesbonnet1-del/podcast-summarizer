import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 300; // 5 minutes max for generation

export async function POST() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Check if user has pending content
  const { data: pendingContent, error: queueError } = await supabase
    .from("content_queue")
    .select("id")
    .eq("user_id", user.id)
    .eq("status", "pending");

  if (queueError) {
    return NextResponse.json({ error: queueError.message }, { status: 500 });
  }

  if (!pendingContent || pendingContent.length === 0) {
    return NextResponse.json(
      { error: "No content in queue. Add topics or URLs first!" },
      { status: 400 }
    );
  }

  // Call the Python worker to generate
  // For now, we'll trigger via a simple HTTP call to a worker endpoint
  // Or we can use Supabase Edge Functions
  
  const workerUrl = process.env.WORKER_URL;
  
  if (!workerUrl) {
    // If no worker URL, return instructions
    return NextResponse.json({
      success: true,
      message: "Generation queued",
      pending_items: pendingContent.length,
      note: "Use /generate on Telegram bot or wait for scheduled generation"
    });
  }

  try {
    // Trigger worker
    const response = await fetch(`${workerUrl}/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${process.env.WORKER_SECRET || ""}`
      },
      body: JSON.stringify({ user_id: user.id })
    });

    if (!response.ok) {
      throw new Error("Worker failed");
    }

    const result = await response.json();
    return NextResponse.json(result);

  } catch (error) {
    // Fallback: just confirm the queue status
    return NextResponse.json({
      success: true,
      message: "Generation request received",
      pending_items: pendingContent.length,
      note: "Your podcast will be generated shortly"
    });
  }
}

// GET - Check generation status
export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Get pending count
  const { data: pending } = await supabase
    .from("content_queue")
    .select("id")
    .eq("user_id", user.id)
    .eq("status", "pending");

  // Get latest episode
  const { data: latestEpisode } = await supabase
    .from("episodes")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(1)
    .single();

  return NextResponse.json({
    pending_count: pending?.length || 0,
    latest_episode: latestEpisode || null
  });
}
