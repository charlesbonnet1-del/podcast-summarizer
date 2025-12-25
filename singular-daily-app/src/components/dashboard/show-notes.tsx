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

// Elegant color palette for sources - alternating warm neutrals
const SOURCE_COLORS = [
  { bg: "bg-[#F5F0E8]", icon: "bg-[#E8DFD0]", text: "text-[#3D3D3D]" },      // Beige / Cream
  { bg: "bg-[#FAFAFA]", icon: "bg-[#F0F0F0]", text: "text-[#2D2D2D]" },      // White / Light gray
  { bg: "bg-[#EDE8E0]", icon: "bg-[#DDD5C8]", text: "text-[#4A4A4A]" },      // Sand / Taupe
  { bg: "bg-[#F8F6F3]", icon: "bg-[#E5E0D8]", text: "text-[#3D3D3D]" },      // Off-white / Cream
  { bg: "bg-[#2D2D2D]", icon: "bg-[#404040]", text: "text-[#F5F5F5]" },      // Charcoal
  { bg: "bg-[#1A1A1A]", icon: "bg-[#333333]", text: "text-[#FFFFFF]" },      // Noir / Black
];

export function ShowNotes({ sources, summary }: ShowNotesProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!sources || sources.length === 0) {
    return null;
  }

  const getSourceColor = (index: number) => {
    return SOURCE_COLORS[index % SOURCE_COLORS.length];
  };

  return (
    <Card className="shadow-zen rounded-2xl border-border bg-[#FAF9F7]">
      <CardContent className="p-0">
        {/* Accordion header */}
        <Button
          variant="ghost"
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center justify-between p-4 h-auto rounded-2xl hover:bg-[#F0EDE8]"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#E8DFD0] flex items-center justify-center">
              <FileText className="w-4 h-4 text-[#6B5B4F]" />
            </div>
            <div className="text-left">
              <p className="font-medium text-[#2D2D2D]">Sources & Links</p>
              <p className="text-xs text-[#6B6B6B]">
                {sources.length} source{sources.length > 1 ? "s" : ""} used
              </p>
            </div>
          </div>
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-[#6B6B6B]" />
          ) : (
            <ChevronDown className="w-5 h-5 text-[#6B6B6B]" />
          )}
        </Button>

        {/* Accordion content */}
        {isExpanded && (
          <div className="px-4 pb-4 space-y-3">
            {/* Summary */}
            {summary && (
              <div className="p-3 bg-[#F0EDE8] rounded-xl text-sm text-[#4A4A4A]">
                <p className="line-clamp-4">{summary}</p>
              </div>
            )}

            {/* Sources list */}
            <div className="space-y-2">
              {sources.map((source, index) => {
                const colors = getSourceColor(index);
                return (
                  <a
                    key={index}
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`flex items-start gap-3 p-3 rounded-xl ${colors.bg} hover:opacity-90 transition-all group shadow-sm`}
                  >
                    <div className={`w-8 h-8 rounded-lg ${colors.icon} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                      <Link2 className={`w-4 h-4 ${colors.text}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`font-medium text-sm line-clamp-2 ${colors.text} transition-colors`}>
                        {source.title || source.domain}
                      </p>
                      <p className={`text-xs mt-0.5 ${colors.text} opacity-60`}>
                        {source.domain}
                      </p>
                    </div>
                    <ExternalLink className={`w-4 h-4 ${colors.text} flex-shrink-0 opacity-0 group-hover:opacity-60 transition-opacity`} />
                  </a>
                );
              })}
            </div>

            {/* Go further */}
            <p className="text-xs text-center text-[#8B8B8B] pt-2">
              Click any source to read the full content
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
