"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Zap,
  ThumbsUp,
  ThumbsDown,
  Target,
  RefreshCw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  AlertCircle,
  Bell,
  FileText,
  BarChart3
} from "lucide-react";
import { cn } from "@/lib/utils";

// ============================================
// TYPES
// ============================================

interface Signal {
  id: string;
  topic: string;
  title: string;
  severity: "breaking" | "alert" | "digest" | "log";
  total_score: number;
  velocity_score: number;
  velocity_details: {
    baseline: number;
    current: number;
    velocity: number;
  };
  source_mix: {
    authority: number;
    generalist: number;
    corporate: number;
  };
  score_breakdown: Record<string, number>;
  status: string;
  detected_at: string;
  hook?: string;
  thesis?: string;
  antithesis?: string;
  key_data?: string;
  context?: string;
  articles?: Array<{
    title: string;
    url: string;
    source: string;
  }>;
  clusters?: {
    name: string;
    article_count: number;
    source_names: string[];
  };
  user_feedback?: string;
}

interface Stats {
  total_signals: number;
  by_topic: Record<string, number>;
  by_severity: Record<string, number>;
  feedback: {
    useful: number;
    not_useful: number;
    acted_on: number;
    no_feedback: number;
  };
  precision: number;
  thresholds: Array<{
    topic: string;
    min_velocity: number;
    min_score: number;
  }>;
}

// ============================================
// CONSTANTS
// ============================================

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "https://podcast-summarizeredaily-bot.onrender.com";

const SEVERITY_CONFIG = {
  breaking: {
    color: "text-red-500",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    icon: AlertCircle,
    label: "BREAKING"
  },
  alert: {
    color: "text-orange-500",
    bg: "bg-orange-500/10",
    border: "border-orange-500/30",
    icon: Bell,
    label: "ALERT"
  },
  digest: {
    color: "text-yellow-500",
    bg: "bg-yellow-500/10",
    border: "border-yellow-500/30",
    icon: FileText,
    label: "DIGEST"
  },
  log: {
    color: "text-gray-500",
    bg: "bg-gray-500/10",
    border: "border-gray-500/30",
    icon: FileText,
    label: "LOG"
  }
};

const TOPIC_COLORS: Record<string, string> = {
  ia: "bg-purple-500",
  macro: "bg-blue-500",
  asia: "bg-green-500",
  general: "bg-gray-500"
};

// ============================================
// SIGNAL CARD COMPONENT
// ============================================

function SignalCard({ 
  signal, 
  onFeedback 
}: { 
  signal: Signal; 
  onFeedback: (id: string, rating: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<string | null>(null);
  
  const severity = SEVERITY_CONFIG[signal.severity];
  const SeverityIcon = severity.icon;
  
  const timeAgo = getTimeAgo(signal.detected_at);
  
  const handleFeedback = (rating: string) => {
    setFeedbackGiven(rating);
    onFeedback(signal.id, rating);
  };
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-xl border p-4 transition-all",
        severity.bg,
        severity.border
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        {/* Severity badge */}
        <div className={cn(
          "flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium",
          severity.bg,
          severity.color
        )}>
          <SeverityIcon className="w-3.5 h-3.5" />
          {severity.label}
        </div>
        
        {/* Topic badge */}
        <div className={cn(
          "px-2 py-1 rounded-lg text-xs font-medium text-white",
          TOPIC_COLORS[signal.topic] || "bg-gray-500"
        )}>
          {signal.topic.toUpperCase()}
        </div>
        
        {/* Score */}
        <div className="ml-auto flex items-center gap-1 text-sm font-medium">
          <BarChart3 className="w-4 h-4" />
          {signal.total_score}
        </div>
      </div>
      
      {/* Title */}
      <h3 className="text-lg font-semibold mt-3 text-foreground">
        {signal.title}
      </h3>
      
      {/* Meta */}
      <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
        <span className="flex items-center gap-1">
          <TrendingUp className="w-4 h-4" />
          {signal.velocity_score?.toFixed(1)}x velocity
        </span>
        <span>
          {signal.source_mix?.authority || 0} auth + {signal.source_mix?.generalist || 0} gen
        </span>
        <span>{timeAgo}</span>
      </div>
      
      {/* Hook/Summary */}
      {signal.hook && (
        <p className="mt-3 text-sm text-muted-foreground italic">
          "{signal.hook}"
        </p>
      )}
      
      {/* Expand toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 mt-3 text-sm text-primary hover:underline"
      >
        {expanded ? (
          <>
            <ChevronUp className="w-4 h-4" />
            Masquer les détails
          </>
        ) : (
          <>
            <ChevronDown className="w-4 h-4" />
            Voir les détails
          </>
        )}
      </button>
      
      {/* Expanded details */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-4 pt-4 border-t border-border space-y-4">
              {/* Thesis/Antithesis */}
              {signal.thesis && (
                <div>
                  <h4 className="text-sm font-medium text-foreground">Thèse</h4>
                  <p className="text-sm text-muted-foreground mt-1">{signal.thesis}</p>
                </div>
              )}
              
              {signal.antithesis && (
                <div>
                  <h4 className="text-sm font-medium text-foreground">Antithèse</h4>
                  <p className="text-sm text-muted-foreground mt-1">{signal.antithesis}</p>
                </div>
              )}
              
              {/* Context */}
              {signal.context && (
                <div>
                  <h4 className="text-sm font-medium text-foreground">Contexte</h4>
                  <p className="text-sm text-muted-foreground mt-1">{signal.context}</p>
                </div>
              )}
              
              {/* Key data */}
              {signal.key_data && (
                <div>
                  <h4 className="text-sm font-medium text-foreground">Données clés</h4>
                  <p className="text-sm text-muted-foreground mt-1 whitespace-pre-line">{signal.key_data}</p>
                </div>
              )}
              
              {/* Articles sources */}
              {signal.articles && signal.articles.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-foreground mb-2">Articles sources ({signal.articles.length})</h4>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {signal.articles.map((article, i) => (
                      <a
                        key={i}
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 text-xs p-2 bg-muted rounded hover:bg-muted/80"
                      >
                        <span className="text-muted-foreground flex-shrink-0">{article.source}</span>
                        <span className="truncate flex-1">{article.title}</span>
                        <ExternalLink className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Score breakdown */}
              <div>
                <h4 className="text-sm font-medium text-foreground mb-2">Score breakdown</h4>
                <div className="grid grid-cols-5 gap-2">
                  {Object.entries(signal.score_breakdown || {}).map(([key, value]) => (
                    <div key={key} className="text-center p-2 bg-muted rounded-lg">
                      <div className="text-lg font-semibold">{Math.round(value as number)}</div>
                      <div className="text-xs text-muted-foreground capitalize">{key}</div>
                    </div>
                  ))}
                </div>
              </div>
              
              {/* Sources */}
              {signal.clusters?.source_names && (
                <div>
                  <h4 className="text-sm font-medium text-foreground mb-2">Sources ({signal.clusters.article_count} articles)</h4>
                  <div className="flex flex-wrap gap-2">
                    {signal.clusters.source_names.map((source: string) => (
                      <span key={source} className="px-2 py-1 bg-muted rounded text-xs">
                        {source}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      
      {/* Feedback buttons */}
      <div className="flex items-center gap-2 mt-4 pt-4 border-t border-border">
        <span className="text-sm text-muted-foreground mr-2">Ce signal est-il utile ?</span>
        
        <button
          onClick={() => handleFeedback("useful")}
          disabled={feedbackGiven !== null}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all",
            feedbackGiven === "useful"
              ? "bg-green-500 text-white"
              : feedbackGiven !== null
              ? "bg-muted text-muted-foreground opacity-50"
              : "bg-muted hover:bg-green-500/20 hover:text-green-500"
          )}
        >
          <ThumbsUp className="w-4 h-4" />
          Utile
        </button>
        
        <button
          onClick={() => handleFeedback("not_useful")}
          disabled={feedbackGiven !== null}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all",
            feedbackGiven === "not_useful"
              ? "bg-red-500 text-white"
              : feedbackGiven !== null
              ? "bg-muted text-muted-foreground opacity-50"
              : "bg-muted hover:bg-red-500/20 hover:text-red-500"
          )}
        >
          <ThumbsDown className="w-4 h-4" />
          Pas pertinent
        </button>
        
        <button
          onClick={() => handleFeedback("acted_on")}
          disabled={feedbackGiven !== null}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all",
            feedbackGiven === "acted_on"
              ? "bg-primary text-white"
              : feedbackGiven !== null
              ? "bg-muted text-muted-foreground opacity-50"
              : "bg-muted hover:bg-primary/20 hover:text-primary"
          )}
        >
          <Target className="w-4 h-4" />
          J'ai agi
        </button>
      </div>
    </motion.div>
  );
}

// ============================================
// STATS CARD COMPONENT
// ============================================

function StatsCard({ stats }: { stats: Stats | null }) {
  if (!stats) return null;
  
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div className="p-4 rounded-xl bg-card border border-border">
        <div className="text-2xl font-bold text-foreground">{stats.total_signals}</div>
        <div className="text-sm text-muted-foreground">Signaux (30j)</div>
      </div>
      
      <div className="p-4 rounded-xl bg-card border border-border">
        <div className="text-2xl font-bold text-foreground">{stats.precision}%</div>
        <div className="text-sm text-muted-foreground">Précision</div>
      </div>
      
      <div className="p-4 rounded-xl bg-card border border-border">
        <div className="text-2xl font-bold text-green-500">{stats.feedback.acted_on}</div>
        <div className="text-sm text-muted-foreground">Actions prises</div>
      </div>
      
      <div className="p-4 rounded-xl bg-card border border-border">
        <div className="text-2xl font-bold text-foreground">
          {stats.feedback.useful + stats.feedback.acted_on}
        </div>
        <div className="text-sm text-muted-foreground">Signaux utiles</div>
      </div>
    </div>
  );
}

// ============================================
// HELPER FUNCTIONS
// ============================================

function getTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffMins < 60) return `il y a ${diffMins}min`;
  if (diffHours < 24) return `il y a ${diffHours}h`;
  return `il y a ${diffDays}j`;
}

// ============================================
// MAIN PAGE COMPONENT
// ============================================

export default function SignalsDashboard() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState(false);
  const [filter, setFilter] = useState<string>("all");
  
  // Fetch signals
  const fetchSignals = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/signals?limit=50`);
      const data = await res.json();
      if (data.success) {
        setSignals(data.signals || []);
      }
    } catch (error) {
      console.error("Error fetching signals:", error);
    }
  };
  
  // Fetch stats
  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/signals/stats`);
      const data = await res.json();
      if (data.success) {
        setStats(data.stats);
      }
    } catch (error) {
      console.error("Error fetching stats:", error);
    }
  };
  
  // Initial load
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchSignals(), fetchStats()]);
      setLoading(false);
    };
    load();
  }, []);
  
  // Trigger detection
  const handleDetect = async () => {
    setDetecting(true);
    try {
      const res = await fetch(`${API_BASE}/api/lab/detect-and-save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ topics: ["ia", "macro", "asia"], max_age_days: 3 })
      });
      const data = await res.json();
      if (data.success) {
        // Show detection result
        alert(`✅ Détection terminée!\n\n${data.saved_count} signaux sauvegardés\n${data.rejected_count} clusters rejetés`);
        // Refresh signals
        await fetchSignals();
        await fetchStats();
      } else {
        alert(`❌ Erreur: ${data.error}`);
      }
    } catch (error) {
      console.error("Error detecting:", error);
      alert("❌ Erreur de détection");
    } finally {
      setDetecting(false);
    }
  };
  
  // Send feedback
  const handleFeedback = async (signalId: string, rating: string) => {
    try {
      await fetch(`${API_BASE}/api/signals/${signalId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating })
      });
    } catch (error) {
      console.error("Error sending feedback:", error);
    }
  };
  
  // Filter signals
  const filteredSignals = signals.filter(s => {
    if (filter === "all") return true;
    return s.severity === filter;
  });
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Zap className="w-6 h-6 text-primary" />
            Signals
          </h1>
          <p className="text-muted-foreground mt-1">
            Détection automatique d'anomalies et tendances
          </p>
        </div>
        
        <button
          onClick={handleDetect}
          disabled={detecting}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 disabled:opacity-50 transition-all"
        >
          <RefreshCw className={cn("w-4 h-4", detecting && "animate-spin")} />
          {detecting ? "Détection..." : "Détecter"}
        </button>
      </div>
      
      {/* Stats */}
      <StatsCard stats={stats} />
      
      {/* Filters */}
      <div className="flex items-center gap-2">
        {["all", "breaking", "alert", "digest"].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-sm transition-all",
              filter === f
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground"
            )}
          >
            {f === "all" ? "Tous" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      
      {/* Signals list */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : filteredSignals.length === 0 ? (
        <div className="text-center py-12">
          <Zap className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-medium text-foreground">Aucun signal</h3>
          <p className="text-muted-foreground mt-1">
            Cliquez sur "Détecter" pour lancer une analyse
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredSignals.map((signal) => (
            <SignalCard
              key={signal.id}
              signal={signal}
              onFeedback={handleFeedback}
            />
          ))}
        </div>
      )}
    </div>
  );
}
