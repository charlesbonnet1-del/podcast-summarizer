"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { 
  LayoutDashboard, 
  Settings2,
  Sparkles,
  Play,
  Loader2, 
  ExternalLink,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  Filter,
  Layers,
  Target,
  AlertTriangle,
  RefreshCw,
  Clock,
  XCircle
} from "lucide-react";

interface PipelineParams {
  flash_segment_count: number;
  digest_segment_count: number;
  min_cluster_size: number;
  min_articles_fallback: number;
  content_queue_days: number;
  maturation_window_hours: number;
  segment_cache_days: number;
  flash_duration_min: number;
  flash_duration_max: number;
  digest_duration_min: number;
  digest_duration_max: number;
  bing_backup_threshold: number;
  max_articles_per_rss: number;
  topics_enabled: { [topic: string]: boolean };
}

interface Article {
  url: string;
  title: string;
  source_type: string;
  source_name: string;
  source_country: string;
  topic: string;
  published?: string;
  fetched_at?: string;
}

interface Cluster {
  topic: string;
  cluster_id: string;
  size: number;
  articles: Article[];
  representative_title: string;
  sources: string[];
}

interface Segment {
  topic: string;
  type: string;
  cluster_size: number;
  articles: Article[];
  representative_title: string;
  duration_target: number;
}

interface Exclusion {
  type: string;
  topic?: string;
  article?: string;
  reason: string;
  source?: string;
  cluster_size?: number;
  article_count?: number;
}

interface StepResult {
  articles?: Article[];
  clusters?: Cluster[];
  segments?: Segment[];
  exclusions: Exclusion[];
  stats: Record<string, unknown>;
}

const DEFAULT_PARAMS: PipelineParams = {
  flash_segment_count: 4,
  digest_segment_count: 8,
  min_cluster_size: 3,
  min_articles_fallback: 5,
  content_queue_days: 3,
  maturation_window_hours: 72,
  segment_cache_days: 1,
  flash_duration_min: 45,
  flash_duration_max: 60,
  digest_duration_min: 90,
  digest_duration_max: 120,
  bing_backup_threshold: 5,
  max_articles_per_rss: 10,
  topics_enabled: {
    asia: true, attention: true, crypto: true, cyber: true, deals: true,
    deep_tech: true, energy: true, health: true, ia: true, info: true,
    macro: true, persuasion: true, regulation: true, resources: true, space: true
  }
};

export default function PipelineLabPage() {
  // State
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState<"idle" | "fetch" | "cluster" | "select">("idle");
  
  // Parameters
  const [params, setParams] = useState<PipelineParams>(DEFAULT_PARAMS);
  const [format, setFormat] = useState<"flash" | "digest">("flash");
  
  // Results for each step
  const [fetchResult, setFetchResult] = useState<StepResult | null>(null);
  const [clusterResult, setClusterResult] = useState<StepResult | null>(null);
  const [selectResult, setSelectResult] = useState<StepResult | null>(null);
  
  // UI state
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["params"]));
  const [error, setError] = useState<string | null>(null);

  function toggleSection(section: string) {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  }

  function updateParam<K extends keyof PipelineParams>(key: K, value: PipelineParams[K]) {
    setParams(prev => ({ ...prev, [key]: value }));
  }

  function toggleTopic(topic: string) {
    setParams(prev => ({
      ...prev,
      topics_enabled: {
        ...prev.topics_enabled,
        [topic]: !prev.topics_enabled[topic]
      }
    }));
  }

  async function runFetch() {
    setLoading(true);
    setCurrentStep("fetch");
    setError(null);
    setFetchResult(null);
    setClusterResult(null);
    setSelectResult(null);

    try {
      const res = await fetch("/api/pipeline-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "fetch",
          params,
          topics: Object.entries(params.topics_enabled)
            .filter(([, enabled]) => enabled)
            .map(([topic]) => topic)
        })
      });

      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setFetchResult(data);
        setExpandedSections(prev => {
          const next = new Set(prev);
          next.add("fetch");
          return next;
        });
      }
    } catch (err) {
      setError("Fetch failed");
      console.error(err);
    } finally {
      setLoading(false);
      setCurrentStep("idle");
    }
  }

  async function runCluster() {
    if (!fetchResult?.articles) {
      setError("Run Fetch first");
      return;
    }

    setLoading(true);
    setCurrentStep("cluster");
    setError(null);
    setClusterResult(null);
    setSelectResult(null);

    try {
      const res = await fetch("/api/pipeline-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "cluster",
          articles: fetchResult.articles,
          params
        })
      });

      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setClusterResult(data);
        setExpandedSections(prev => {
          const next = new Set(prev);
          next.add("cluster");
          return next;
        });
      }
    } catch (err) {
      setError("Clustering failed");
      console.error(err);
    } finally {
      setLoading(false);
      setCurrentStep("idle");
    }
  }

  async function runSelect() {
    if (!clusterResult?.clusters || !fetchResult?.articles) {
      setError("Run Cluster first");
      return;
    }

    setLoading(true);
    setCurrentStep("select");
    setError(null);
    setSelectResult(null);

    try {
      const res = await fetch("/api/pipeline-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "select",
          clusters: clusterResult.clusters,
          articles: fetchResult.articles,
          params,
          format
        })
      });

      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSelectResult(data);
        setExpandedSections(prev => {
          const next = new Set(prev);
          next.add("select");
          return next;
        });
      }
    } catch (err) {
      setError("Selection failed");
      console.error(err);
    } finally {
      setLoading(false);
      setCurrentStep("idle");
    }
  }

  async function runFullPipeline() {
    setLoading(true);
    setCurrentStep("fetch");
    setError(null);
    setFetchResult(null);
    setClusterResult(null);
    setSelectResult(null);

    try {
      const res = await fetch("/api/pipeline-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "run",
          params,
          format,
          topics: Object.entries(params.topics_enabled)
            .filter(([, enabled]) => enabled)
            .map(([topic]) => topic)
        })
      });

      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setFetchResult(data.fetch);
        setClusterResult(data.cluster);
        setSelectResult(data.select);
        const newSections = new Set<string>();
        newSections.add("fetch");
        newSections.add("cluster");
        newSections.add("select");
        setExpandedSections(newSections);
      }
    } catch (err) {
      setError("Pipeline failed");
      console.error(err);
    } finally {
      setLoading(false);
      setCurrentStep("idle");
    }
  }

  function resetAll() {
    setFetchResult(null);
    setClusterResult(null);
    setSelectResult(null);
    setError(null);
    setParams(DEFAULT_PARAMS);
  }

  const enabledTopicsCount = Object.values(params.topics_enabled).filter(Boolean).length;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-xl border-b border-border/50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/dashboard">
              <button className="flex items-center gap-2 px-4 py-2 rounded-full bg-card/60 backdrop-blur-xl border border-border/30 text-foreground hover:bg-card/80 hover:border-primary/30 transition-all font-medium text-sm">
                <LayoutDashboard className="w-4 h-4" />
                Dashboard
              </button>
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500/20 to-red-500/20 flex items-center justify-center">
                <Settings2 className="w-4 h-4 text-orange-400" />
              </div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-orange-400 to-red-400 bg-clip-text text-transparent">
                Pipeline Lab
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/prompt-lab">
              <button className="flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-cyan-500/20 to-purple-500/20 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/30 transition-all font-medium text-sm">
                <Sparkles className="w-4 h-4" />
                Prompt Lab
              </button>
            </Link>
            <button
              onClick={resetAll}
              className="p-2 rounded-lg hover:bg-background/50 transition-colors"
              title="Reset all"
            >
              <RefreshCw className="w-4 h-4 text-muted-foreground" />
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="pt-20 pb-12 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Left column: Parameters */}
          <div className="space-y-4">
            {/* Parameters */}
            <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl overflow-hidden">
              <button
                onClick={() => toggleSection("params")}
                className="w-full flex items-center justify-between p-4 hover:bg-background/30 transition-colors"
              >
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Settings2 className="w-5 h-5 text-orange-400" />
                  Parameters
                </h2>
                {expandedSections.has("params") ? (
                  <ChevronDown className="w-5 h-5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="w-5 h-5 text-muted-foreground" />
                )}
              </button>

              {expandedSections.has("params") && (
                <div className="px-4 pb-4 space-y-4">
                  {/* Format selector */}
                  <div>
                    <label className="text-xs text-muted-foreground mb-2 block">Format</label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setFormat("flash")}
                        className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                          format === "flash"
                            ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                            : "bg-background/50 text-muted-foreground border border-border/30 hover:bg-background/80"
                        }`}
                      >
                        Flash
                      </button>
                      <button
                        onClick={() => setFormat("digest")}
                        className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                          format === "digest"
                            ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                            : "bg-background/50 text-muted-foreground border border-border/30 hover:bg-background/80"
                        }`}
                      >
                        Digest
                      </button>
                    </div>
                  </div>

                  {/* Segment counts */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">Flash Segments</label>
                      <input
                        type="number"
                        value={params.flash_segment_count}
                        onChange={(e) => updateParam("flash_segment_count", parseInt(e.target.value) || 0)}
                        className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">Digest Segments</label>
                      <input
                        type="number"
                        value={params.digest_segment_count}
                        onChange={(e) => updateParam("digest_segment_count", parseInt(e.target.value) || 0)}
                        className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm"
                      />
                    </div>
                  </div>

                  {/* Clustering */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">Min Cluster Size</label>
                      <input
                        type="number"
                        value={params.min_cluster_size}
                        onChange={(e) => updateParam("min_cluster_size", parseInt(e.target.value) || 0)}
                        className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">Fallback Articles</label>
                      <input
                        type="number"
                        value={params.min_articles_fallback}
                        onChange={(e) => updateParam("min_articles_fallback", parseInt(e.target.value) || 0)}
                        className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm"
                      />
                    </div>
                  </div>

                  {/* Time windows */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">Queue Days</label>
                      <input
                        type="number"
                        value={params.content_queue_days}
                        onChange={(e) => updateParam("content_queue_days", parseInt(e.target.value) || 0)}
                        className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">Bing Threshold</label>
                      <input
                        type="number"
                        value={params.bing_backup_threshold}
                        onChange={(e) => updateParam("bing_backup_threshold", parseInt(e.target.value) || 0)}
                        className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm"
                      />
                    </div>
                  </div>

                  {/* Duration targets */}
                  <div>
                    <label className="text-xs text-muted-foreground mb-2 block">
                      Duration (sec): Flash {params.flash_duration_min}-{params.flash_duration_max} / Digest {params.digest_duration_min}-{params.digest_duration_max}
                    </label>
                  </div>

                  {/* Topics */}
                  <div>
                    <label className="text-xs text-muted-foreground mb-2 block">
                      Topics ({enabledTopicsCount}/15 enabled)
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(params.topics_enabled).map(([topic, enabled]) => (
                        <button
                          key={topic}
                          onClick={() => toggleTopic(topic)}
                          className={`px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
                            enabled
                              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                              : "bg-background/50 text-muted-foreground border border-border/30"
                          }`}
                        >
                          {topic}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl p-4 space-y-3">
              <button
                onClick={runFetch}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30 disabled:opacity-50 transition-all font-medium"
              >
                {loading && currentStep === "fetch" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Filter className="w-4 h-4" />
                )}
                1. Fetch Articles
              </button>

              <button
                onClick={runCluster}
                disabled={loading || !fetchResult}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-purple-500/20 text-purple-400 border border-purple-500/30 hover:bg-purple-500/30 disabled:opacity-50 transition-all font-medium"
              >
                {loading && currentStep === "cluster" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Layers className="w-4 h-4" />
                )}
                2. Cluster
              </button>

              <button
                onClick={runSelect}
                disabled={loading || !clusterResult}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 disabled:opacity-50 transition-all font-medium"
              >
                {loading && currentStep === "select" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Target className="w-4 h-4" />
                )}
                3. Select
              </button>

              <div className="border-t border-border/30 pt-3">
                <button
                  onClick={runFullPipeline}
                  disabled={loading}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-500 text-white font-semibold hover:opacity-90 disabled:opacity-50 transition-all"
                >
                  {loading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Play className="w-5 h-5" />
                  )}
                  Run Full Pipeline
                </button>
              </div>
            </div>

            {/* Error display */}
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                <p className="text-red-400 text-sm flex items-center gap-2">
                  <XCircle className="w-4 h-4" />
                  {error}
                </p>
              </div>
            )}
          </div>

          {/* Middle + Right columns: Results */}
          <div className="lg:col-span-2 space-y-4">
            {/* Fetch Results */}
            {fetchResult && (
              <ResultCard
                title="1. Fetch Results"
                icon={<Filter className="w-5 h-5 text-blue-400" />}
                stats={fetchResult.stats}
                expanded={expandedSections.has("fetch")}
                onToggle={() => toggleSection("fetch")}
              >
                <div className="space-y-4">
                  {/* Articles by topic */}
                  <div>
                    <h4 className="text-sm font-medium mb-2">Articles by Topic</h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(fetchResult.stats.by_topic || {}).map(([topic, count]) => (
                        <span key={topic} className="px-2 py-1 bg-blue-500/10 text-blue-400 rounded text-xs">
                          {topic}: {String(count)}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Exclusions */}
                  {fetchResult.exclusions.length > 0 && (
                    <ExclusionsList exclusions={fetchResult.exclusions} />
                  )}
                </div>
              </ResultCard>
            )}

            {/* Cluster Results */}
            {clusterResult && (
              <ResultCard
                title="2. Cluster Results"
                icon={<Layers className="w-5 h-5 text-purple-400" />}
                stats={clusterResult.stats}
                expanded={expandedSections.has("cluster")}
                onToggle={() => toggleSection("cluster")}
              >
                <div className="space-y-4">
                  {/* Clusters */}
                  {clusterResult.clusters && clusterResult.clusters.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2">Clusters ({clusterResult.clusters.length})</h4>
                      <div className="space-y-2 max-h-60 overflow-y-auto">
                        {clusterResult.clusters.map((cluster, i) => (
                          <div key={i} className="p-3 bg-background/30 rounded-lg border border-border/20">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs uppercase text-purple-400 font-medium">{cluster.topic}</span>
                              <span className="text-xs text-muted-foreground">{cluster.size} articles</span>
                            </div>
                            <p className="text-sm truncate">{cluster.representative_title}</p>
                            <p className="text-xs text-muted-foreground mt-1">
                              Sources: {cluster.sources.join(", ")}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Exclusions */}
                  {clusterResult.exclusions.length > 0 && (
                    <ExclusionsList exclusions={clusterResult.exclusions} />
                  )}
                </div>
              </ResultCard>
            )}

            {/* Select Results */}
            {selectResult && (
              <ResultCard
                title="3. Selection Results"
                icon={<Target className="w-5 h-5 text-emerald-400" />}
                stats={selectResult.stats}
                expanded={expandedSections.has("select")}
                onToggle={() => toggleSection("select")}
              >
                <div className="space-y-4">
                  {/* Final Segments */}
                  {selectResult.segments && selectResult.segments.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2">Final Segments ({selectResult.segments.length})</h4>
                      <div className="space-y-2">
                        {selectResult.segments.map((seg, i) => (
                          <div key={i} className="p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs uppercase text-emerald-400 font-medium">{seg.topic}</span>
                              <div className="flex items-center gap-2">
                                <span className={`text-xs px-2 py-0.5 rounded ${
                                  seg.type === "cluster" 
                                    ? "bg-purple-500/20 text-purple-400" 
                                    : "bg-amber-500/20 text-amber-400"
                                }`}>
                                  {seg.type}
                                </span>
                                <span className="text-xs text-muted-foreground">
                                  {seg.articles.length} articles • {seg.duration_target}s
                                </span>
                              </div>
                            </div>
                            <p className="text-sm truncate">{seg.representative_title}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Send to Prompt Lab */}
                  {selectResult.segments && selectResult.segments.length > 0 && (
                    <Link href="/prompt-lab">
                      <button className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-purple-500 text-white font-semibold hover:opacity-90 transition-all">
                        <Sparkles className="w-5 h-5" />
                        Generate Script in Prompt Lab
                      </button>
                    </Link>
                  )}

                  {/* Exclusions */}
                  {selectResult.exclusions.length > 0 && (
                    <ExclusionsList exclusions={selectResult.exclusions} />
                  )}
                </div>
              </ResultCard>
            )}

            {/* Empty state */}
            {!fetchResult && !clusterResult && !selectResult && (
              <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl p-12 text-center">
                <Settings2 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold mb-2">Pipeline Lab</h3>
                <p className="text-muted-foreground text-sm mb-6">
                  Configure parameters and run the pipeline to see results.<br />
                  Each step can be run individually or all at once.
                </p>
                <div className="flex justify-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><Filter className="w-3 h-3" /> Fetch</span>
                  <span>→</span>
                  <span className="flex items-center gap-1"><Layers className="w-3 h-3" /> Cluster</span>
                  <span>→</span>
                  <span className="flex items-center gap-1"><Target className="w-3 h-3" /> Select</span>
                  <span>→</span>
                  <span className="flex items-center gap-1"><Sparkles className="w-3 h-3" /> Generate</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Result Card Component
function ResultCard({ 
  title, 
  icon, 
  stats, 
  expanded, 
  onToggle, 
  children 
}: { 
  title: string;
  icon: React.ReactNode;
  stats: Record<string, unknown>;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-background/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          {icon}
          <h3 className="font-semibold">{title}</h3>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {stats.total_articles !== undefined && (
              <span className="px-2 py-0.5 bg-background/50 rounded">{String(stats.total_articles)} articles</span>
            )}
            {stats.clusters_formed !== undefined && (
              <span className="px-2 py-0.5 bg-background/50 rounded">{String(stats.clusters_formed)} clusters</span>
            )}
            {stats.segments_created !== undefined && (
              <span className="px-2 py-0.5 bg-background/50 rounded">{String(stats.segments_created)} segments</span>
            )}
            {stats.duration_seconds !== undefined && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {Number(stats.duration_seconds).toFixed(1)}s
              </span>
            )}
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="w-5 h-5 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-5 h-5 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border/20 pt-4">
          {children}
        </div>
      )}
    </div>
  );
}

// Exclusions List Component
function ExclusionsList({ exclusions }: { exclusions: Exclusion[] }) {
  const [showAll, setShowAll] = useState(false);
  const displayedExclusions = showAll ? exclusions : exclusions.slice(0, 5);

  return (
    <div>
      <h4 className="text-sm font-medium mb-2 flex items-center gap-2 text-amber-400">
        <AlertTriangle className="w-4 h-4" />
        Exclusions ({exclusions.length})
      </h4>
      <div className="space-y-1 max-h-40 overflow-y-auto">
        {displayedExclusions.map((exc, i) => (
          <div key={i} className="text-xs p-2 bg-amber-500/10 rounded border border-amber-500/20">
            <span className="font-medium text-amber-400">{exc.type}</span>
            {exc.topic && <span className="text-muted-foreground"> • {exc.topic}</span>}
            {exc.article && <span className="text-muted-foreground"> • {exc.article}</span>}
            <p className="text-muted-foreground mt-0.5">{exc.reason}</p>
          </div>
        ))}
      </div>
      {exclusions.length > 5 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="text-xs text-amber-400 mt-2 hover:underline"
        >
          {showAll ? "Show less" : `Show all ${exclusions.length} exclusions`}
        </button>
      )}
    </div>
  );
}
