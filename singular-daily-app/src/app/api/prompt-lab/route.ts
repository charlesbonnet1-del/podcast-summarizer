import { NextRequest, NextResponse } from "next/server";

const WORKER_URL = process.env.WORKER_URL || "https://podcast-summarizeredaily-bot.onrender.com";
const WORKER_SECRET = process.env.WORKER_SECRET || "";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const action = searchParams.get("action");

  try {
    let endpoint = "/prompt-lab/queue";
    if (action === "prompts") {
      endpoint = "/prompt-lab/prompts";
    }

    const res = await fetch(`${WORKER_URL}${endpoint}`, {
      headers: {
        "Authorization": `Bearer ${WORKER_SECRET}`,
      },
    });

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Prompt lab GET error:", error);
    return NextResponse.json({ error: "Failed to fetch" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const action = body.action;

    let endpoint = "/prompt-lab/generate";
    let payload: Record<string, unknown> = body;

    if (action === "save") {
      endpoint = "/prompt-lab/prompts";
      payload = {
        prompt_name: body.prompt_name,
        prompt_content: body.prompt_content,
        topic_slug: body.topic_slug,
        topic_intention: body.topic_intention,
      };
    } else if (action === "generate") {
      endpoint = "/prompt-lab/generate";
      payload = {
        article_ids: body.article_ids,
        articles: body.articles,
        topic: body.topic,
        custom_prompt: body.custom_prompt,
        custom_intention: body.custom_intention,
        use_enrichment: body.use_enrichment,
      };
    } else if (action === "fill-queue") {
      endpoint = "/cron/fill-queue";
      payload = {};
    }

    const res = await fetch(`${WORKER_URL}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${WORKER_SECRET}`,
      },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Prompt lab POST error:", error);
    return NextResponse.json({ error: "Failed to process" }, { status: 500 });
  }
}
