"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Calendar, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { SummaryCard, SummaryCardSkeleton } from "@/components/dashboard/summary-card";
import { cn } from "@/lib/utils";

// Force dynamic rendering
export const dynamic = 'force-dynamic';

interface ArchiveDate {
  date: string;
  summary_count: number;
  topics: string[];
}

interface Summary {
  id: string;
  cluster_id: number;
  topic: string;
  title: string;
  summary_markdown: string;
  key_points: string[];
  why_it_matters: string;
  sources: { name: string; url: string; title?: string }[];
  article_count: number;
  generated_at: string;
}

export default function ArchivePage() {
  const [dates, setDates] = useState<ArchiveDate[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [isLoadingDates, setIsLoadingDates] = useState(true);
  const [isLoadingSummaries, setIsLoadingSummaries] = useState(false);

  // Fetch available dates on mount
  useEffect(() => {
    fetchDates();
  }, []);

  const fetchDates = async () => {
    setIsLoadingDates(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
      const response = await fetch(`${backendUrl}/api/intelligence/archive?limit=30`);
      const data = await response.json();
      
      if (data.success && data.dates) {
        setDates(data.dates);
        // Auto-select first date if available
        if (data.dates.length > 0) {
          setSelectedDate(data.dates[0].date);
          fetchSummariesForDate(data.dates[0].date);
        }
      }
    } catch (error) {
      console.error("Failed to fetch archive dates:", error);
    } finally {
      setIsLoadingDates(false);
    }
  };

  const fetchSummariesForDate = async (date: string) => {
    setIsLoadingSummaries(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
      const response = await fetch(`${backendUrl}/api/intelligence/archive?date=${date}`);
      const data = await response.json();
      
      if (data.success && data.summaries) {
        setSummaries(data.summaries);
      }
    } catch (error) {
      console.error("Failed to fetch summaries:", error);
    } finally {
      setIsLoadingSummaries(false);
    }
  };

  const handleDateSelect = (date: string) => {
    setSelectedDate(date);
    fetchSummariesForDate(date);
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("fr-FR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric"
    });
  };

  const formatShortDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short"
    });
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-foreground flex items-center gap-3">
          <Calendar className="w-8 h-8 text-primary" />
          Archive
        </h1>
        <p className="text-muted-foreground">
          Retrouvez vos briefings passés
        </p>
      </div>

      {/* Date selector */}
      <div className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground">
          Sélectionnez une date
        </h2>
        
        {isLoadingDates ? (
          <div className="flex gap-2">
            {[...Array(7)].map((_, i) => (
              <div key={i} className="w-20 h-16 bg-muted rounded-xl animate-pulse" />
            ))}
          </div>
        ) : dates.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            Aucune archive disponible pour le moment.
          </p>
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-2">
            {dates.map((d) => (
              <button
                key={d.date}
                onClick={() => handleDateSelect(d.date)}
                className={cn(
                  "flex flex-col items-center px-4 py-3 rounded-xl border transition-all shrink-0",
                  selectedDate === d.date
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-card border-border hover:border-primary/50"
                )}
              >
                <span className="text-lg font-semibold">
                  {new Date(d.date).getDate()}
                </span>
                <span className="text-xs opacity-70">
                  {new Date(d.date).toLocaleDateString("fr-FR", { month: "short" })}
                </span>
                <span className={cn(
                  "text-xs mt-1 px-2 py-0.5 rounded-full",
                  selectedDate === d.date
                    ? "bg-primary-foreground/20"
                    : "bg-muted"
                )}>
                  {d.summary_count} briefings
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Selected date content */}
      {selectedDate && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">
            {formatDate(selectedDate)}
          </h2>

          {isLoadingSummaries ? (
            <div className="grid gap-4 md:grid-cols-2">
              <SummaryCardSkeleton />
              <SummaryCardSkeleton />
            </div>
          ) : summaries.length === 0 ? (
            <p className="text-muted-foreground">
              Aucun briefing pour cette date.
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {summaries.map((summary) => (
                <SummaryCard
                  key={summary.id}
                  summary={summary}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
