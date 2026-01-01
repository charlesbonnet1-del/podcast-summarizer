import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // 1 minute max for text generation

const WORKER_URL = process.env.WORKER_URL;
const WORKER_SECRET = process.env.WORKER_SECRET || "";

// GET - Fetch queue and prompts
export async function GET(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const action = searchParams.get("action");

  if (!WORKER_URL) {
    return NextResponse.json({ error: "Worker not configured" }, { status: 500 });
  }

  try {
    if (action === "queue") {
      // Get articles in queue
      const response = await fetch(`${WORKER_URL}/prompt-lab/queue?user_id=${user.id}`, {
        headers: { "Authorization": `Bearer ${WORKER_SECRET}` }
      });
      const data = await response.json();
      return NextResponse.json(data);
    } 
    
    if (action === "prompts") {
      // Get prompts and topic intentions
      const response = await fetch(`${WORKER_URL}/prompt-lab/prompts`, {
        headers: { "Authorization": `Bearer ${WORKER_SECRET}` }
      });
      const data = await response.json();
      return NextResponse.json(data);
    }

    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  } catch (error) {
    console.error("Prompt lab GET error:", error);
    return NextResponse.json({ error: "Failed to fetch data" }, { status: 500 });
  }
}

// POST - Generate text or save prompts
export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (!WORKER_URL) {
    return NextResponse.json({ error: "Worker not configured" }, { status: 500 });
  }

  try {
    const body = await request.json();
    const action = body.action;

    if (action === "generate") {
      // Generate text only
      const response = await fetch(`${WORKER_URL}/prompt-lab/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${WORKER_SECRET}`
        },
        body: JSON.stringify({
          article_ids: body.article_ids,
          topic: body.topic,
          custom_prompt: body.custom_prompt,
          custom_intention: body.custom_intention,
          use_enrichment: body.use_enrichment
        })
      });
      const data = await response.json();
      return NextResponse.json(data);
    }

    if (action === "save") {
      // Save prompts/intentions
      const response = await fetch(`${WORKER_URL}/prompt-lab/prompts`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${WORKER_SECRET}`
        },
        body: JSON.stringify({
          prompt_name: body.prompt_name,
          prompt_content: body.prompt_content,
          topic_slug: body.topic_slug,
          topic_intention: body.topic_intention
        })
      });
      const data = await response.json();
      return NextResponse.json(data);
    }

    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  } catch (error) {
    console.error("Prompt lab POST error:", error);
    return NextResponse.json({ error: "Request failed" }, { status: 500 });
  }
}
