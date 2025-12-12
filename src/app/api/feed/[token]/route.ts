import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ token: string }> }
) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!supabaseUrl || !supabaseServiceKey) {
    return new NextResponse("Server configuration error", { status: 500 });
  }

  // Use service role for public RSS feed access
  const supabase = createClient(supabaseUrl, supabaseServiceKey);

  const { token } = await params;

  // Find user by RSS token
  const { data: user, error: userError } = await supabase
    .from("users")
    .select("id, email")
    .eq("rss_token", token)
    .single();

  if (userError || !user) {
    return new NextResponse("Feed not found", { status: 404 });
  }

  // Fetch user's episodes
  const { data: episodes, error: episodesError } = await supabase
    .from("episodes")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(50);

  if (episodesError) {
    return new NextResponse("Error fetching episodes", { status: 500 });
  }

  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://singular.daily";
  const feedUrl = `${appUrl}/api/feed/${token}`;

  // Generate RSS XML
  const rss = generateRSS({
    title: `Singular Daily - ${user.email?.split("@")[0]}'s Digest`,
    description: "Your personalized AI-generated audio digest",
    feedUrl,
    siteUrl: appUrl,
    episodes: episodes || [],
  });

  return new NextResponse(rss, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=300", // Cache for 5 minutes
    },
  });
}

interface RSSOptions {
  title: string;
  description: string;
  feedUrl: string;
  siteUrl: string;
  episodes: Array<{
    id: string;
    title: string;
    summary_text: string | null;
    audio_url: string;
    audio_duration: number | null;
    created_at: string;
  }>;
}

function generateRSS(options: RSSOptions): string {
  const { title, description, feedUrl, siteUrl, episodes } = options;

  const escapeXml = (str: string): string => {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;");
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toUTCString();
  };

  const formatDuration = (seconds: number | null): string => {
    if (!seconds) return "00:15:00";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours.toString().padStart(2, "0")}:${minutes
      .toString()
      .padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const items = episodes
    .map(
      (episode) => `
    <item>
      <title>${escapeXml(episode.title)}</title>
      <description><![CDATA[${episode.summary_text || "Your daily audio digest"}]]></description>
      <pubDate>${formatDate(episode.created_at)}</pubDate>
      <enclosure url="${escapeXml(episode.audio_url)}" type="audio/mpeg" length="0"/>
      <guid isPermaLink="false">${episode.id}</guid>
      <itunes:duration>${formatDuration(episode.audio_duration)}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>`
    )
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${escapeXml(title)}</title>
    <description>${escapeXml(description)}</description>
    <link>${escapeXml(siteUrl)}</link>
    <atom:link href="${escapeXml(feedUrl)}" rel="self" type="application/rss+xml"/>
    <language>en-us</language>
    <itunes:author>Singular Daily</itunes:author>
    <itunes:summary>${escapeXml(description)}</itunes:summary>
    <itunes:type>episodic</itunes:type>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Technology"/>
    <itunes:image href="${siteUrl}/podcast-cover.png"/>
    ${items}
  </channel>
</rss>`;
}
