"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Settings,
  Save,
  RotateCcw,
  Loader2,
  Check,
  Database,
  Brain,
  Zap,
  Layers,
  BarChart3,
  Search,
  FileText,
  Mic,
  HardDrive,
  Trash2,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Copy,
  Eye,
  EyeOff
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ============================================
// TYPES
// ============================================

interface Model {
  id: string;
  name: string;
  context: number;
}

interface Article {
  title: string;
  url: string;
  description?: string;
  source_name: string;
  source_tier: string;
  topic: string;
  classified_topic?: string;
  cluster_id?: number;
  embedding?: number[];
}

interface Cluster {
  cluster_id: number;
  articles: Article[];
  authority_count?: number;
  generalist_count?: number;
  corporate_count?: number;
  source_count?: number;
  total_score?: number;
  is_valid?: boolean;
  reason?: string;
}

interface LabConfig {
  topics: string[];
  models: Model[];
  prompts: Record<string, string>;
  params: Record<string, any>;
  default_prompts: Record<string, string>;
  default_params: Record<string, any>;
}

// ============================================
// STEPS
// ============================================

const STEPS = [
  { id: "fetch", name: "1. Fetch", icon: Database, color: "text-blue-500", hasLLM: false },
  { id: "classify", name: "2. Classify", icon: Brain, color: "text-purple-500", hasLLM: true, promptKey: "classification" },
  { id: "embed", name: "3. Embed", icon: Zap, color: "text-yellow-500", hasLLM: false },
  { id: "cluster", name: "4. Cluster", icon: Layers, color: "text-green-500", hasLLM: false },
  { id: "score", name: "5. Score", icon: BarChart3, color: "text-orange-500", hasLLM: false },
  { id: "enrich", name: "6. Enrich", icon: Search, color: "text-cyan-500", hasLLM: false },
  { id: "summarize", name: "7. Summary", icon: FileText, color: "text-pink-500", hasLLM: true, promptKey: "summary" },
  { id: "script", name: "8. Script", icon: Mic, color: "text-red-500", hasLLM: true, promptKey: "script" },
  { id: "store", name: "9. Store", icon: HardDrive, color: "text-gray-500", hasLLM: false },
];

// ============================================
// MAIN COMPONENT
// ============================================

export default function LabV2Page() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";

  // Config
  const [config, setConfig] = useState<LabConfig | null>(null);
  const [isLoadingConfig, setIsLoadingConfig] = useState(true);

  // Current step
  const [activeStep, setActiveStep] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const [stepResults, setStepResults] = useState<Record<string, any>>({});

  // Data through pipeline
  const [articles, setArticles] = useState<Article[]>([]);
  const [classifiedArticles, setClassifiedArticles] = useState<Article[]>([]);
  const [embeddedArticles, setEmbeddedArticles] = useState<Article[]>([]);
  const [clusters, setClusters] = useState<Record<string, Article[]>>({});
  const [scoredClusters, setScoredClusters] = useState<Cluster[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<Cluster | null>(null);
  const [enrichment, setEnrichment] = useState<{
    hook: string;
    thesis: string;
    antithesis: string;
    key_data: string;
    context: string;
    citations: string[];
  }>({ hook: "", thesis: "", antithesis: "", key_data: "", context: "", citations: [] });
  const [summary, setSummary] = useState<any>(null);
  const [script, setScript] = useState<any>(null);

  // Models per step
  const [stepModels, setStepModels] = useState({
    classify: "llama-3.3-70b-versatile",
    summarize: "llama-3.3-70b-versatile",
    script: "llama-3.3-70b-versatile",
  });

  // Prompts
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [showPrompt, setShowPrompt] = useState(false);

  // Params
  const [params, setParams] = useState<Record<string, any>>({});
  const [showParams, setShowParams] = useState(false);

  // ============================================
  // LOAD CONFIG
  // ============================================

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/lab/v2/config`);
      const data = await res.json();
      if (data.success) {
        setConfig(data);
        setPrompts(data.prompts || data.default_prompts);
        setParams(data.params || data.default_params);
      }
    } catch (e) {
      toast.error("Failed to load config");
    } finally {
      setIsLoadingConfig(false);
    }
  };

  // ============================================
  // RUN STEPS
  // ============================================

  const runStep = async () => {
    const step = STEPS[activeStep];
    setIsRunning(true);

    try {
      let result: any;

      switch (step.id) {
        case "fetch":
          result = await runFetch();
          if (result.articles) setArticles(result.articles);
          break;

        case "classify":
          result = await runClassify();
          if (result.classified_articles) setClassifiedArticles(result.classified_articles);
          break;

        case "embed":
          result = await runEmbed();
          if (result.articles) setEmbeddedArticles(result.articles);
          break;

        case "cluster":
          result = await runCluster();
          if (result.clusters) setClusters(result.clusters);
          break;

        case "score":
          result = await runScore();
          if (result.scored_clusters) {
            setScoredClusters(result.scored_clusters);
            const firstValid = result.valid_clusters?.[0];
            if (firstValid) setSelectedCluster(firstValid);
          }
          break;

        case "enrich":
          result = await runEnrich();
          if (result.hook || result.thesis || result.context) {
            setEnrichment({
              hook: result.hook || "",
              thesis: result.thesis || "",
              antithesis: result.antithesis || "",
              key_data: result.key_data || "",
              context: result.context || "",
              citations: result.citations || []
            });
          }
          break;

        case "summarize":
          result = await runSummarize();
          if (result.summary_markdown) setSummary(result);
          break;

        case "script":
          result = await runScript();
          if (result.script) setScript(result);
          break;

        case "store":
          result = await runStore();
          break;
      }

      setStepResults(prev => ({ ...prev, [step.id]: result }));

      if (result.error) {
        toast.error(result.error);
      } else {
        toast.success(`${step.name} completed in ${result.duration_ms}ms`);
      }

    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setIsRunning(false);
    }
  };

  const runFetch = async () => {
    const res = await fetch(`${backendUrl}/api/lab/v2/fetch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topics: config?.topics,
        max_per_source: params.max_articles_per_source || 10
      })
    });
    return res.json();
  };

  const runClassify = async () => {
    const res = await fetch(`${backendUrl}/api/lab/v2/classify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        articles,
        topics: config?.topics,
        model: stepModels.classify,
        prompt_template: prompts.classification
      })
    });
    return res.json();
  };

  const runEmbed = async () => {
    const input = classifiedArticles.length > 0 ? classifiedArticles : articles;
    const res = await fetch(`${backendUrl}/api/lab/v2/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ articles: input })
    });
    return res.json();
  };

  const runCluster = async () => {
    const res = await fetch(`${backendUrl}/api/lab/v2/cluster`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        articles: embeddedArticles,
        eps: params.dbscan_eps || 0.65,
        min_samples: params.dbscan_min_samples || 2
      })
    });
    return res.json();
  };

  const runScore = async () => {
    const res = await fetch(`${backendUrl}/api/lab/v2/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clusters, params })
    });
    return res.json();
  };

  const runEnrich = async () => {
    if (!selectedCluster) return { error: "Select a cluster first" };
    const res = await fetch(`${backendUrl}/api/lab/v2/enrich`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cluster: selectedCluster })
    });
    return res.json();
  };

  const runSummarize = async () => {
    if (!selectedCluster) return { error: "Select a cluster first" };
    const res = await fetch(`${backendUrl}/api/lab/v2/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cluster: selectedCluster,
        context: enrichment.context,
        model: stepModels.summarize,
        prompt_template: prompts.summary
      })
    });
    return res.json();
  };

  const runScript = async () => {
    if (!summary) return { error: "Generate summary first" };
    
    // Get enrichment from previous step
    const enrichment = stepResults.enrich?.enrichment || {
      hook: stepResults.enrich?.hook || "",
      thesis: stepResults.enrich?.thesis || "",
      antithesis: stepResults.enrich?.antithesis || "",
      key_data: stepResults.enrich?.key_data || "",
    };
    
    const res = await fetch(`${backendUrl}/api/lab/v2/script`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        summary: {
          ...summary,
          cluster_name: selectedCluster?.name || summary.title,
          articles: selectedCluster?.articles || []
        },
        enrichment,
        model: stepModels.script,
        prompt_template: prompts.script,
        word_count: 375  // ~2.5 min per cluster
      })
    });
    return res.json();
  };

  const runStore = async () => {
    const res = await fetch(`${backendUrl}/api/lab/v2/store`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        articles: embeddedArticles,
        clusters: scoredClusters.filter(c => c.is_valid),
        summaries: summary ? [summary] : [],
        dry_run: false
      })
    });
    return res.json();
  };

  // ============================================
  // SAVE HANDLERS
  // ============================================

  const savePrompt = async (key: string) => {
    const res = await fetch(`${backendUrl}/api/lab/v2/prompts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: key, template: prompts[key] })
    });
    const data = await res.json();
    if (data.success) toast.success("Prompt saved");
    else toast.error(data.error);
  };

  const saveParams = async () => {
    const res = await fetch(`${backendUrl}/api/lab/v2/params`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params })
    });
    const data = await res.json();
    if (data.success) toast.success("Params saved");
    else toast.error(data.error);
  };

  // ============================================
  // RESET
  // ============================================

  const resetPipeline = () => {
    setActiveStep(0);
    setStepResults({});
    setArticles([]);
    setClassifiedArticles([]);
    setEmbeddedArticles([]);
    setClusters({});
    setScoredClusters([]);
    setSelectedCluster(null);
    setEnrichment({ hook: "", thesis: "", antithesis: "", key_data: "", context: "", citations: [] });
    setSummary(null);
    setScript(null);
    toast.info("Pipeline reset");
  };

  // ============================================
  // RENDER
  // ============================================

  if (isLoadingConfig) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const currentStep = STEPS[activeStep];
  const currentResult = stepResults[currentStep.id];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="sticky top-0 z-50 bg-card border-b border-border">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Prompt Lab V2</h1>
              <p className="text-sm text-muted-foreground">Pipeline B2B Intelligence</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowParams(!showParams)}
                className={cn(
                  "px-3 py-2 rounded-lg text-sm flex items-center gap-2",
                  showParams ? "bg-primary text-primary-foreground" : "bg-muted"
                )}
              >
                <Settings className="w-4 h-4" />
                Params
              </button>
              <button
                onClick={resetPipeline}
                className="px-3 py-2 rounded-lg text-sm bg-muted flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" />
                Reset
              </button>
            </div>
          </div>

          {/* Steps nav */}
          <div className="flex gap-1 mt-4 overflow-x-auto pb-2">
            {STEPS.map((step, i) => {
              const Icon = step.icon;
              const hasResult = !!stepResults[step.id];
              const isActive = activeStep === i;

              return (
                <button
                  key={step.id}
                  onClick={() => setActiveStep(i)}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-all",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : hasResult
                      ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
                      : "bg-muted/50 text-muted-foreground hover:bg-muted"
                  )}
                >
                  {hasResult ? <Check className="w-4 h-4" /> : <Icon className={cn("w-4 h-4", step.color)} />}
                  <span className="hidden sm:inline">{step.name}</span>
                  <span className="sm:hidden">{i + 1}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Params panel */}
      <AnimatePresence>
        {showParams && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-b border-border overflow-hidden"
          >
            <div className="max-w-7xl mx-auto px-4 py-4">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground">DBSCAN eps</label>
                  <input
                    type="number"
                    step="0.05"
                    value={params.dbscan_eps || 0.65}
                    onChange={e => setParams(p => ({ ...p, dbscan_eps: parseFloat(e.target.value) }))}
                    className="w-full mt-1 px-3 py-2 bg-muted rounded text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Min samples</label>
                  <input
                    type="number"
                    value={params.dbscan_min_samples || 2}
                    onChange={e => setParams(p => ({ ...p, dbscan_min_samples: parseInt(e.target.value) }))}
                    className="w-full mt-1 px-3 py-2 bg-muted rounded text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Min authority</label>
                  <input
                    type="number"
                    value={params.min_authority_sources || 1}
                    onChange={e => setParams(p => ({ ...p, min_authority_sources: parseInt(e.target.value) }))}
                    className="w-full mt-1 px-3 py-2 bg-muted rounded text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Min generalist</label>
                  <input
                    type="number"
                    value={params.min_generalist_sources || 5}
                    onChange={e => setParams(p => ({ ...p, min_generalist_sources: parseInt(e.target.value) }))}
                    className="w-full mt-1 px-3 py-2 bg-muted rounded text-sm"
                  />
                </div>
                <div className="flex items-end">
                  <button onClick={saveParams} className="px-4 py-2 bg-primary text-primary-foreground rounded text-sm">
                    Save Params
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left panel - Controls */}
          <div className="lg:col-span-4 space-y-4">
            {/* Step info */}
            <div className="bg-card rounded-xl border p-6">
              <div className="flex items-center gap-3 mb-4">
                {(() => {
                  const Icon = currentStep.icon;
                  return <Icon className={cn("w-8 h-8", currentStep.color)} />;
                })()}
                <div>
                  <h2 className="text-xl font-bold">{currentStep.name}</h2>
                  <p className="text-sm text-muted-foreground">
                    {currentStep.id === "fetch" && "Récupérer les articles des sources MVP"}
                    {currentStep.id === "classify" && "Classifier les articles par topic"}
                    {currentStep.id === "embed" && "Générer les embeddings OpenAI"}
                    {currentStep.id === "cluster" && "Grouper avec DBSCAN"}
                    {currentStep.id === "score" && "Scorer avec Radar + Loupe"}
                    {currentStep.id === "enrich" && "Enrichir avec Perplexity"}
                    {currentStep.id === "summarize" && "Générer le résumé structuré"}
                    {currentStep.id === "script" && "Générer le script podcast"}
                    {currentStep.id === "store" && "Sauvegarder en base"}
                  </p>
                </div>
              </div>

              {/* Model selector */}
              {currentStep.hasLLM && (
                <div className="mb-4">
                  <label className="text-xs text-muted-foreground mb-1 block">Model Groq</label>
                  <select
                    value={stepModels[currentStep.id as keyof typeof stepModels]}
                    onChange={e => setStepModels(m => ({ ...m, [currentStep.id]: e.target.value }))}
                    className="w-full px-3 py-2 bg-muted rounded text-sm"
                  >
                    {config?.models.map(m => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Cluster selector (steps 6-8) */}
              {["enrich", "summarize", "script"].includes(currentStep.id) && scoredClusters.length > 0 && (
                <div className="mb-4">
                  <label className="text-xs text-muted-foreground mb-1 block">Cluster sélectionné</label>
                  <select
                    value={selectedCluster?.cluster_id ?? ""}
                    onChange={e => {
                      const c = scoredClusters.find(x => x.cluster_id === parseInt(e.target.value));
                      setSelectedCluster(c || null);
                    }}
                    className="w-full px-3 py-2 bg-muted rounded text-sm"
                  >
                    {scoredClusters.filter(c => c.is_valid).map(c => (
                      <option key={c.cluster_id} value={c.cluster_id}>
                        Cluster {c.cluster_id} — Score {c.total_score} ({c.articles.length} articles)
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Status info */}
              <div className="mb-4 text-sm text-muted-foreground">
                {currentStep.id === "fetch" && <p>Topics: {config?.topics.join(", ")}</p>}
                {currentStep.id === "classify" && <p>{articles.length} articles à classifier</p>}
                {currentStep.id === "embed" && <p>{classifiedArticles.length || articles.length} articles</p>}
                {currentStep.id === "cluster" && <p>{embeddedArticles.length} articles avec embeddings</p>}
                {currentStep.id === "score" && <p>{Object.keys(clusters).length} clusters</p>}
                {currentStep.id === "enrich" && selectedCluster && <p>Cluster {selectedCluster.cluster_id}</p>}
                {currentStep.id === "summarize" && selectedCluster && <p>Cluster {selectedCluster.cluster_id}</p>}
                {currentStep.id === "script" && summary && <p>Summary ready</p>}
              </div>

              {/* Run button */}
              <button
                onClick={runStep}
                disabled={isRunning}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary text-primary-foreground rounded-xl font-medium disabled:opacity-50"
              >
                {isRunning ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Running...</>
                ) : (
                  <><Play className="w-4 h-4" /> Run {currentStep.name}</>
                )}
              </button>

              {/* Result meta */}
              {currentResult && (
                <div className="mt-4 p-3 bg-muted/50 rounded-lg text-xs">
                  <p>Duration: {currentResult.duration_ms}ms</p>
                  {currentResult.model && <p>Model: {currentResult.model}</p>}
                  {currentResult.count !== undefined && <p>Count: {currentResult.count}</p>}
                </div>
              )}
            </div>

            {/* Prompt editor */}
            {currentStep.hasLLM && currentStep.promptKey && (
              <div className="bg-card rounded-xl border p-6">
                <div className="flex items-center justify-between mb-3">
                  <button
                    onClick={() => setShowPrompt(!showPrompt)}
                    className="flex items-center gap-2 text-sm font-medium"
                  >
                    {showPrompt ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    Prompt Template
                  </button>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPrompts(p => ({ ...p, [currentStep.promptKey!]: config?.default_prompts[currentStep.promptKey!] || "" }))}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Reset
                    </button>
                    <button
                      onClick={() => savePrompt(currentStep.promptKey!)}
                      className="text-xs text-primary flex items-center gap-1"
                    >
                      <Save className="w-3 h-3" /> Save
                    </button>
                  </div>
                </div>
                {showPrompt && (
                  <textarea
                    value={prompts[currentStep.promptKey] || ""}
                    onChange={e => setPrompts(p => ({ ...p, [currentStep.promptKey!]: e.target.value }))}
                    className="w-full h-64 px-3 py-2 bg-muted rounded text-xs font-mono"
                  />
                )}
              </div>
            )}
          </div>

          {/* Right panel - Results */}
          <div className="lg:col-span-8">
            <div className="bg-card rounded-xl border p-6 min-h-[600px]">
              <h3 className="font-semibold mb-4">Results</h3>

              {/* FETCH */}
              {currentStep.id === "fetch" && (
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {articles.length === 0 ? (
                    <p className="text-muted-foreground">Click Run to fetch articles</p>
                  ) : (
                    articles.map((a, i) => (
                      <div key={i} className="flex items-start gap-3 p-3 bg-muted/50 rounded-lg group">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{a.title}</p>
                          <div className="flex items-center gap-2 mt-1 text-xs">
                            <span className="text-muted-foreground">{a.source_name}</span>
                            <span className={cn(
                              "px-2 py-0.5 rounded-full",
                              a.source_tier === "authority" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" :
                              a.source_tier === "corporate" ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400" :
                              "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                            )}>{a.source_tier}</span>
                            <span className="px-2 py-0.5 bg-primary/10 text-primary rounded-full">{a.topic}</span>
                          </div>
                        </div>
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1 text-muted-foreground hover:text-primary"
                          title="Open article"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                        <button
                          onClick={() => setArticles(arr => arr.filter(x => x.url !== a.url))}
                          className="opacity-0 group-hover:opacity-100 p-1 text-red-500"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* CLASSIFY */}
              {currentStep.id === "classify" && (
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {currentResult?.results?.map((r: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                      <div className={cn(
                        "w-2 h-2 rounded-full",
                        r.classified_topic === "discard" ? "bg-red-500" : "bg-green-500"
                      )} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">{r.title}</p>
                        <p className="text-xs text-muted-foreground">{r.source}</p>
                      </div>
                      <span className={cn(
                        "text-xs px-2 py-0.5 rounded-full",
                        r.classified_topic === "discard" ? "bg-red-100 text-red-700" : "bg-primary/10 text-primary"
                      )}>{r.classified_topic}</span>
                      <span className="text-xs text-muted-foreground">{r.method}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* EMBED */}
              {currentStep.id === "embed" && (
                <div className="p-6 text-center">
                  {currentResult ? (
                    <div>
                      <Check className="w-12 h-12 text-green-500 mx-auto mb-4" />
                      <p className="text-lg font-medium">{currentResult.count} embeddings generated</p>
                      <p className="text-sm text-muted-foreground">Dimensions: {currentResult.dimensions}</p>
                    </div>
                  ) : (
                    <p className="text-muted-foreground">Run to generate embeddings</p>
                  )}
                </div>
              )}

              {/* CLUSTER */}
              {currentStep.id === "cluster" && (
                <div className="space-y-3 max-h-[500px] overflow-y-auto">
                  {currentResult?.cluster_info?.map((c: any) => (
                    <div key={c.cluster_id} className={cn(
                      "p-4 rounded-lg border",
                      c.cluster_id === -1 ? "bg-muted/30 border-dashed" : "bg-muted/50"
                    )}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium">{c.name || c.label}</span>
                        <span className="text-sm text-muted-foreground">{c.count} articles</span>
                      </div>
                      {c.tiers && (
                        <div className="flex gap-2 mb-2">
                          {c.tiers.map((t: string) => (
                            <span key={t} className="text-xs px-2 py-0.5 bg-background rounded">{t}</span>
                          ))}
                        </div>
                      )}
                      <div className="text-xs text-muted-foreground space-y-1">
                        {c.articles.slice(0, 5).map((a: any, i: number) => (
                          <div key={i} className="flex items-center gap-2">
                            <p className="truncate flex-1">• {a.title}</p>
                            {a.url && (
                              <a
                                href={a.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-primary hover:text-primary/80 shrink-0"
                              >
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                          </div>
                        ))}
                        {c.articles.length > 5 && <p>+{c.articles.length - 5} more</p>}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* SCORE */}
              {currentStep.id === "score" && (
                <div className="space-y-3 max-h-[500px] overflow-y-auto">
                  {scoredClusters.map(c => (
                    <button
                      key={c.cluster_id}
                      onClick={() => setSelectedCluster(c)}
                      className={cn(
                        "w-full text-left p-4 rounded-lg border transition-all",
                        selectedCluster?.cluster_id === c.cluster_id
                          ? "border-primary bg-primary/5"
                          : c.is_valid
                          ? "border-green-500/30 bg-green-50 dark:bg-green-900/10"
                          : "border-red-500/30 bg-red-50 dark:bg-red-900/10"
                      )}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium">
                          {(c as any).name || `Cluster ${c.cluster_id}`}
                        </span>
                        <span className={cn("text-xl font-bold", c.is_valid ? "text-green-600" : "text-red-600")}>
                          {c.total_score}
                        </span>
                      </div>
                      <div className="flex gap-4 text-xs text-muted-foreground mb-2">
                        <span>👑 {c.authority_count} auth</span>
                        <span>📰 {c.generalist_count} gen</span>
                        <span>🏢 {c.corporate_count} corp</span>
                      </div>
                      <p className={cn("text-xs", c.is_valid ? "text-green-600" : "text-red-600")}>{c.reason}</p>
                    </button>
                  ))}
                </div>
              )}

              {/* ENRICH */}
              {currentStep.id === "enrich" && (
                <div className="space-y-4">
                  {stepResults.enrich?.enrichment ? (
                    <>
                      <div className="grid gap-4">
                        {/* Hook */}
                        <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
                          <h4 className="font-medium text-sm text-yellow-700 dark:text-yellow-400 mb-1">🎣 Hook</h4>
                          <p className="text-sm">{stepResults.enrich.hook || "Non généré"}</p>
                        </div>
                        
                        {/* Thesis */}
                        <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                          <h4 className="font-medium text-sm text-green-700 dark:text-green-400 mb-1">✅ Thèse</h4>
                          <p className="text-sm">{stepResults.enrich.thesis || "Non généré"}</p>
                        </div>
                        
                        {/* Antithesis */}
                        <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                          <h4 className="font-medium text-sm text-red-700 dark:text-red-400 mb-1">⚖️ Antithèse</h4>
                          <p className="text-sm">{stepResults.enrich.antithesis || "Non généré"}</p>
                        </div>
                        
                        {/* Key Data */}
                        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                          <h4 className="font-medium text-sm text-blue-700 dark:text-blue-400 mb-1">📊 Données clés</h4>
                          <p className="text-sm whitespace-pre-wrap">{stepResults.enrich.key_data || "Non généré"}</p>
                        </div>
                        
                        {/* Context */}
                        <div className="p-4 bg-muted/50 rounded-lg">
                          <h4 className="font-medium text-sm mb-1">📝 Contexte</h4>
                          <p className="text-sm">{stepResults.enrich.context || "Non généré"}</p>
                        </div>
                      </div>
                      
                      {stepResults.enrich.citations?.length > 0 && (
                        <div>
                          <h4 className="font-medium text-sm mb-2">Citations</h4>
                          <div className="flex flex-wrap gap-2">
                            {stepResults.enrich.citations.map((url: string, i: number) => (
                              <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary flex items-center gap-1">
                                <ExternalLink className="w-3 h-3" />
                                {new URL(url).hostname}
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  ) : enrichment.context ? (
                    <div className="p-4 bg-muted/50 rounded-lg">
                      <h4 className="font-medium mb-2">Perplexity Context (raw)</h4>
                      <p className="text-sm whitespace-pre-wrap">{enrichment.context}</p>
                    </div>
                  ) : (
                    <p className="text-muted-foreground">Select a cluster and run enrichment</p>
                  )}
                </div>
              )}

              {/* SUMMARIZE */}
              {currentStep.id === "summarize" && (
                <div className="space-y-4">
                  {summary ? (
                    <>
                      <div className="p-4 bg-muted/50 rounded-lg">
                        <h4 className="font-bold text-lg mb-2">{summary.title}</h4>
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                          <pre className="whitespace-pre-wrap text-sm font-sans">{summary.summary_markdown}</pre>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => navigator.clipboard.writeText(summary.summary_markdown)}
                          className="text-xs flex items-center gap-1 text-muted-foreground hover:text-foreground"
                        >
                          <Copy className="w-3 h-3" /> Copy
                        </button>
                      </div>
                    </>
                  ) : (
                    <p className="text-muted-foreground">Select a cluster and generate summary</p>
                  )}
                </div>
              )}

              {/* SCRIPT */}
              {currentStep.id === "script" && (
                <div className="space-y-4">
                  {script ? (
                    <>
                      <div className="p-4 bg-muted/50 rounded-lg">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm text-muted-foreground">~{script.estimated_duration_seconds}s</span>
                          <span className="text-sm text-muted-foreground">{script.word_count} words</span>
                        </div>
                        <p className="text-sm whitespace-pre-wrap">{script.script}</p>
                      </div>
                      <button
                        onClick={() => navigator.clipboard.writeText(script.script)}
                        className="text-xs flex items-center gap-1 text-muted-foreground hover:text-foreground"
                      >
                        <Copy className="w-3 h-3" /> Copy Script
                      </button>
                    </>
                  ) : (
                    <p className="text-muted-foreground">Generate summary first, then script</p>
                  )}
                </div>
              )}

              {/* STORE */}
              {currentStep.id === "store" && (
                <div className="p-6 text-center">
                  {currentResult ? (
                    currentResult.dry_run ? (
                      <div>
                        <p className="text-lg font-medium mb-2">Dry Run Results</p>
                        <p className="text-sm text-muted-foreground">
                          Would store: {currentResult.would_store?.articles} articles, {currentResult.would_store?.clusters} clusters, {currentResult.would_store?.summaries} summaries
                        </p>
                      </div>
                    ) : (
                      <div>
                        <Check className="w-12 h-12 text-green-500 mx-auto mb-4" />
                        <p className="text-lg font-medium">Stored to database</p>
                        <p className="text-sm text-muted-foreground">
                          {currentResult.stored?.articles} articles, {currentResult.stored?.clusters} clusters, {currentResult.stored?.summaries} summaries
                        </p>
                      </div>
                    )
                  ) : (
                    <div>
                      <p className="text-muted-foreground mb-4">Ready to store:</p>
                      <ul className="text-sm space-y-1">
                        <li>{embeddedArticles.length} articles</li>
                        <li>{scoredClusters.filter(c => c.is_valid).length} valid clusters</li>
                        <li>{summary ? 1 : 0} summaries</li>
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
