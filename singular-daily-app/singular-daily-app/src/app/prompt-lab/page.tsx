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
  Settings2
} from "lucide-react";

interface Article {
  id: string;
  title: string;
  source_name: string;
  url: string;
  published_at: string | null;
  keyword: string;
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

export default function PromptLabPage() {
  // State
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  
  // Data
  const [queue, setQueue] = useState<TopicArticles>({});
  const [prompts, setPrompts] = useState<Prompts>({ dialogue_segment: "", dialogue_multi_source: "" });
  const [topicIntentions, setTopicIntentions] = useState<TopicIntentions>({});
  
  // Form state
  const [selectedTopic, setSelectedTopic] = useState<string>("");
  const [selectedArticles, setSelectedArticles] = useState<Set<string>>(new Set());
  const [editedPrompt, setEditedPrompt] = useState<string>("");
  const [editedIntention, setEditedIntention] = useState<string>("");
  const [useEnrichment, setUseEnrichment] = useState(false);
  
  // Results
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Collapsed topics
  const [collapsedTopics, setCollapsedTopics] = useState<Set<string>>(new Set());

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  // Update edited prompt when selected topic changes
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
      // Fetch queue
      const queueRes = await fetch("/api/prompt-lab?action=queue");
      const queueData = await queueRes.json();
      if (queueData.topics) {
        setQueue(queueData.topics);
        // Select first topic with articles
        const firstTopic = Object.keys(queueData.topics).find(t => queueData.topics[t].length > 0);
        if (firstTopic) {
          setSelectedTopic(firstTopic);
        }
      }

      // Fetch prompts
      const promptsRes = await fetch("/api/prompt-lab?action=prompts");
      const promptsData = await promptsRes.json();
      if (promptsData.prompts) {
        setPrompts(promptsData.prompts);
        setEditedPrompt(promptsData.prompts.dialogue_segment);
      }
      if (promptsData.topic_intentions) {
        setTopicIntentions(promptsData.topic_intentions);
      }
    } catch (err) {
      console.error("Failed to load data:", err);
      setError("Failed to load data");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    if (selectedArticles.size === 0) {
      setError("Please select at least one article");
      return;
    }

    setGenerating(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/prompt-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "generate",
          article_ids: Array.from(selectedArticles),
          topic: selectedTopic,
          custom_prompt: editedPrompt !== prompts.dialogue_segment ? editedPrompt : undefined,
          custom_intention: editedIntention !== topicIntentions[selectedTopic] ? editedIntention : undefined,
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

  async function handleSavePrompt() {
    setSaving(true);
    try {
      await fetch("/api/prompt-lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "save",
          prompt_name: "dialogue_segment",
          prompt_content: editedPrompt
        })
      });
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
        body: JSON.stringify({
          action: "save",
          topic_slug: selectedTopic,
          topic_intention: editedIntention
        })
      });
      setTopicIntentions(prev => ({ ...prev, [selectedTopic]: editedIntention }));
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  }

  function toggleArticle(id: string) {
    setSelectedArticles(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleTopic(topic: string) {
    setCollapsedTopics(prev => {
      const next = new Set(prev);
      if (next.has(topic)) {
        next.delete(topic);
      } else {
        next.add(topic);
      }
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

  function formatDate(dateStr: string | null) {
    if (!dateStr) return "Date inconnue";
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    } catch {
      return dateStr;
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const topics = Object.keys(queue).sort((a, b) => (queue[b]?.length || 0) - (queue[a]?.length || 0));
  const totalArticles = Object.values(queue).flat().length;

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
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-cyan-400" />
              </div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
                Prompt Lab
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/pipeline-lab">
              <button className="flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-orange-500/20 to-red-500/20 border border-orange-500/30 text-orange-400 hover:bg-orange-500/30 transition-all font-medium text-sm">
                <Settings2 className="w-4 h-4" />
                Pipeline Lab
              </button>
            </Link>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <FileText className="w-4 h-4" />
              {totalArticles} articles en queue
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="pt-20 pb-12 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
          
          {/* Left column: Prompts */}
          <div className="space-y-6">
            {/* Main Prompt */}
            <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <FileText className="w-5 h-5 text-cyan-400" />
                  Main Prompt
                </h2>
                <button
                  onClick={handleSavePrompt}
                  disabled={saving || editedPrompt === prompts.dialogue_segment}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save
                </button>
              </div>
              <textarea
                value={editedPrompt}
                onChange={(e) => setEditedPrompt(e.target.value)}
                className="w-full h-64 p-4 bg-background/50 border border-border/50 rounded-xl text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="Main dialogue prompt..."
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Variables: {"{title}"}, {"{content}"}, {"{source_label}"}, {"{word_count}"}, {"{topic_intention}"}, {"{style}"}
              </p>
            </div>

            {/* Topic Intention */}
            <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Zap className="w-5 h-5 text-amber-400" />
                  Topic Intention
                </h2>
                <button
                  onClick={handleSaveIntention}
                  disabled={saving || !selectedTopic || editedIntention === topicIntentions[selectedTopic]}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save
                </button>
              </div>
              
              {/* Topic selector */}
              <select
                value={selectedTopic}
                onChange={(e) => setSelectedTopic(e.target.value)}
                className="w-full mb-4 p-3 bg-background/50 border border-border/50 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                <option value="">Select a topic...</option>
                {topics.map(topic => (
                  <option key={topic} value={topic}>
                    {topic.toUpperCase()} ({queue[topic]?.length || 0} articles)
                  </option>
                ))}
              </select>

              <textarea
                value={editedIntention}
                onChange={(e) => setEditedIntention(e.target.value)}
                className="w-full h-32 p-4 bg-background/50 border border-border/50 rounded-xl text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="Editorial angle for this topic..."
              />
            </div>

            {/* Generation Options */}
            <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl p-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-400" />
                Options
              </h2>
              
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useEnrichment}
                  onChange={(e) => setUseEnrichment(e.target.checked)}
                  className="w-5 h-5 rounded border-border/50 bg-background/50 text-primary focus:ring-primary/50"
                />
                <span className="text-sm">Use Perplexity enrichment</span>
              </label>
              <p className="mt-2 text-xs text-muted-foreground ml-8">
                Adds web search context to the article (slower but richer)
              </p>

              {/* Generate button */}
              <button
                onClick={handleGenerate}
                disabled={generating || selectedArticles.size === 0}
                className="mt-6 w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-purple-500 text-white font-semibold hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {generating ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Send className="w-5 h-5" />
                    Generate Script ({selectedArticles.size} article{selectedArticles.size > 1 ? "s" : ""})
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Right column: Articles & Results */}
          <div className="space-y-6">
            {/* Articles Queue */}
            <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <FileText className="w-5 h-5 text-emerald-400" />
                  Articles Queue
                </h2>
                <button
                  onClick={loadData}
                  className="p-2 rounded-lg hover:bg-background/50 transition-colors"
                >
                  <RefreshCw className="w-4 h-4 text-muted-foreground" />
                </button>
              </div>

              <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
                {topics.map(topic => {
                  const articles = queue[topic] || [];
                  const isCollapsed = collapsedTopics.has(topic);
                  const selectedCount = articles.filter(a => selectedArticles.has(a.id)).length;

                  return (
                    <div key={topic} className="border border-border/30 rounded-xl overflow-hidden">
                      {/* Topic header */}
                      <button
                        onClick={() => toggleTopic(topic)}
                        className="w-full flex items-center justify-between p-3 bg-background/30 hover:bg-background/50 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          {isCollapsed ? (
                            <ChevronRight className="w-4 h-4 text-muted-foreground" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-muted-foreground" />
                          )}
                          <span className="font-medium text-sm uppercase">{topic}</span>
                          <span className="text-xs text-muted-foreground">
                            ({articles.length})
                          </span>
                          {selectedCount > 0 && (
                            <span className="px-2 py-0.5 rounded-full bg-primary/20 text-primary text-xs">
                              {selectedCount} selected
                            </span>
                          )}
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            selectAllInTopic(topic);
                          }}
                          className="text-xs text-primary hover:underline"
                        >
                          Select all
                        </button>
                      </button>

                      {/* Articles */}
                      {!isCollapsed && (
                        <div className="divide-y divide-border/20">
                          {articles.map(article => (
                            <label
                              key={article.id}
                              className="flex items-start gap-3 p-3 hover:bg-background/30 cursor-pointer transition-colors"
                            >
                              <input
                                type="checkbox"
                                checked={selectedArticles.has(article.id)}
                                onChange={() => toggleArticle(article.id)}
                                className="mt-1 w-4 h-4 rounded border-border/50 bg-background/50 text-primary focus:ring-primary/50"
                              />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium truncate">
                                  {article.title}
                                </p>
                                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                                  <span className="font-medium text-foreground/70">
                                    {article.source_name}
                                  </span>
                                  <span>•</span>
                                  <span className="flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {formatDate(article.published_at)}
                                  </span>
                                </div>
                              </div>
                              <a
                                href={article.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="p-1 hover:bg-background/50 rounded transition-colors"
                              >
                                <ExternalLink className="w-4 h-4 text-muted-foreground" />
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

            {/* Results */}
            {(result || error) && (
              <div className="bg-card/60 backdrop-blur-xl border border-border/30 rounded-2xl p-6">
                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  {error ? (
                    <span className="text-red-400">❌ Error</span>
                  ) : (
                    <>
                      <Check className="w-5 h-5 text-emerald-400" />
                      Result
                      <span className="text-xs font-normal text-muted-foreground ml-2">
                        {result?.word_count} words • {result?.generation_time_ms}ms
                      </span>
                    </>
                  )}
                </h2>

                {error && (
                  <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
                    {error}
                  </div>
                )}

                {result && (
                  <div className="space-y-4">
                    {/* Perplexity context */}
                    {result.enriched_context && (
                      <div className="p-4 bg-purple-500/10 border border-purple-500/30 rounded-xl">
                        <h3 className="text-sm font-semibold text-purple-400 mb-2 flex items-center gap-2">
                          <Sparkles className="w-4 h-4" />
                          Perplexity Context
                        </h3>
                        <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                          {result.enriched_context}
                        </p>
                        {result.perplexity_citations?.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-purple-500/20">
                            <p className="text-xs text-muted-foreground mb-2">Citations:</p>
                            <div className="flex flex-wrap gap-2">
                              {result.perplexity_citations.map((cite, i) => (
                                <a
                                  key={i}
                                  href={cite.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-xs px-2 py-1 bg-background/50 rounded hover:bg-background/80 transition-colors flex items-center gap-1"
                                >
                                  <ExternalLink className="w-3 h-3" />
                                  {cite.title?.slice(0, 30) || "Source"}
                                </a>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Script */}
                    <div className="p-4 bg-background/50 border border-border/30 rounded-xl">
                      <h3 className="text-sm font-semibold text-foreground mb-2">
                        Generated Script
                      </h3>
                      <pre className="text-sm text-foreground/90 whitespace-pre-wrap font-mono leading-relaxed">
                        {result.script}
                      </pre>
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>Topic: <strong className="text-foreground">{result.topic}</strong></span>
                      <span>Sources: {result.sources?.join(", ")}</span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
