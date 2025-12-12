"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Play, Clock, Calendar, Headphones } from "lucide-react";
import type { Episode } from "@/lib/types/database";

interface EpisodesListProps {
  episodes: Episode[];
}

export function EpisodesList({ episodes }: EpisodesListProps) {
  if (episodes.length === 0) {
    return (
      <Card className="shadow-zen rounded-2xl border-border">
        <CardContent className="py-12 text-center">
          <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center mx-auto mb-4">
            <Headphones className="w-8 h-8 text-muted-foreground" />
          </div>
          <h3 className="font-medium mb-1">No episodes yet</h3>
          <p className="text-sm text-muted-foreground max-w-sm mx-auto">
            Add content to your queue via Telegram, then generate your first episode.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {episodes.map((episode) => (
        <EpisodeCard key={episode.id} episode={episode} />
      ))}
    </div>
  );
}

function EpisodeCard({ episode }: { episode: Episode }) {
  const date = new Date(episode.created_at);
  const formattedDate = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return "~15 min";
    const minutes = Math.floor(seconds / 60);
    return `${minutes} min`;
  };

  const sources = Array.isArray(episode.sources) ? episode.sources : [];

  return (
    <Card className="shadow-zen rounded-2xl border-border hover-lift">
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          {/* Play Button */}
          <Button
            size="icon"
            className="rounded-xl h-12 w-12 shrink-0"
            onClick={() => {
              const audio = new Audio(episode.audio_url);
              audio.play();
            }}
          >
            <Play className="w-5 h-5" />
          </Button>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <h3 className="font-medium truncate">{episode.title}</h3>
            {episode.summary_text && (
              <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                {episode.summary_text}
              </p>
            )}
            
            <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {formattedDate}
              </span>
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatDuration(episode.audio_duration)}
              </span>
              {sources.length > 0 && (
                <Badge variant="secondary" className="rounded-md text-xs">
                  {sources.length} source{sources.length > 1 ? "s" : ""}
                </Badge>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
