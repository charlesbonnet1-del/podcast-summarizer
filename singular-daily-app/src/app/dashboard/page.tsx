"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
  RefreshCw,
  Loader2,
  Headphones,
  ThumbsUp,
  ThumbsDown,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Clock,
  Calendar,
  Zap
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ============================================
// TYPES
// ============================================

interface Segment {
  id: string;
  topic: string;
  title: string;
  summary: string;
  script?: string;
  sources: { title: string; url: string; domain: string }[];
  start_time?: number;
  end_time?: number;
  user_feedback?: "up" | "down" | null;
}

interface Episode {
  id: string;
  title: string;
  audio_url: string;
  audio_duration: number | null;
  summary_text?: string;
  sources_data?: { title: string; url: string; domain: string }[];
  segments?: Segment[];
  created_at: string;
}

// ============================================
// CONSTANTS
// ============================================

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "";

const TOPIC_COLORS: Record<string, string> = {
  ia: "bg-purple-500",
  macro: "bg-blue-500",
  asia: "bg-green-500",
  crypto: "bg-orange-500",
  cyber: "bg-red-500",
  space: "bg-indigo-500",
  health: "bg-pink-500",
  energy: "bg-yellow-500",
  deals: "bg-emerald-500",
  general: "bg-gray-500"
};

// ============================================
// FORMAT HELPERS
// ============================================

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("fr-FR", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  });
}

// ============================================
// SEGMENT CARD COMPONENT
// ============================================

function SegmentCard({
  segment,
  isActive,
  onFeedback,
  onSeek
}: {
  segment: Segment;
  isActive: boolean;
  onFeedback: (id: string, feedback: "up" | "down") => void;
  onSeek?: (time: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<"up" | "down" | null>(
    segment.user_feedback || null
  );

  const handleFeedback = (feedback: "up" | "down") => {
    setFeedbackGiven(feedback);
    onFeedback(segment.id, feedback);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-xl border p-4 transition-all",
        isActive
          ? "border-primary bg-primary/5"
          : "border-border bg-card hover:border-primary/30"
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        {/* Topic badge */}
        <div
          className={cn(
            "px-2 py-1 rounded-lg text-xs font-medium text-white",
            TOPIC_COLORS[segment.topic] || TOPIC_COLORS.general
          )}
        >
          {segment.topic.toUpperCase()}
        </div>

        {/* Seek button */}
        {segment.start_time !== undefined && onSeek && (
          <button
            onClick={() => onSeek(segment.start_time!)}
            className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
          >
            <Clock className="w-3 h-3" />
            {formatDuration(segment.start_time)}
          </button>
        )}

        {/* Active indicator */}
        {isActive && (
          <div className="ml-auto flex items-center gap-1 text-xs text-primary">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            En cours
          </div>
        )}
      </div>

      {/* Title */}
      <h4 className="font-medium mt-2 text-foreground">{segment.title}</h4>

      {/* Summary */}
      <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
        {segment.summary}
      </p>

      {/* Expand toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 mt-2 text-xs text-primary hover:underline"
      >
        {expanded ? (
          <>
            <ChevronUp className="w-3 h-3" />
            Masquer
          </>
        ) : (
          <>
            <ChevronDown className="w-3 h-3" />
            Voir les sources
          </>
        )}
      </button>

      {/* Expanded content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 pt-3 border-t border-border space-y-2">
              {segment.sources.map((source, i) => (
                <a
                  key={i}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-xs p-2 bg-muted rounded hover:bg-muted/80"
                >
                  <span className="text-muted-foreground flex-shrink-0">
                    {source.domain}
                  </span>
                  <span className="truncate flex-1">{source.title}</span>
                  <ExternalLink className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                </a>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Feedback buttons */}
      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border">
        <span className="text-xs text-muted-foreground mr-auto">
          Ce segment est-il utile ?
        </span>

        <button
          onClick={() => handleFeedback("up")}
          disabled={feedbackGiven !== null}
          className={cn(
            "flex items-center gap-1 px-2 py-1 rounded-lg text-xs transition-all",
            feedbackGiven === "up"
              ? "bg-green-500 text-white"
              : feedbackGiven !== null
              ? "bg-muted text-muted-foreground opacity-50"
              : "bg-muted hover:bg-green-500/20 hover:text-green-500"
          )}
        >
          <ThumbsUp className="w-3 h-3" />
        </button>

        <button
          onClick={() => handleFeedback("down")}
          disabled={feedbackGiven !== null}
          className={cn(
            "flex items-center gap-1 px-2 py-1 rounded-lg text-xs transition-all",
            feedbackGiven === "down"
              ? "bg-red-500 text-white"
              : feedbackGiven !== null
              ? "bg-muted text-muted-foreground opacity-50"
              : "bg-muted hover:bg-red-500/20 hover:text-red-500"
          )}
        >
          <ThumbsDown className="w-3 h-3" />
        </button>
      </div>
    </motion.div>
  );
}

// ============================================
// EPISODE CARD COMPONENT
// ============================================

function EpisodeCard({
  episode,
  isSelected,
  onClick
}: {
  episode: Episode;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-4 p-4 rounded-xl border transition-all text-left",
        isSelected
          ? "border-primary bg-primary/5"
          : "border-border bg-card hover:border-primary/30"
      )}
    >
      <div
        className={cn(
          "w-12 h-12 rounded-lg flex items-center justify-center shrink-0",
          isSelected ? "bg-primary text-primary-foreground" : "bg-muted"
        )}
      >
        <Play className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-foreground truncate">{episode.title}</p>
        <p className="text-xs text-muted-foreground flex items-center gap-2">
          <Calendar className="w-3 h-3" />
          {formatDate(episode.created_at)}
          {episode.audio_duration && (
            <>
              <Clock className="w-3 h-3 ml-2" />
              {formatDuration(episode.audio_duration)}
            </>
          )}
        </p>
      </div>
    </button>
  );
}

// ============================================
// MAIN DASHBOARD COMPONENT
// ============================================

export default function PodcastDashboard() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [currentEpisode, setCurrentEpisode] = useState<Episode | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  // Audio state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number>(-1);

  // Fetch episodes
  const fetchEpisodes = async () => {
    try {
      const res = await fetch("/api/history");
      const data = await res.json();
      if (data.episodes) {
        setEpisodes(data.episodes);
        if (data.episodes.length > 0 && !currentEpisode) {
          setCurrentEpisode(data.episodes[0]);
        }
      }
    } catch (error) {
      console.error("Error fetching episodes:", error);
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchEpisodes();
  }, []);

  // Audio event handlers
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => {
      setCurrentTime(audio.currentTime);

      // Update active segment based on time
      if (currentEpisode?.segments) {
        const idx = currentEpisode.segments.findIndex(
          (seg) =>
            seg.start_time !== undefined &&
            seg.end_time !== undefined &&
            audio.currentTime >= seg.start_time &&
            audio.currentTime < seg.end_time
        );
        setActiveSegmentIndex(idx);
      }
    };

    const handleLoadedMetadata = () => setDuration(audio.duration);
    const handleEnded = () => setIsPlaying(false);

    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("loadedmetadata", handleLoadedMetadata);
    audio.addEventListener("ended", handleEnded);

    return () => {
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
      audio.removeEventListener("ended", handleEnded);
    };
  }, [currentEpisode]);

  // Controls
  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const seek = (seconds: number) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = Math.max(
      0,
      Math.min(audioRef.current.currentTime + seconds, duration)
    );
  };

  const seekTo = (time: number) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = time;
  };

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!audioRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    audioRef.current.currentTime = percent * duration;
  };

  const toggleMute = () => {
    if (!audioRef.current) return;
    audioRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  // Generate podcast
  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await fetch("/api/generate", { method: "POST" });
      const data = await res.json();

      if (res.ok) {
        toast.success(
          "Génération lancée ! Votre podcast sera prêt dans quelques minutes."
        );
        // Poll for completion
        setTimeout(() => fetchEpisodes(), 30000);
      } else {
        toast.error(data.error || "Erreur lors de la génération");
      }
    } catch {
      toast.error("Erreur de connexion");
    } finally {
      setGenerating(false);
    }
  };

  // Segment feedback
  const handleSegmentFeedback = async (
    segmentId: string,
    feedback: "up" | "down"
  ) => {
    try {
      await fetch(`${API_BASE}/api/segments/${segmentId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback })
      });
      toast.success("Merci pour votre retour !");
    } catch {
      console.error("Error sending feedback");
    }
  };

  // Select episode
  const selectEpisode = (episode: Episode) => {
    setCurrentEpisode(episode);
    setIsPlaying(false);
    setCurrentTime(0);
    setActiveSegmentIndex(-1);
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  // Mock segments if not present (for demo)
  const segments: Segment[] = currentEpisode?.segments || [
    {
      id: "1",
      topic: "ia",
      title: "OpenAI lance GPT-5",
      summary:
        "La nouvelle version du modèle phare d'OpenAI promet des avancées majeures en raisonnement et multimodalité.",
      sources: [
        { title: "OpenAI announces GPT-5", url: "#", domain: "techcrunch.com" }
      ]
    },
    {
      id: "2",
      topic: "macro",
      title: "La Fed maintient ses taux",
      summary:
        "Jerome Powell annonce une pause dans le cycle de hausse, les marchés réagissent positivement.",
      sources: [
        {
          title: "Fed holds rates steady",
          url: "#",
          domain: "bloomberg.com"
        }
      ]
    },
    {
      id: "3",
      topic: "asia",
      title: "Alibaba se restructure",
      summary:
        "Le géant chinois annonce une scission en 6 entités indépendantes pour favoriser l'innovation.",
      sources: [
        { title: "Alibaba splits into 6 units", url: "#", domain: "scmp.com" }
      ]
    }
  ];

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto p-6 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <Zap className="w-6 h-6 text-primary" />
              Keernel
            </h1>
            <p className="text-muted-foreground mt-1">
              Votre briefing quotidien en audio
            </p>
          </div>

          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 disabled:opacity-50 transition-all"
          >
            {generating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Génération...
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4" />
                Générer
              </>
            )}
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Main Player Column */}
            <div className="lg:col-span-2 space-y-6">
              {/* Player Card */}
              <div className="bg-card rounded-2xl border border-border p-6 space-y-6">
                {currentEpisode ? (
                  <>
                    {/* Audio element */}
                    <audio
                      ref={audioRef}
                      src={currentEpisode.audio_url}
                      preload="metadata"
                    />

                    {/* Episode info */}
                    <div className="flex items-start gap-4">
                      <div className="w-20 h-20 rounded-xl bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center shrink-0">
                        <Headphones className="w-10 h-10 text-primary-foreground" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h2 className="text-xl font-semibold text-foreground">
                          {currentEpisode.title}
                        </h2>
                        <p className="text-sm text-muted-foreground mt-1">
                          {formatDate(currentEpisode.created_at)}
                          {currentEpisode.audio_duration && (
                            <span className="ml-2">
                              • {formatDuration(currentEpisode.audio_duration)}
                            </span>
                          )}
                        </p>
                        {currentEpisode.summary_text && (
                          <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                            {currentEpisode.summary_text}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Progress bar */}
                    <div className="space-y-2">
                      <div
                        className="h-2 bg-muted rounded-full cursor-pointer overflow-hidden"
                        onClick={handleProgressClick}
                      >
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>{formatDuration(currentTime)}</span>
                        <span>{formatDuration(duration)}</span>
                      </div>
                    </div>

                    {/* Controls */}
                    <div className="flex items-center justify-center gap-4">
                      <button
                        onClick={() => seek(-15)}
                        className="p-3 rounded-full hover:bg-muted transition-colors"
                      >
                        <SkipBack className="w-5 h-5" />
                      </button>

                      <button
                        onClick={togglePlay}
                        className="p-4 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                      >
                        {isPlaying ? (
                          <Pause className="w-6 h-6" />
                        ) : (
                          <Play className="w-6 h-6 ml-0.5" />
                        )}
                      </button>

                      <button
                        onClick={() => seek(30)}
                        className="p-3 rounded-full hover:bg-muted transition-colors"
                      >
                        <SkipForward className="w-5 h-5" />
                      </button>

                      <button
                        onClick={toggleMute}
                        className="p-3 rounded-full hover:bg-muted transition-colors ml-4"
                      >
                        {isMuted ? (
                          <VolumeX className="w-5 h-5" />
                        ) : (
                          <Volume2 className="w-5 h-5" />
                        )}
                      </button>
                    </div>
                  </>
                ) : (
                  /* No episode state */
                  <div className="text-center py-12">
                    <div className="w-20 h-20 rounded-full bg-muted flex items-center justify-center mx-auto mb-4">
                      <Headphones className="w-10 h-10 text-muted-foreground" />
                    </div>
                    <h3 className="text-lg font-medium text-foreground mb-2">
                      Pas encore de podcast
                    </h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Générez votre premier briefing audio personnalisé
                    </p>
                    <button
                      onClick={handleGenerate}
                      disabled={generating}
                      className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-full font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                    >
                      {generating ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Génération...
                        </>
                      ) : (
                        <>
                          <RefreshCw className="w-4 h-4" />
                          Générer un podcast
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>

              {/* Segments */}
              {currentEpisode && segments.length > 0 && (
                <div className="space-y-4">
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Segments ({segments.length})
                  </h3>
                  <div className="space-y-3">
                    {segments.map((segment, idx) => (
                      <SegmentCard
                        key={segment.id}
                        segment={segment}
                        isActive={idx === activeSegmentIndex}
                        onFeedback={handleSegmentFeedback}
                        onSeek={seekTo}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Sidebar - Episode History */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-muted-foreground">
                Épisodes
              </h3>

              {episodes.length === 0 ? (
                <div className="text-center py-8 bg-card rounded-xl border border-border">
                  <Headphones className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">
                    Aucun épisode
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {episodes.map((episode) => (
                    <EpisodeCard
                      key={episode.id}
                      episode={episode}
                      isSelected={currentEpisode?.id === episode.id}
                      onClick={() => selectEpisode(episode)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
