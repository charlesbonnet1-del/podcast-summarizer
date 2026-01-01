import { NextRequest, NextResponse } from "next/server";

const WORKER_URL = process.env.WORKER_URL || "https://podcast-summarizeredaily-bot.onrender.com";
const WORKER_SECRET = process.env.WORKER_SECRET || "";

export async function GET() {
  try {
    const res = await fetch(`${WORKER_URL}/pipeline-lab/params`, {
      headers: {
        "Authorization": `Bearer ${WORKER_SECRET}`,
      },
    });

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Pipeline lab GET error:", error);
    return NextResponse.json({ error: "Failed to fetch params" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const action = body.action;

    let endpoint = "/pipeline-lab/run";
    let payload: Record<string, unknown> = body;

    switch (action) {
      case "fetch":
        endpoint = "/pipeline-lab/fetch";
        payload = {
          params: body.params,
          topics: body.topics,
        };
        break;

      case "cluster":
        endpoint = "/pipeline-lab/cluster";
        payload = {
          articles: body.articles,
          params: body.params,
        };
        break;

      case "select":
        endpoint = "/pipeline-lab/select";
        payload = {
          clusters: body.clusters,
          articles: body.articles,
          params: body.params,
          format: body.format,
        };
        break;

      case "run":
        endpoint = "/pipeline-lab/run";
        payload = {
          params: body.params,
          format: body.format,
          topics: body.topics,
        };
        break;

      case "generate-script":
        endpoint = "/pipeline-lab/generate-script";
        payload = {
          segments: body.segments,
          format: body.format,
          prompt_id: body.prompt_id,
        };
        break;

      default:
        return NextResponse.json({ error: "Invalid action" }, { status: 400 });
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
    console.error("Pipeline lab POST error:", error);
    return NextResponse.json({ error: "Failed to process" }, { status: 500 });
  }
}
