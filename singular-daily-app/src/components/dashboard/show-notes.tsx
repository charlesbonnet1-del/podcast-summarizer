"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { 
  ChevronDown, 
  ChevronUp, 
  ExternalLink, 
  FileText,
  Link2
} from "lucide-react";

interface Source {
  title: string;
  url: string;
  domain: string;
}

interface ShowNotesProps {
  sources: Source[];
  summary?: string;
}

export function ShowNotes({ sources, summary }: ShowNotesProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <Card className="shadow-zen rounded-2xl border-border">
      <CardContent className="p-0">
        {/* Accordion header */}
        <Button
          variant="ghost"
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center justify-between p-4 h-auto rounded-2xl hover:bg-secondary/50"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <FileText className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-left">
              <p className="font-medium">Sources & Links</p>
              <p className="text-xs text-muted-foreground">
                {sources.length} source{sources.length > 1 ? "s" : ""} used
              </p>
            </div>
          </div>
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-muted-foreground" />
          ) : (
            <ChevronDown className="w-5 h-5 text-muted-foreground" />
          )}
        </Button>

        {/* Accordion content */}
        {isExpanded && (
          <div className="px-4 pb-4 space-y-3">
            {/* Summary */}
            {summary && (
              <div className="p-3 bg-secondary/50 rounded-xl text-sm text-muted-foreground">
                <p className="line-clamp-4">{summary}</p>
              </div>
            )}

            {/* Sources list */}
            <div className="space-y-2">
              {sources.map((source, index) => (
                <a
                  key={index}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start gap-3 p-3 rounded-xl bg-secondary/30 hover:bg-secondary/60 transition-colors group"
                >
                  <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Link2 className="w-4 h-4 text-blue-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm line-clamp-2 group-hover:text-primary transition-colors">
                      {source.title || source.domain}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {source.domain}
                    </p>
                  </div>
                  <ExternalLink className="w-4 h-4 text-muted-foreground flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                </a>
              ))}
            </div>

            {/* Go further */}
            <p className="text-xs text-center text-muted-foreground pt-2">
              Click any source to read the full content
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
