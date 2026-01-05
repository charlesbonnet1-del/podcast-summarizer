"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FlaskConical,
  Play,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  XCircle,
  ExternalLink,
  Zap,
  Settings,
  TrendingUp
} from "lucide-react";
import { cn } from "@/lib/utils";

// ============================================
// TYPES
// ============================================

interface Article {
  id: string;
  title: string;
  url: string;
  source_name: string;
  source_tier: string;
  topic?: string;
}

interface Cluster {
  id?: string;
  name: string;
  topic: string;
  article_count: number;
  sources?: string[];
}

interface VelocityData {
  cluster_name: string;
  topic: string;
  baseline: number;
  current: number;
  velocity: number;
}

interface ScoringData {
  cluster_name: string;
  topic: string;
  breakdown: Record<string, number>;
  source_mix: { authority: number; generalist: number; corporate: number };
  total_score: number;
  passes_threshold: boolean;
  severity: string;
  threshold_used: number;
}

interface PipelineResult {
  timestamp: string;
  steps: {
    fetch?: { duration_ms: number; total_articles: number; by_topic: Record<string, number>; by_tier: Record<string, number>; articles: Article[]; failed_sources?: any[]; failed_count?: number };
    embedding?: { duration_ms: number; embedded_count: number; total_articles: number };
    classify?: { duration_ms: number; general_articles: number; classified: number; results: Article[] };
    cluster?: { duration_ms: number; total_clusters: number; clusters: Cluster[]; noise_count?: number };
    velocity?: { duration_ms: number; data: VelocityData[] };
    scoring?: { duration_ms: number; data: ScoringData[] };
    signals?: { generated: ScoringData[]; rejected: ScoringData[]; generated_count: number; rejected_count: number };
  };
  thresholds?: { topic: string; min_velocity: number; min_score: number }[];
}

// ============================================
// CONSTANTS
// ============================================

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "https://podcast-summarizeredaily-bot.onrender.com";

const TIER_COLORS: Record<string, string> = { authority: "bg-purple-500", generalist: "bg-blue-500", corporate: "bg-gray-500" };
const TOPIC_COLORS: Record<string, string> = { ia: "bg-purple-500", macro: "bg-blue-500", asia: "bg-green-500", general: "bg-gray-500" };

// ============================================
// MAIN COMPONENT
// ============================================

export default function LabPage() {
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set(["fetch", "scoring", "signals"]));

  const toggleStep = (step: string) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(step)) newExpanded.delete(step);
    else newExpanded.add(step);
    setExpandedSteps(newExpanded);
  };

  const runPipeline = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/lab/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topics: ["ia", "macro", "asia"], max_age_days: 3 })
      });
      const data = await res.json();
      if (data.success) setResult(data.pipeline);
    } catch (error) {
      console.error("Pipeline error:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <FlaskConical className="w-6 h-6 text-primary" />
            Lab - Pipeline Observer
          </h1>
          <p className="text-muted-foreground mt-1">Observer la boîte noire : chaque étape de détection</p>
        </div>
        <button
          onClick={runPipeline}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {loading ? "Exécution..." : "Lancer le pipeline"}
        </button>
      </div>

      {/* No result yet */}
      {!result && !loading && (
        <div className="text-center py-16 bg-card border border-border rounded-xl">
          <FlaskConical className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-medium text-foreground">Pipeline non exécuté</h3>
          <p className="text-muted-foreground mt-1">Cliquez sur "Lancer le pipeline" pour observer chaque étape</p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-center py-16">
          <RefreshCw className="w-8 h-8 animate-spin text-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Exécution du pipeline...</p>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-4">
          {/* Step 1: Fetch */}
          <div>
            <button
              onClick={() => toggleStep("fetch")}
              className="w-full flex items-center gap-3 p-4 bg-card border border-border rounded-xl hover:border-primary/50"
            >
              {expandedSteps.has("fetch") ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span className="font-medium">ÉTAPE 1: FETCH</span>
              <span className="ml-auto px-2 py-0.5 bg-primary/20 text-primary rounded text-sm">
                {result.steps.fetch?.total_articles} articles
              </span>
              {(result.steps.fetch?.failed_count ?? 0) > 0 && (
                <span className="px-2 py-0.5 bg-red-500/20 text-red-500 rounded text-sm">
                  {result.steps.fetch?.failed_count} erreurs
                </span>
              )}
              <span className="text-sm text-muted-foreground">{result.steps.fetch?.duration_ms}ms</span>
            </button>
            <AnimatePresence>
              {expandedSteps.has("fetch") && result.steps.fetch && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                  <div className="mt-2 p-4 bg-muted/50 rounded-xl space-y-4">
                    <div>
                      <h4 className="text-sm font-medium mb-2">Par topic</h4>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(result.steps.fetch.by_topic).map(([topic, count]) => (
                          <div key={topic} className="flex items-center gap-2 px-3 py-1.5 bg-card rounded-lg">
                            <div className={cn("w-2 h-2 rounded-full", TOPIC_COLORS[topic])} />
                            <span className="text-sm">{topic}: {count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium mb-2">Par tier</h4>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(result.steps.fetch.by_tier).map(([tier, count]) => (
                          <div key={tier} className="flex items-center gap-2 px-3 py-1.5 bg-card rounded-lg">
                            <div className={cn("w-2 h-2 rounded-full", TIER_COLORS[tier])} />
                            <span className="text-sm capitalize">{tier}: {count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    
                    {/* Alternative sources stats */}
                    {result.steps.fetch.alternative_stats && (
                      <div>
                        <h4 className="text-sm font-medium mb-2">Sources alternatives</h4>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(result.steps.fetch.alternative_stats).map(([source, data]: [string, any]) => (
                            <div key={source} className={cn(
                              "flex items-center gap-2 px-3 py-1.5 rounded-lg",
                              data.count > 0 ? "bg-green-500/10 text-green-500" : "bg-muted text-muted-foreground"
                            )}>
                              <span className="text-sm capitalize">{source}:</span>
                              <span className="font-medium">{data.count}</span>
                              {data.error && <span className="text-xs text-red-500">({data.error})</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <div>
                      <h4 className="text-sm font-medium mb-2">Échantillon</h4>
                      <div className="space-y-1 max-h-48 overflow-y-auto">
                        {result.steps.fetch.articles.slice(0, 8).map((a, i) => (
                          <div key={i} className="flex items-center gap-2 p-2 bg-card rounded text-sm">
                            <div className={cn("w-2 h-2 rounded-full", TIER_COLORS[a.source_tier])} />
                            <span className="truncate flex-1">{a.title}</span>
                            <span className="text-muted-foreground text-xs">{a.source_name}</span>
                            <a href={a.url} target="_blank" className="text-primary"><ExternalLink className="w-3 h-3" /></a>
                          </div>
                        ))}
                      </div>
                    </div>
                    
                    {/* Failed sources */}
                    {result.steps.fetch.failed_sources && result.steps.fetch.failed_sources.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium mb-2 text-red-500 flex items-center gap-2">
                          <XCircle className="w-4 h-4" />
                          Sources en erreur ({result.steps.fetch.failed_count})
                        </h4>
                        <div className="space-y-1 max-h-48 overflow-y-auto">
                          {result.steps.fetch.failed_sources.map((s: any, i: number) => (
                            <div key={i} className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-sm">
                              <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                              <span className="text-foreground font-medium">{s.source_name}</span>
                              <span className={cn("px-1.5 py-0.5 rounded text-xs", TOPIC_COLORS[s.topic], "text-white")}>{s.topic}</span>
                              <span className="text-red-500 text-xs ml-auto">{s.error}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Step 2: Embedding */}
          {result.steps.embedding && (
            <div>
              <button
                onClick={() => toggleStep("embedding")}
                className="w-full flex items-center gap-3 p-4 bg-card border border-border rounded-xl hover:border-primary/50"
              >
                {expandedSteps.has("embedding") ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                <CheckCircle className="w-5 h-5 text-green-500" />
                <span className="font-medium">ÉTAPE 2: EMBEDDING</span>
                <span className="ml-auto px-2 py-0.5 bg-primary/20 text-primary rounded text-sm">
                  {result.steps.embedding.embedded_count} / {result.steps.embedding.total_articles}
                </span>
                <span className="text-sm text-muted-foreground">{result.steps.embedding.duration_ms}ms</span>
              </button>
            </div>
          )}

          {/* Step 3: Clustering */}
          <div>
            <button
              onClick={() => toggleStep("cluster")}
              className="w-full flex items-center gap-3 p-4 bg-card border border-border rounded-xl hover:border-primary/50"
            >
              {expandedSteps.has("cluster") ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span className="font-medium">ÉTAPE 3: CLUSTERING</span>
              <span className="ml-auto px-2 py-0.5 bg-primary/20 text-primary rounded text-sm">
                {result.steps.cluster?.total_clusters} clusters
              </span>
              <span className="text-sm text-muted-foreground">{result.steps.cluster?.duration_ms}ms</span>
            </button>
            <AnimatePresence>
              {expandedSteps.has("cluster") && result.steps.cluster && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                  <div className="mt-2 p-4 bg-muted/50 rounded-xl space-y-2">
                    {result.steps.cluster.clusters.map((c, i) => (
                      <div key={i} className="flex items-center gap-3 p-3 bg-card rounded-lg">
                        <div className={cn("w-2 h-2 rounded-full", TOPIC_COLORS[c.topic])} />
                        <span className="text-sm font-medium truncate flex-1">{c.name}</span>
                        <span className="text-xs text-muted-foreground">{c.article_count} articles</span>
                        <span className={cn("px-2 py-0.5 rounded text-xs text-white", TOPIC_COLORS[c.topic])}>{c.topic}</span>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Step 3: Velocity */}
          <div>
            <button
              onClick={() => toggleStep("velocity")}
              className="w-full flex items-center gap-3 p-4 bg-card border border-border rounded-xl hover:border-primary/50"
            >
              {expandedSteps.has("velocity") ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
              <TrendingUp className="w-5 h-5 text-green-500" />
              <span className="font-medium">ÉTAPE 4: VELOCITY</span>
              <span className="text-sm text-muted-foreground">{result.steps.velocity?.duration_ms}ms</span>
            </button>
            <AnimatePresence>
              {expandedSteps.has("velocity") && result.steps.velocity && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                  <div className="mt-2 p-4 bg-muted/50 rounded-xl overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="text-left text-muted-foreground"><th className="pb-2">Cluster</th><th className="pb-2">Baseline</th><th className="pb-2">Current</th><th className="pb-2">Velocity</th></tr></thead>
                      <tbody>
                        {result.steps.velocity.data.map((v, i) => (
                          <tr key={i} className="border-t border-border">
                            <td className="py-2"><div className="flex items-center gap-2"><div className={cn("w-2 h-2 rounded-full", TOPIC_COLORS[v.topic])} /><span className="truncate max-w-[200px]">{v.cluster_name}</span></div></td>
                            <td className="py-2 text-muted-foreground">{v.baseline}/j</td>
                            <td className="py-2">{v.current}</td>
                            <td className="py-2"><span className={cn("font-medium", v.velocity >= 5 ? "text-red-500" : v.velocity >= 3 ? "text-orange-500" : "text-muted-foreground")}>{v.velocity.toFixed(1)}x{v.velocity >= 5 && " 🔥"}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Step 4: Scoring */}
          <div>
            <button
              onClick={() => toggleStep("scoring")}
              className="w-full flex items-center gap-3 p-4 bg-card border border-border rounded-xl hover:border-primary/50"
            >
              {expandedSteps.has("scoring") ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span className="font-medium">ÉTAPE 5: SCORING</span>
              <span className="text-sm text-muted-foreground">{result.steps.scoring?.duration_ms}ms</span>
            </button>
            <AnimatePresence>
              {expandedSteps.has("scoring") && result.steps.scoring && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                  <div className="mt-2 p-4 bg-muted/50 rounded-xl overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="text-left text-muted-foreground"><th className="pb-2">Cluster</th><th className="pb-2">Vel</th><th className="pb-2">Src</th><th className="pb-2">Div</th><th className="pb-2">Nov</th><th className="pb-2">Vol</th><th className="pb-2">Total</th><th className="pb-2">Status</th></tr></thead>
                      <tbody>
                        {result.steps.scoring.data.map((s, i) => (
                          <tr key={i} className="border-t border-border">
                            <td className="py-2 truncate max-w-[120px]">{s.cluster_name}</td>
                            <td className="py-2 text-muted-foreground">{s.breakdown.velocity?.toFixed(0) || 0}</td>
                            <td className="py-2 text-muted-foreground">{s.breakdown.sources?.toFixed(0) || 0}</td>
                            <td className="py-2 text-muted-foreground">{s.breakdown.diversity?.toFixed(0) || 0}</td>
                            <td className="py-2 text-muted-foreground">{s.breakdown.novelty || 0}</td>
                            <td className="py-2 text-muted-foreground">{s.breakdown.volume || 0}</td>
                            <td className="py-2"><span className={cn("font-bold", s.total_score >= 70 ? "text-green-500" : s.total_score >= 60 ? "text-yellow-500" : "text-muted-foreground")}>{s.total_score}</span></td>
                            <td className="py-2">{s.passes_threshold ? <span className="text-green-500 flex items-center gap-1"><CheckCircle className="w-4 h-4" />{s.severity}</span> : <span className="text-muted-foreground flex items-center gap-1"><XCircle className="w-4 h-4" />reject</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Step 5: Signals */}
          <div>
            <button
              onClick={() => toggleStep("signals")}
              className="w-full flex items-center gap-3 p-4 bg-card border border-border rounded-xl hover:border-primary/50"
            >
              {expandedSteps.has("signals") ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
              <Zap className="w-5 h-5 text-primary" />
              <span className="font-medium">ÉTAPE 6: SIGNAUX</span>
              <span className="ml-auto px-2 py-0.5 bg-green-500/20 text-green-500 rounded text-sm">
                {result.steps.signals?.generated_count || 0} générés
              </span>
              <span className="px-2 py-0.5 bg-muted text-muted-foreground rounded text-sm">
                {result.steps.signals?.rejected_count || 0} rejetés
              </span>
            </button>
            <AnimatePresence>
              {expandedSteps.has("signals") && result.steps.signals && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                  <div className="mt-2 space-y-4">
                    {/* Generated */}
                    <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-xl">
                      <h4 className="text-sm font-medium text-green-500 mb-2 flex items-center gap-2">
                        <CheckCircle className="w-4 h-4" />Signaux générés ({result.steps.signals.generated_count})
                      </h4>
                      {result.steps.signals.generated.length > 0 ? (
                        <div className="space-y-2">
                          {result.steps.signals.generated.map((s, i) => (
                            <div key={i} className="flex items-center gap-3 p-2 bg-card rounded-lg">
                              <Zap className="w-4 h-4 text-green-500" />
                              <span className="text-sm flex-1">{s.cluster_name}</span>
                              <span className="text-sm font-medium text-green-500">Score: {s.total_score}</span>
                              <span className={cn("px-2 py-0.5 rounded text-xs text-white", s.severity === "breaking" ? "bg-red-500" : s.severity === "alert" ? "bg-orange-500" : "bg-yellow-500")}>{s.severity}</span>
                            </div>
                          ))}
                        </div>
                      ) : <p className="text-sm text-muted-foreground">Aucun signal généré</p>}
                    </div>
                    {/* Rejected */}
                    <div className="p-4 bg-muted/50 rounded-xl">
                      <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                        <XCircle className="w-4 h-4" />Clusters rejetés ({result.steps.signals.rejected_count})
                      </h4>
                      {result.steps.signals.rejected.length > 0 ? (
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                          {result.steps.signals.rejected.map((s, i) => (
                            <div key={i} className="flex items-center gap-3 p-2 bg-card rounded text-sm">
                              <span className="text-muted-foreground truncate flex-1">{s.cluster_name}</span>
                              <span className="text-muted-foreground text-xs">Score {s.total_score} &lt; {s.threshold_used}</span>
                            </div>
                          ))}
                        </div>
                      ) : <p className="text-sm text-muted-foreground">Aucun cluster rejeté</p>}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Thresholds info */}
          {result.thresholds && result.thresholds.length > 0 && (
            <div className="p-4 bg-card border border-border rounded-xl">
              <h4 className="text-sm font-medium mb-3 flex items-center gap-2"><Settings className="w-4 h-4" />Seuils actuels</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {result.thresholds.map((t) => (
                  <div key={t.topic} className="p-3 bg-muted rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={cn("w-2 h-2 rounded-full", TOPIC_COLORS[t.topic])} />
                      <span className="text-sm font-medium">{t.topic.toUpperCase()}</span>
                    </div>
                    <div className="text-xs text-muted-foreground space-y-1">
                      <div>min_velocity: {t.min_velocity}</div>
                      <div>min_score: {t.min_score}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
