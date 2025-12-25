"use client";

import { motion } from "framer-motion";
import { 
  ExternalLink, 
  User, 
  Calendar, 
  Lightbulb, 
  History,
  BookOpen
} from "lucide-react";

interface DigestCardProps {
  digest: {
    id: string;
    title: string;
    source_url: string;
    author?: string | null;
    published_date?: string | null;
    summary?: string | null;
    key_insights?: string[] | null;
    historical_context?: string | null;
    created_at: string;
    episodes?: {
      title: string;
      created_at: string;
    };
  };
  index?: number;
}

// Color palette for cards
const CARD_COLORS = [
  { bg: "bg-[#F5F0E8]", accent: "bg-[#E8DFD0]", text: "text-[#3D3D3D]", muted: "text-[#6B5B4F]" },
  { bg: "bg-[#FAFAFA]", accent: "bg-[#F0F0F0]", text: "text-[#2D2D2D]", muted: "text-[#7A7A7A]" },
  { bg: "bg-[#EDE8E0]", accent: "bg-[#DDD5C8]", text: "text-[#4A4A4A]", muted: "text-[#8B7355]" },
  { bg: "bg-[#F8F6F3]", accent: "bg-[#E5E0D8]", text: "text-[#3D3D3D]", muted: "text-[#9A8B7A]" },
];

export function DigestCard({ digest, index = 0 }: DigestCardProps) {
  const colors = CARD_COLORS[index % CARD_COLORS.length];
  const domain = new URL(digest.source_url).hostname.replace("www.", "");

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      year: "numeric"
    });
  };

  return (
    <motion.div
      className={`${colors.bg} rounded-2xl p-5 shadow-sm hover:shadow-md transition-all`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex-1 min-w-0">
          <h3 className={`font-medium ${colors.text} line-clamp-2 mb-1`}>
            {digest.title}
          </h3>
          <p className={`text-xs ${colors.muted} font-mono`}>{domain}</p>
        </div>
        <a
          href={digest.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`p-2 rounded-lg ${colors.accent} hover:opacity-80 transition-opacity flex-shrink-0`}
        >
          <ExternalLink className={`w-4 h-4 ${colors.text}`} />
        </a>
      </div>

      {/* Meta info */}
      <div className="flex flex-wrap gap-3 mb-4 text-xs">
        {digest.author && (
          <div className={`flex items-center gap-1.5 ${colors.muted}`}>
            <User className="w-3 h-3" />
            <span>{digest.author}</span>
          </div>
        )}
        {digest.published_date && (
          <div className={`flex items-center gap-1.5 ${colors.muted}`}>
            <Calendar className="w-3 h-3" />
            <span>{formatDate(digest.published_date)}</span>
          </div>
        )}
      </div>

      {/* Summary */}
      {digest.summary && (
        <div className="mb-4">
          <div className={`flex items-center gap-2 mb-2 ${colors.muted}`}>
            <BookOpen className="w-3.5 h-3.5" />
            <span className="text-xs font-medium uppercase tracking-wide">Résumé</span>
          </div>
          <p className={`text-sm ${colors.text} leading-relaxed`}>
            {digest.summary}
          </p>
        </div>
      )}

      {/* Key Insights */}
      {digest.key_insights && digest.key_insights.length > 0 && (
        <div className="mb-4">
          <div className={`flex items-center gap-2 mb-2 ${colors.muted}`}>
            <Lightbulb className="w-3.5 h-3.5" />
            <span className="text-xs font-medium uppercase tracking-wide">Points clés</span>
          </div>
          <ul className="space-y-1.5">
            {digest.key_insights.map((insight, i) => (
              <li 
                key={i} 
                className={`text-sm ${colors.text} flex items-start gap-2`}
              >
                <span className={`${colors.accent} w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0`} />
                {insight}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Historical Context */}
      {digest.historical_context && (
        <div className={`p-3 rounded-xl ${colors.accent}`}>
          <div className={`flex items-center gap-2 mb-1.5 ${colors.muted}`}>
            <History className="w-3.5 h-3.5" />
            <span className="text-xs font-medium uppercase tracking-wide">Contexte</span>
          </div>
          <p className={`text-sm ${colors.text}`}>
            {digest.historical_context}
          </p>
        </div>
      )}

      {/* Episode reference */}
      {digest.episodes && (
        <div className={`mt-4 pt-3 border-t border-black/5 text-xs ${colors.muted}`}>
          Épisode : {digest.episodes.title}
        </div>
      )}
    </motion.div>
  );
}
