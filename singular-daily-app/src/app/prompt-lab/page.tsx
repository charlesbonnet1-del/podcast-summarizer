"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { 
  LayoutDashboard, 
  Sparkles, 
  Send, 
  Loader2, 
  ExternalLink,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  Clock,
  Save,
  RefreshCw,
  Zap,
  Filter,
  Layers,
  Target,
  Play,
  AlertTriangle,
  XCircle
} from "lucide-react";

// ============================================
// TYPES
// ============================================

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
  id: string;
  url: string;
  title: string;
  source_type?: string;
  source_name: string;
  source_country?: string;
  topic?: string;
  keyword?: string;
  published?: string;
  published_at?: string | null;
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

interface TopicArticles {
  [topic: string]: Article[];
}

interface Prompts {
  dialogue_segment: string;
  dialogue_multi_source: string;
}

interface TopicIntentions {
  [topic: string]: string;
}

interface GenerationResult {
  script: string;
  enriched_context: string | null;
  perplexity_citations: Array<{ title: string; url: string }>;
  word_count: number;
  generation_time_ms: number;
  topic: string;
  topic_intention: string;
  sources: string[];
}

// ============================================
// DEFAULT VALUES
// ============================================

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

// ============================================
// MAIN COMPONENT
// ============================================

export default function PromptLabPage() {
  // Loading states
  const [loading, setLoading] = useState(true);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [currentStep, setCurrentStep] = useState<"idle" | "fetch" | "cluster" | "select">("idle");
  
  // Pipeline params (sandbox - not saved until "Save" clicked)
  const [params, setParams] = useState<PipelineParams>(DEFAULT_PARAMS);
  const [savedParams, setSavedParams] = useState<PipelineParams>(DEFAULT_PARAMS);
  const [format, setFormat] = useState<"flash" | "digest">("flash");
  
  // Pipeline results
  const [fetchResult, setFetchResult] = useState<StepResult | null>(null);
  const [clusterResult, setClusterResult] = useState<StepResult | null>(null);
  const [selectResult, setSelectResult] = useState<StepResult | null>(null);
  
  // Queue data
  const [queue, setQueue] = useState<TopicArticles>({});
  
  // Prompts (sandbox)
  const [prompts, setPrompts] = useState<Prompts>({ dialogue_segment: "", dialogue_multi_source: "" });
  const [savedPrompts, setSavedPrompts] = useState<Prompts>({ dialogue_segment: "", dialogue_multi_source: "" });
  const [topicIntentions, setTopicIntentions] = useState<TopicIntentions>({});
  const [savedIntentions, setSavedIntentions] = useState<TopicIntentions>({});
  
  // Form state
  const [selectedTopic, setSelectedTopic] = useState<string>("");
  const [selectedArticles, setSelectedArticles] = useState<Set<string>>(new Set());
  const [editedPrompt, setEditedPrompt] = useState<string>("");
  const [editedIntention, setEditedIntention] = useState<string>("");
  const [useEnrichment, setUseEnrichment] = useState(false);
  
  // Results
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // UI state
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["prompts"]));
  const [collapsedQueueTopics, setCollapsedQueueTopics] = useState<Set<string>>(new Set());

  // ============================================
  // LOAD DATA
  // ============================================

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (selectedTopic && topicIntentions[selectedTopic]) {
      setEditedIntention(topicIntentions[selectedTopic]);
    } else {
      setEditedIntention("");
    }
  }, [selectedTopic, topicIntentions]);

  async function loadData() {
    setLoading(true);
    try {
      const queueRes = await fetch("/api/prompt-lab?action=queue");
      const queueData = await queueRes.json();
      if (queueData.topics) {
        setQueue(queueData.topics);
        const firstTopic = Object.keys(queueData.topics).find(t => queueData.topics[t].length > 0);
        if (firstTopic) setSelectedTopic(firstTopic);
      }

      const promptsRes = await fetch("/api/prompt-lab?action=prompts");
      const promptsData = await promptsRes.json();
      if (promptsData.prompts) {
        setPrompts(promptsData.prompts);
        setSavedPrompts(promptsData.prompts);
        setEditedPrompt(promptsData.prompts.dialogue_segment);
      }
      if (promptsData.topic_intentions) {
        setTopicIntentions(promptsData.topic_intentions);
        setSavedIntentions(promptsData.topic_intentions);
      }

      const paramsRes = await fetch("/api/pipeline-lab");
      const paramsData = await paramsRes.json();
      if (paramsData && !paramsData.error) {
        setParams(paramsData);
        setSavedParams(paramsData);
      }
    } catch (err) {
      console.error("Failed to load data:", err);
      setError("Failed to load data");
    } finally {
      setLoading(false);
    }
  }

  // ============================================
  // PIPELINE ACTIONS
  // ============================================

  async function runFetch() {
    setPipelineLoading(true);
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
        setExpandedSections(prev => { const next = new Set(Array.from(prev)); next.add("fetch-results"); return next; });
      }
    } catch (err) {
      setError("Fetch failed");
      console.error(err);
    } finally {
      setPipelineLoading(false);
      setCurrentStep("idle");
    }
  }

  async function runCluster() {
    if (!fetchResult?.articles) {
      setError("Run Fetch first");
      return;
    }
    setPipelineLoading(true);
    setCurrentStep("cluster");
    setError(null);
    setClusterResult(null);
    setSelectResult(null);

    try {
      const res = await fetch("/api/pipeline-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "cluster", articles: fetchResult.articles, params })
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setClusterResult(data);
        setExpandedSections(prev => { const next = new Set(Array.from(prev)); next.add("cluster-results"); return next; });
      }
    } catch (err) {
      setError("Clustering failed");
      console.error(err);
    } finally {
      setPipelineLoading(false);
      setCurrentStep("idle");
    }
  }

  async function runSelect() {
    if (!clusterResult?.clusters || !fetchResult?.articles) {
      setError("Run Cluster first");
      return;
    }
    setPipelineLoading(true);
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
        setExpandedSections(prev => { const next = new Set(Array.from(prev)); next.add("select-results"); return next; });
      }
    } catch (err) {
      setError("Selection failed");
      console.error(err);
    } finally {
      setPipelineLoading(false);
      setCurrentStep("idle");
    }
  }

  async function runFullPipeline() {
    setPipelineLoading(true);
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
        setExpandedSections(new Set(["fetch-results", "cluster-results", "select-results"]));
      }
    } catch (err) {
      setError("Pipeline failed");
      console.error(err);
    } finally {
      setPipelineLoading(false);
      setCurrentStep("idle");
    }
  }

  // ============================================
  // GENERATION ACTIONS
  // ============================================

  async function handleGenerate() {
    if (selectedArticles.size === 0) {
      setError("Please select at least one article");
      return;
    }
    setGenerating(true);
    setError(null);
    setResult(null);

    try {
      // Collect full article data from queue (sidebar) or from pipeline results
      const articlesToSend: Article[] = [];
      
      // First, try to get articles from selectResult segments (pipeline path)
      if (selectResult?.segments) {
        for (const segment of selectResult.segments) {
          if (segment.articles) {
            for (const art of segment.articles) {
              if (selectedArticles.has(art.id) || selectedArticles.has(art.url)) {
                articlesToSend.push(art);
              }
            }
          }
        }
      }
      
      // Also check clusterResult
      if (clusterResult?.clusters) {
        for (const cluster of clusterResult.clusters) {
          if (cluster.articles) {
            for (const art of cluster.articles) {
              const artId = art.id || art.url;
              if (selectedArticles.has(artId) && !articlesToSend.find(a => (a.id || a.url) === artId)) {
                articlesToSend.push(art);
              }
            }
          }
        }
      }
      
      // Fall back to queue articles (sidebar selection)
      if (articlesToSend.length === 0) {
        for (const topic of Object.keys(queue)) {
          for (const art of queue[topic]) {
            if (selectedArticles.has(art.id)) {
              articlesToSend.push(art);
            }
          }
        }
      }

      const res = await fetch("/api/prompt-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "generate",
          article_ids: Array.from(selectedArticles),
          articles: articlesToSend, // Send full article data to avoid re-extraction
          topic: selectedTopic,
          custom_prompt: editedPrompt !== savedPrompts.dialogue_segment ? editedPrompt : undefined,
          custom_intention: editedIntention !== savedIntentions[selectedTopic] ? editedIntention : undefined,
          use_enrichment: useEnrichment
        })
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (err) {
      console.error("Generation failed:", err);
      setError("Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  // ============================================
  // SAVE ACTIONS
  // ============================================

  async function handleSavePrompt() {
    setSaving(true);
    try {
      await fetch("/api/prompt-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "save", prompt_name: "dialogue_segment", prompt_content: editedPrompt })
      });
      setSavedPrompts(prev => ({ ...prev, dialogue_segment: editedPrompt }));
      setPrompts(prev => ({ ...prev, dialogue_segment: editedPrompt }));
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveIntention() {
    if (!selectedTopic) return;
    setSaving(true);
    try {
      await fetch("/api/prompt-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "save", topic_slug: selectedTopic, topic_intention: editedIntention })
      });
      setSavedIntentions(prev => ({ ...prev, [selectedTopic]: editedIntention }));
      setTopicIntentions(prev => ({ ...prev, [selectedTopic]: editedIntention }));
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  }

  // ============================================
  // UI HELPERS
  // ============================================

  function toggleSection(section: string) {
    setExpandedSections(prev => {
      const next = new Set(prev);
      next.has(section) ? next.delete(section) : next.add(section);
      return next;
    });
  }

  function toggleQueueTopic(topic: string) {
    setCollapsedQueueTopics(prev => {
      const next = new Set(prev);
      next.has(topic) ? next.delete(topic) : next.add(topic);
      return next;
    });
  }

  function toggleArticle(id: string) {
    setSelectedArticles(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function selectAllInTopic(topic: string) {
    const articles = queue[topic] || [];
    setSelectedArticles(prev => {
      const next = new Set(prev);
      articles.forEach(a => next.add(a.id));
      return next;
    });
    setSelectedTopic(topic);
  }

  function togglePipelineTopic(topic: string) {
    setParams(prev => ({
      ...prev,
      topics_enabled: { ...prev.topics_enabled, [topic]: !prev.topics_enabled[topic] }
    }));
  }

  function updateParam<K extends keyof PipelineParams>(key: K, value: PipelineParams[K]) {
    setParams(prev => ({ ...prev, [key]: value }));
  }

  // ============================================
  // RENDER
  // ============================================

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const topics = Object.keys(queue).sort((a, b) => (queue[b]?.length || 0) - (queue[a]?.length || 0));
  const totalArticles = Object.values(queue).flat().length;
  const enabledTopicsCount = Object.values(params.topics_enabled).filter(Boolean).length;
  const hasParamChanges = JSON.stringify(params) !== JSON.stringify(savedParams);
  const hasPromptChanges = editedPrompt !== savedPrompts.dialogue_segment;
  const hasIntentionChanges = selectedTopic && editedIntention !== savedIntentions[selectedTopic];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-xl border-b border-border/50">
        <div className="max-w-[1800px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/dashboard">
              <button className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-card/60 backdrop-blur-xl border border-border/30 text-foreground hover:bg-card/80 hover:border-primary/30 transition-all font-medium text-sm">
                <LayoutDashboard className="w-4 h-4" />
                Dashboard
              </button>
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-cyan-400" />
              </div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
                Production Lab
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{totalArticles} articles en queue</span>
            <button onClick={loadData} className="p-2 rounded-lg hover:bg-background/50 transition-colors" title="Refresh all">
              <RefreshCw className="w-4 h-4 text-muted-foreground" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Layout */}
      <div className="pt-16 h-screen flex">
        
        {/* LEFT SIDEBAR: Articles Queue */}
        <div className="w-80 flex-shrink-0 border-r border-border/30 overflow-y-auto bg-card/30">
          <div className="p-4">
            <h2 className="text-sm font-semibold flex items-center gap-2 mb-4 text-muted-foreground uppercase tracking-wide">
              <FileText className="w-4 h-4" />
              Articles Queue
            </h2>
            <div className="space-y-2">
              {topics.map(topic => {
                const articles = queue[topic] || [];
                const isCollapsed = collapsedQueueTopics.has(topic);
                const selectedCount = articles.filter(a => selectedArticles.has(a.id)).length;
                return (
                  <div key={topic} className="border border-border/30 rounded-xl overflow-hidden bg-background/50">
                    <button onClick={() => toggleQueueTopic(topic)} className="w-full flex items-center justify-between p-2.5 hover:bg-background/80 transition-colors">
                      <div className="flex items-center gap-2">
                        {isCollapsed ? <ChevronRight className="w-3 h-3 text-muted-foreground" /> : <ChevronDown className="w-3 h-3 text-muted-foreground" />}
                        <span className="font-medium text-xs uppercase">{topic}</span>
                        <span className="text-xs text-muted-foreground">({articles.length})</span>
                        {selectedCount > 0 && <span className="px-1.5 py-0.5 rounded-full bg-primary/20 text-primary text-[10px]">{selectedCount}</span>}
                      </div>
                      <button onClick={(e) => { e.stopPropagation(); selectAllInTopic(topic); }} className="text-[10px] text-primary hover:underline">Select all</button>
                    </button>
                    {!isCollapsed && (
                      <div className="divide-y divide-border/20">
                        {articles.map(article => (
                          <label key={article.id} className="flex items-start gap-2 p-2 hover:bg-background/50 cursor-pointer transition-colors">
                            <input type="checkbox" checked={selectedArticles.has(article.id)} onChange={() => toggleArticle(article.id)} className="mt-0.5 w-3.5 h-3.5 rounded border-border/50 bg-background/50 text-primary focus:ring-primary/50" />
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-medium truncate">{article.title}</p>
                              <p className="text-[10px] text-muted-foreground truncate">{article.source_name}</p>
                            </div>
                            <a href={article.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="p-0.5 hover:bg-background rounded">
                              <ExternalLink className="w-3 h-3 text-muted-foreground" />
                            </a>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* CENTER: Pipeline & Prompts */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto p-6 space-y-4">
            
            {/* 1. FETCH PARAMETERS */}
            <AccordionSection title="1. Fetch Parameters" icon={<Filter className="w-4 h-4 text-blue-400" />} expanded={expandedSections.has("fetch-params")} onToggle={() => toggleSection("fetch-params")} badge={hasParamChanges ? "Modified" : undefined}>
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-muted-foreground mb-2 block">Format</label>
                  <div className="flex gap-2">
                    <button onClick={() => setFormat("flash")} className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${format === "flash" ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-background/50 text-muted-foreground border border-border/30 hover:bg-background/80"}`}>Flash (4min)</button>
                    <button onClick={() => setFormat("digest")} className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${format === "digest" ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-background/50 text-muted-foreground border border-border/30 hover:bg-background/80"}`}>Digest (15min)</button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Flash Segments</label>
                    <input type="number" value={params.flash_segment_count} onChange={(e) => updateParam("flash_segment_count", parseInt(e.target.value) || 0)} className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Digest Segments</label>
                    <input type="number" value={params.digest_segment_count} onChange={(e) => updateParam("digest_segment_count", parseInt(e.target.value) || 0)} className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Min Cluster Size</label>
                    <input type="number" value={params.min_cluster_size} onChange={(e) => updateParam("min_cluster_size", parseInt(e.target.value) || 0)} className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">Bing Threshold</label>
                    <input type="number" value={params.bing_backup_threshold} onChange={(e) => updateParam("bing_backup_threshold", parseInt(e.target.value) || 0)} className="w-full p-2 bg-background/50 border border-border/50 rounded-lg text-sm" />
                  </div>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-2 block">Topics ({enabledTopicsCount}/15 enabled)</label>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(params.topics_enabled).map(([topic, enabled]) => (
                      <button key={topic} onClick={() => togglePipelineTopic(topic)} className={`px-2 py-1 rounded text-xs font-medium transition-colors ${enabled ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-background/50 text-muted-foreground border border-border/30"}`}>{topic}</button>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 pt-2">
                  <button onClick={runFetch} disabled={pipelineLoading} className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30 disabled:opacity-50 transition-all font-medium text-sm">
                    {pipelineLoading && currentStep === "fetch" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Filter className="w-4 h-4" />}
                    Fetch
                  </button>
                  <button onClick={runFullPipeline} disabled={pipelineLoading} className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 text-white font-medium text-sm hover:opacity-90 disabled:opacity-50 transition-all">
                    {pipelineLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    Run All
                  </button>
                </div>
              </div>
            </AccordionSection>

            {/* Fetch Results */}
            {fetchResult && (
              <AccordionSection title="Fetch Results" icon={<Filter className="w-4 h-4 text-blue-400" />} expanded={expandedSections.has("fetch-results")} onToggle={() => toggleSection("fetch-results")} stats={`${fetchResult.stats.total_articles || 0} articles`}>
                <div className="space-y-3">
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(fetchResult.stats.by_topic || {}).map(([topic, count]) => (
                      <span key={topic} className="px-2 py-1 bg-blue-500/10 text-blue-400 rounded text-xs">{topic}: {String(count)}</span>
                    ))}
                  </div>
                  {fetchResult.exclusions.length > 0 && <ExclusionsList exclusions={fetchResult.exclusions} />}
                  <button onClick={runCluster} disabled={pipelineLoading} className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-purple-500/20 text-purple-400 border border-purple-500/30 hover:bg-purple-500/30 disabled:opacity-50 transition-all font-medium text-sm">
                    {pipelineLoading && currentStep === "cluster" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Layers className="w-4 h-4" />}
                    2. Cluster
                  </button>
                </div>
              </AccordionSection>
            )}

            {/* Cluster Results */}
            {clusterResult && (
              <AccordionSection title="Cluster Results" icon={<Layers className="w-4 h-4 text-purple-400" />} expanded={expandedSections.has("cluster-results")} onToggle={() => toggleSection("cluster-results")} stats={`${clusterResult.stats.clusters_formed || 0} clusters`}>
                <div className="space-y-3">
                  {clusterResult.clusters && clusterResult.clusters.length > 0 && (
                    <div className="space-y-2 max-h-[400px] overflow-y-auto">
                      {clusterResult.clusters.map((cluster, i) => (
                        <ClusterCard key={i} cluster={cluster} />
                      ))}
                    </div>
                  )}
                  {clusterResult.exclusions.length > 0 && <ExclusionsList exclusions={clusterResult.exclusions} />}
                  <button onClick={runSelect} disabled={pipelineLoading} className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 disabled:opacity-50 transition-all font-medium text-sm">
                    {pipelineLoading && currentStep === "select" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Target className="w-4 h-4" />}
                    3. Select
                  </button>
                </div>
              </AccordionSection>
            )}

            {/* Select Results */}
            {selectResult && (
              <AccordionSection title="Selection Results" icon={<Target className="w-4 h-4 text-emerald-400" />} expanded={expandedSections.has("select-results")} onToggle={() => toggleSection("select-results")} stats={`${selectResult.stats.segments_created || 0} segments`}>
                <div className="space-y-3">
                  {selectResult.segments && selectResult.segments.length > 0 && (
                    <div className="space-y-2 max-h-[400px] overflow-y-auto">
                      {selectResult.segments.map((seg, i) => (
                        <SegmentCard key={i} segment={seg} />
                      ))}
                    </div>
                  )}
                  {selectResult.exclusions.length > 0 && <ExclusionsList exclusions={selectResult.exclusions} />}
                </div>
              </AccordionSection>
            )}

            {/* 4. PROMPTS */}
            <AccordionSection title="4. Prompts" icon={<FileText className="w-4 h-4 text-cyan-400" />} expanded={expandedSections.has("prompts")} onToggle={() => toggleSection("prompts")} badge={hasPromptChanges ? "Modified" : undefined}>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs text-muted-foreground">Main Dialogue Prompt</label>
                    <button onClick={handleSavePrompt} disabled={saving || !hasPromptChanges} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs">
                      {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                      Save
                    </button>
                  </div>
                  <textarea value={editedPrompt} onChange={(e) => setEditedPrompt(e.target.value)} className="w-full h-40 p-3 bg-background/50 border border-border/50 rounded-xl text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-primary/50" placeholder="Main dialogue prompt..." />
                  <p className="mt-1 text-[10px] text-muted-foreground">Variables: {"{title}"}, {"{content}"}, {"{word_count}"}, {"{topic_intention}"}, {"{style}"}</p>
                </div>
              </div>
            </AccordionSection>

            {/* 5. TOPIC INTENTION */}
            <AccordionSection title="5. Topic Intention" icon={<Zap className="w-4 h-4 text-amber-400" />} expanded={expandedSections.has("intention")} onToggle={() => toggleSection("intention")} badge={hasIntentionChanges ? "Modified" : undefined}>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <select value={selectedTopic} onChange={(e) => setSelectedTopic(e.target.value)} className="flex-1 mr-2 p-2 bg-background/50 border border-border/50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50">
                    <option value="">Select a topic...</option>
                    {topics.map(topic => <option key={topic} value={topic}>{topic.toUpperCase()} ({queue[topic]?.length || 0})</option>)}
                  </select>
                  <button onClick={handleSaveIntention} disabled={saving || !hasIntentionChanges} className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs">
                    {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    Save
                  </button>
                </div>
                <textarea value={editedIntention} onChange={(e) => setEditedIntention(e.target.value)} className="w-full h-28 p-3 bg-background/50 border border-border/50 rounded-xl text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-primary/50" placeholder="Editorial angle for this topic..." />
              </div>
            </AccordionSection>

            {/* 6. GENERATE */}
            <AccordionSection title="6. Generate Script" icon={<Sparkles className="w-4 h-4 text-purple-400" />} expanded={expandedSections.has("generate")} onToggle={() => toggleSection("generate")}>
              <div className="space-y-4">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" checked={useEnrichment} onChange={(e) => setUseEnrichment(e.target.checked)} className="w-4 h-4 rounded border-border/50 bg-background/50 text-primary focus:ring-primary/50" />
                  <span className="text-sm">Use Perplexity enrichment</span>
                </label>
                <p className="text-xs text-muted-foreground">Adds web search context to the article (slower but richer)</p>
                <button onClick={handleGenerate} disabled={generating || selectedArticles.size === 0} className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-purple-500 text-white font-semibold hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
                  {generating ? <><Loader2 className="w-5 h-5 animate-spin" />Generating...</> : <><Send className="w-5 h-5" />Generate Script ({selectedArticles.size} article{selectedArticles.size > 1 ? "s" : ""})</>}
                </button>
              </div>
            </AccordionSection>

            {/* Error display */}
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                <p className="text-red-400 text-sm flex items-center gap-2"><XCircle className="w-4 h-4" />{error}</p>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT PANEL: Results */}
        <div className="w-[450px] flex-shrink-0 border-l border-border/30 overflow-y-auto bg-card/30">
          <div className="p-4">
            <h2 className="text-sm font-semibold flex items-center gap-2 mb-4 text-muted-foreground uppercase tracking-wide">
              <Check className="w-4 h-4" />
              Output
            </h2>

            {!result && !generating && (
              <div className="text-center py-12">
                <Sparkles className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                <p className="text-muted-foreground text-sm">Select articles and generate a script to see results here</p>
              </div>
            )}

            {generating && (
              <div className="text-center py-12">
                <Loader2 className="w-12 h-12 text-primary animate-spin mx-auto mb-4" />
                <p className="text-muted-foreground text-sm">Generating script...</p>
              </div>
            )}

            {result && (
              <div className="space-y-4">
                <div className="flex items-center gap-4 p-3 bg-background/50 rounded-xl text-xs">
                  <span className="flex items-center gap-1"><FileText className="w-3 h-3 text-muted-foreground" />{result.word_count} words</span>
                  <span className="flex items-center gap-1"><Clock className="w-3 h-3 text-muted-foreground" />{result.generation_time_ms}ms</span>
                  <span className="text-muted-foreground">Topic: <strong className="text-foreground">{result.topic}</strong></span>
                </div>

                {result.enriched_context && (
                  <div className="p-3 bg-purple-500/10 border border-purple-500/30 rounded-xl">
                    <h3 className="text-xs font-semibold text-purple-400 mb-2 flex items-center gap-2"><Sparkles className="w-3 h-3" />Perplexity Context</h3>
                    <p className="text-xs text-foreground/80 whitespace-pre-wrap max-h-32 overflow-y-auto">{result.enriched_context}</p>
                  </div>
                )}

                <div className="p-3 bg-background/50 border border-border/30 rounded-xl">
                  <h3 className="text-xs font-semibold text-foreground mb-2">Generated Script</h3>
                  <pre className="text-xs text-foreground/90 whitespace-pre-wrap font-mono leading-relaxed max-h-[calc(100vh-400px)] overflow-y-auto">{result.script}</pre>
                </div>

                <div className="text-xs text-muted-foreground">Sources: {result.sources?.join(", ")}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================
// SUB-COMPONENTS
// ============================================

function AccordionSection({ title, icon, expanded, onToggle, children, badge, stats }: { 
  title: string; icon: React.ReactNode; expanded: boolean; onToggle: () => void; children: React.ReactNode; badge?: string; stats?: string;
}) {
  return (
    <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl overflow-hidden">
      <button onClick={onToggle} className="w-full flex items-center justify-between p-4 hover:bg-background/30 transition-colors">
        <div className="flex items-center gap-3">
          {icon}
          <h3 className="font-semibold text-sm">{title}</h3>
          {badge && <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 text-[10px] font-medium">{badge}</span>}
          {stats && <span className="px-2 py-0.5 rounded bg-background/50 text-muted-foreground text-[10px]">{stats}</span>}
        </div>
        {expanded ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
      </button>
      {expanded && <div className="px-4 pb-4 border-t border-border/20 pt-4">{children}</div>}
    </div>
  );
}

function ExclusionsList({ exclusions }: { exclusions: Exclusion[] }) {
  const [showAll, setShowAll] = useState(false);
  const displayedExclusions = showAll ? exclusions : exclusions.slice(0, 3);

  return (
    <div>
      <h4 className="text-xs font-medium mb-2 flex items-center gap-2 text-amber-400"><AlertTriangle className="w-3 h-3" />Exclusions ({exclusions.length})</h4>
      <div className="space-y-1">
        {displayedExclusions.map((exc, i) => (
          <div key={i} className="text-[10px] p-2 bg-amber-500/10 rounded border border-amber-500/20">
            <span className="font-medium text-amber-400">{exc.type}</span>
            {exc.topic && <span className="text-muted-foreground"> • {exc.topic}</span>}
            <p className="text-muted-foreground mt-0.5 truncate">{exc.reason}</p>
          </div>
        ))}
      </div>
      {exclusions.length > 3 && <button onClick={() => setShowAll(!showAll)} className="text-[10px] text-amber-400 mt-1 hover:underline">{showAll ? "Show less" : `Show all ${exclusions.length}`}</button>}
    </div>
  );
}

function ClusterCard({ cluster }: { cluster: Cluster }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-background/30 rounded-lg border border-border/20 overflow-hidden">
      <button 
        onClick={() => setExpanded(!expanded)}
        className="w-full p-2 flex items-center justify-between hover:bg-background/50 transition-colors"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {expanded ? <ChevronDown className="w-3 h-3 text-muted-foreground flex-shrink-0" /> : <ChevronRight className="w-3 h-3 text-muted-foreground flex-shrink-0" />}
          <span className="text-xs uppercase text-purple-400 font-medium">{cluster.topic}</span>
          <span className="text-xs text-muted-foreground flex-shrink-0">{cluster.size} articles</span>
        </div>
      </button>
      <p className="px-2 pb-2 text-xs truncate text-muted-foreground">{cluster.representative_title}</p>
      
      {expanded && cluster.articles && cluster.articles.length > 0 && (
        <div className="border-t border-border/20 divide-y divide-border/10">
          {cluster.articles.map((article, i) => (
            <div key={i} className="px-3 py-2 flex items-start gap-2 hover:bg-background/30">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium">{article.title}</p>
                <p className="text-[10px] text-muted-foreground">{article.source_name}</p>
              </div>
              {article.url && (
                <a href={article.url} target="_blank" rel="noopener noreferrer" className="p-1 hover:bg-background/50 rounded flex-shrink-0">
                  <ExternalLink className="w-3 h-3 text-muted-foreground" />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SegmentCard({ segment }: { segment: Segment }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-emerald-500/10 rounded-lg border border-emerald-500/20 overflow-hidden">
      <button 
        onClick={() => setExpanded(!expanded)}
        className="w-full p-2 flex items-center justify-between hover:bg-emerald-500/20 transition-colors"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {expanded ? <ChevronDown className="w-3 h-3 text-muted-foreground flex-shrink-0" /> : <ChevronRight className="w-3 h-3 text-muted-foreground flex-shrink-0" />}
          <span className="text-xs uppercase text-emerald-400 font-medium">{segment.topic}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded ${segment.type === "cluster" ? "bg-purple-500/20 text-purple-400" : "bg-amber-500/20 text-amber-400"}`}>{segment.type}</span>
          <span className="text-xs text-muted-foreground flex-shrink-0">{segment.articles?.length || 0} articles</span>
        </div>
      </button>
      <p className="px-2 pb-2 text-xs truncate text-muted-foreground">{segment.representative_title}</p>
      
      {expanded && segment.articles && segment.articles.length > 0 && (
        <div className="border-t border-emerald-500/20 divide-y divide-emerald-500/10">
          {segment.articles.map((article, i) => (
            <div key={i} className="px-3 py-2 flex items-start gap-2 hover:bg-emerald-500/10">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium">{article.title}</p>
                <p className="text-[10px] text-muted-foreground">{article.source_name}</p>
              </div>
              {article.url && (
                <a href={article.url} target="_blank" rel="noopener noreferrer" className="p-1 hover:bg-background/50 rounded flex-shrink-0">
                  <ExternalLink className="w-3 h-3 text-muted-foreground" />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
