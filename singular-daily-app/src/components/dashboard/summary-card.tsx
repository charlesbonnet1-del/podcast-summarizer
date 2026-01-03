"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { 
  Star, 
  ExternalLink, 
  ChevronDown, 
  ChevronUp,
  Sparkles,
  TrendingUp,
  Globe,
  Cpu
} from "lucide-react";
import { cn } from "@/lib/utils";

// ============================================
// TYPES
// ============================================

interface Source {
  name: string;
  url: string;
  title?: string;
}

interface Summary {
  id: string;
  cluster_id: number;
  topic: string;
  title: string;
  summary_markdown: string;
  key_points: string[];
  why_it_matters: string;
  sources: Source[];
  article_count: number;
  generated_at: string;
  is_favorited?: boolean;
}

interface SummaryCardProps {
  summary: Summary;
  onToggleFavorite?: (summaryId: string) => void;
  variant?: "default" | "compact" | "pinned";
}

// ============================================
// TOPIC ICONS & COLORS
// ============================================

const TOPIC_CONFIG: Record<string, { icon: typeof Cpu; color: string; bg: string; label: string }> = {
  ia: { 
    icon: Cpu, 
    color: "text-violet-500", 
    bg: "bg-violet-500/10",
    label: "Intelligence Artificielle"
  },
  macro: { 
    icon: TrendingUp, 
    color: "text-emerald-500", 
    bg: "bg-emerald-500/10",
    label: "Macro & Géopolitique"
  },
  asia: { 
    icon: Globe, 
    color: "text-amber-500", 
    bg: "bg-amber-500/10",
    label: "Asie"
  },
};

// ============================================
// SUMMARY CARD COMPONENT
// ============================================

export function SummaryCard({ summary, onToggleFavorite, variant = "default" }: SummaryCardProps) {
  const [isExpanded, setIsExpanded] = useState(variant === "pinned");
  const [isFavorited, setIsFavorited] = useState(summary.is_favorited || false);
  
  const topicConfig = TOPIC_CONFIG[summary.topic] || TOPIC_CONFIG.ia;
  const TopicIcon = topicConfig.icon;
  
  const handleFavorite = () => {
    setIsFavorited(!isFavorited);
    onToggleFavorite?.(summary.id);
  };
  
  // Parse markdown for display (simple version)
  const parseMarkdown = (md: string) => {
    // Remove ## headers for cleaner display
    return md
      .replace(/^## .+$/gm, "")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" class="text-primary hover:underline">$1</a>')
      .trim();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "relative rounded-2xl border transition-all duration-200",
        variant === "pinned" 
          ? "bg-gradient-to-br from-amber-50/50 to-orange-50/50 dark:from-amber-950/20 dark:to-orange-950/20 border-amber-200/50 dark:border-amber-800/30"
          : "bg-card border-border hover:border-primary/20 hover:shadow-lg",
        "overflow-hidden"
      )}
    >
      {/* Pinned indicator */}
      {variant === "pinned" && (
        <div className="absolute top-0 right-0 px-3 py-1 bg-amber-500/10 rounded-bl-xl">
          <span className="text-xs font-medium text-amber-600 dark:text-amber-400 flex items-center gap-1">
            <Star className="w-3 h-3 fill-current" />
            Épinglé
          </span>
        </div>
      )}
      
      {/* Header */}
      <div className="p-5 pb-3">
        {/* Topic badge + Favorite button */}
        <div className="flex items-center justify-between mb-3">
          <div className={cn("flex items-center gap-2 px-3 py-1.5 rounded-full", topicConfig.bg)}>
            <TopicIcon className={cn("w-4 h-4", topicConfig.color)} />
            <span className={cn("text-xs font-medium", topicConfig.color)}>
              {topicConfig.label}
            </span>
          </div>
          
          <button
            onClick={handleFavorite}
            className={cn(
              "p-2 rounded-full transition-all",
              isFavorited 
                ? "bg-amber-100 dark:bg-amber-900/30 text-amber-500"
                : "hover:bg-muted text-muted-foreground hover:text-foreground"
            )}
          >
            <Star className={cn("w-4 h-4", isFavorited && "fill-current")} />
          </button>
        </div>
        
        {/* Title */}
        <h3 className="text-lg font-semibold text-foreground leading-tight mb-2">
          {summary.title}
        </h3>
        
        {/* Meta */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Sparkles className="w-3 h-3" />
            {summary.article_count} sources
          </span>
          <span>
            {new Date(summary.generated_at).toLocaleTimeString("fr-FR", { 
              hour: "2-digit", 
              minute: "2-digit" 
            })}
          </span>
        </div>
      </div>
      
      {/* Key Points (always visible) */}
      <div className="px-5 pb-3">
        <ul className="space-y-2">
          {summary.key_points.slice(0, isExpanded ? undefined : 2).map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-foreground/80">
              <span className={cn("mt-1.5 w-1.5 h-1.5 rounded-full shrink-0", topicConfig.bg.replace("/10", ""))} />
              <span>{point}</span>
            </li>
          ))}
        </ul>
        
        {summary.key_points.length > 2 && !isExpanded && (
          <p className="text-xs text-muted-foreground mt-2">
            +{summary.key_points.length - 2} autres points...
          </p>
        )}
      </div>
      
      {/* Expanded content */}
      {isExpanded && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="px-5 pb-4"
        >
          {/* Why it matters */}
          {summary.why_it_matters && (
            <div className="mt-3 p-3 rounded-xl bg-muted/50">
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Pourquoi c'est important
              </p>
              <p className="text-sm text-foreground/80">
                {summary.why_it_matters}
              </p>
            </div>
          )}
          
          {/* Sources */}
          <div className="mt-4">
            <p className="text-xs font-medium text-muted-foreground mb-2">
              Sources
            </p>
            <div className="flex flex-wrap gap-2">
              {summary.sources.map((source, i) => (
                <a
                  key={i}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-muted hover:bg-muted/80 rounded-full transition-colors group"
                >
                  <span className="font-medium">{source.name}</span>
                  <ExternalLink className="w-3 h-3 opacity-50 group-hover:opacity-100" />
                </a>
              ))}
            </div>
          </div>
        </motion.div>
      )}
      
      {/* Expand/Collapse button */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full py-3 flex items-center justify-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors border-t border-border/50"
      >
        {isExpanded ? (
          <>
            <ChevronUp className="w-4 h-4" />
            Réduire
          </>
        ) : (
          <>
            <ChevronDown className="w-4 h-4" />
            Voir plus
          </>
        )}
      </button>
    </motion.div>
  );
}

// ============================================
// SUMMARY CARD SKELETON
// ============================================

export function SummaryCardSkeleton() {
  return (
    <div className="rounded-2xl border bg-card p-5 animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="h-7 w-32 bg-muted rounded-full" />
        <div className="h-8 w-8 bg-muted rounded-full" />
      </div>
      <div className="h-6 w-3/4 bg-muted rounded mb-2" />
      <div className="h-4 w-1/4 bg-muted rounded mb-4" />
      <div className="space-y-2">
        <div className="h-4 w-full bg-muted rounded" />
        <div className="h-4 w-5/6 bg-muted rounded" />
      </div>
    </div>
  );
}
