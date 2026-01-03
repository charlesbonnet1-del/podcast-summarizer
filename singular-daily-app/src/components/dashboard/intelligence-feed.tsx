"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  RefreshCw, 
  Calendar,
  Filter,
  Cpu,
  TrendingUp,
  Globe,
  Loader2,
  Inbox,
  Zap
} from "lucide-react";
import { SummaryCard, SummaryCardSkeleton } from "./summary-card";
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

interface IntelligenceFeedProps {
  userId: string;
  initialSummaries?: Summary[];
  initialFavorites?: string[];
}

// ============================================
// TOPIC FILTERS
// ============================================

const TOPICS = [
  { id: "all", label: "Tout", icon: null },
  { id: "ia", label: "IA", icon: Cpu },
  { id: "macro", label: "Macro", icon: TrendingUp },
  { id: "asia", label: "Asie", icon: Globe },
];

// ============================================
// INTELLIGENCE FEED COMPONENT
// ============================================

export function IntelligenceFeed({ 
  userId, 
  initialSummaries = [],
  initialFavorites = []
}: IntelligenceFeedProps) {
  const [summaries, setSummaries] = useState<Summary[]>(initialSummaries);
  const [favorites, setFavorites] = useState<Set<string>>(new Set(initialFavorites));
  const [selectedTopic, setSelectedTopic] = useState("all");
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Fetch summaries on mount if none provided
  useEffect(() => {
    if (initialSummaries.length === 0) {
      fetchSummaries();
    } else {
      setLastUpdated(new Date());
    }
  }, []);

  const fetchSummaries = async () => {
    setIsLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
      const response = await fetch(`${backendUrl}/api/intelligence/today?topics=ia,macro,asia`);
      const data = await response.json();
      
      if (data.success && data.summaries) {
        // Mark favorites
        const summariesWithFavorites = data.summaries.map((s: Summary) => ({
          ...s,
          is_favorited: favorites.has(s.id)
        }));
        setSummaries(summariesWithFavorites);
        setLastUpdated(new Date());
      }
    } catch (error) {
      console.error("Failed to fetch summaries:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // DEV ONLY: Trigger the CRON manually
  const handleManualFetch = async () => {
    setIsFetching(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
      const response = await fetch(`${backendUrl}/cron/daily?topics=ia,macro,asia&dry_run=false`);
      const data = await response.json();
      
      if (data.success) {
        console.log("CRON results:", data.results);
        // Wait a bit then refresh summaries
        setTimeout(() => {
          fetchSummaries();
        }, 1000);
      } else {
        console.error("CRON failed:", data.error);
      }
    } catch (error) {
      console.error("Failed to trigger CRON:", error);
    } finally {
      setIsFetching(false);
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchSummaries();
    setIsRefreshing(false);
  };

  const handleToggleFavorite = async (summaryId: string) => {
    // Optimistic update
    const newFavorites = new Set(favorites);
    if (newFavorites.has(summaryId)) {
      newFavorites.delete(summaryId);
    } else {
      newFavorites.add(summaryId);
    }
    setFavorites(newFavorites);

    // Update summaries
    setSummaries(prev => prev.map(s => ({
      ...s,
      is_favorited: newFavorites.has(s.id)
    })));

    // API call
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
      await fetch(`${backendUrl}/api/favorites/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          item_type: "summary",
          item_id: summaryId
        })
      });
    } catch (error) {
      console.error("Failed to toggle favorite:", error);
      // Revert on error
      setFavorites(favorites);
    }
  };

  // Filter summaries
  const filteredSummaries = selectedTopic === "all" 
    ? summaries 
    : summaries.filter(s => s.topic === selectedTopic);

  // Separate pinned (favorited) and regular
  const pinnedSummaries = filteredSummaries.filter(s => s.is_favorited);
  const regularSummaries = filteredSummaries.filter(s => !s.is_favorited);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">
            Intelligence du jour
          </h2>
          {lastUpdated && (
            <p className="text-sm text-muted-foreground mt-1">
              Mis à jour à {lastUpdated.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
            </p>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {/* DEV ONLY: Manual fetch button */}
          <button
            onClick={handleManualFetch}
            disabled={isFetching}
            className="flex items-center gap-2 px-3 py-2 text-xs font-medium text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30 hover:bg-orange-200 dark:hover:bg-orange-900/50 rounded-full transition-all disabled:opacity-50"
            title="Dev only - Trigger CRON"
          >
            {isFetching ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                Fetching...
              </>
            ) : (
              <>
                <Zap className="w-3 h-3" />
                Fetch Now
              </>
            )}
          </button>
          
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground bg-muted/50 hover:bg-muted rounded-full transition-all disabled:opacity-50"
          >
            <RefreshCw className={cn("w-4 h-4", isRefreshing && "animate-spin")} />
            Actualiser
          </button>
        </div>
      </div>

      {/* Topic filters */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {TOPICS.map((topic) => {
          const Icon = topic.icon;
          const isSelected = selectedTopic === topic.id;
          const count = topic.id === "all" 
            ? summaries.length 
            : summaries.filter(s => s.topic === topic.id).length;
          
          return (
            <button
              key={topic.id}
              onClick={() => setSelectedTopic(topic.id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all whitespace-nowrap",
                isSelected
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {Icon && <Icon className="w-4 h-4" />}
              {topic.label}
              <span className={cn(
                "px-1.5 py-0.5 text-xs rounded-full",
                isSelected ? "bg-primary-foreground/20" : "bg-background"
              )}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2">
          <SummaryCardSkeleton />
          <SummaryCardSkeleton />
          <SummaryCardSkeleton />
        </div>
      )}

      {/* Empty state */}
      {!isLoading && filteredSummaries.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
            <Inbox className="w-8 h-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-medium text-foreground mb-1">
            Pas encore de briefings
          </h3>
          <p className="text-sm text-muted-foreground max-w-sm">
            Les briefings sont générés chaque matin à 6h. Revenez demain pour découvrir les dernières actualités.
          </p>
        </div>
      )}

      {/* Pinned summaries */}
      {pinnedSummaries.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <span className="w-1 h-4 bg-amber-500 rounded-full" />
            Épinglés
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            <AnimatePresence mode="popLayout">
              {pinnedSummaries.map((summary) => (
                <SummaryCard
                  key={summary.id}
                  summary={summary}
                  onToggleFavorite={handleToggleFavorite}
                  variant="pinned"
                />
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Regular summaries */}
      {regularSummaries.length > 0 && (
        <div className="space-y-3">
          {pinnedSummaries.length > 0 && (
            <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <span className="w-1 h-4 bg-primary rounded-full" />
              Aujourd'hui
            </h3>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            <AnimatePresence mode="popLayout">
              {regularSummaries.map((summary) => (
                <SummaryCard
                  key={summary.id}
                  summary={summary}
                  onToggleFavorite={handleToggleFavorite}
                />
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}
    </div>
  );
}
