"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { 
  Play, 
  Pause, 
  SkipBack, 
  SkipForward, 
  Volume2, 
  VolumeX,
  Clock,
  ExternalLink,
  Loader2,
  RefreshCw,
  Headphones
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ============================================
// TYPES
// ============================================

interface Episode {
  id: string;
  title: string;
  audio_url: string;
  audio_duration: number | null;
  sources_data?: { title: string; url: string; domain: string }[];
  created_at: string;
}

interface PodcastPlayerProps {
  episode: Episode | null;
  history: Episode[];
  userId: string;
}

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
    month: "short"
  });
}

// ============================================
// PODCAST PLAYER COMPONENT
// ============================================

export function PodcastPlayer({ episode, history, userId }: PodcastPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentEpisode, setCurrentEpisode] = useState<Episode | null>(episode);

  // Update time
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => setCurrentTime(audio.currentTime);
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
    audioRef.current.currentTime = Math.max(0, Math.min(audioRef.current.currentTime + seconds, duration));
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

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
      const response = await fetch(`${backendUrl}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId })
      });
      
      if (response.ok) {
        toast.success("Génération lancée ! Votre podcast sera prêt dans quelques minutes.");
      } else {
        toast.error("Erreur lors de la génération");
      }
    } catch (error) {
      toast.error("Erreur de connexion");
    } finally {
      setIsGenerating(false);
    }
  };

  const playEpisode = (ep: Episode) => {
    setCurrentEpisode(ep);
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Main player */}
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
                <h2 className="text-xl font-semibold text-foreground truncate">
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

            {/* Sources */}
            {currentEpisode.sources_data && currentEpisode.sources_data.length > 0 && (
              <div className="pt-4 border-t border-border">
                <p className="text-sm font-medium text-muted-foreground mb-3">
                  Sources ({currentEpisode.sources_data.length})
                </p>
                <div className="flex flex-wrap gap-2">
                  {currentEpisode.sources_data.slice(0, 5).map((source, i) => (
                    <a
                      key={i}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-muted hover:bg-muted/80 rounded-full transition-colors"
                    >
                      <span>{source.domain}</span>
                      <ExternalLink className="w-3 h-3 opacity-50" />
                    </a>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          /* No episode state */
          <div className="text-center py-8">
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
              disabled={isGenerating}
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-full font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {isGenerating ? (
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

      {/* History */}
      {history.length > 1 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground">
            Épisodes précédents
          </h3>
          <div className="space-y-2">
            {history.filter(ep => ep.id !== currentEpisode?.id).map((ep) => (
              <button
                key={ep.id}
                onClick={() => playEpisode(ep)}
                className="w-full flex items-center gap-4 p-4 bg-card rounded-xl border border-border hover:border-primary/50 transition-all text-left"
              >
                <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center shrink-0">
                  <Play className="w-5 h-5 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-foreground truncate">
                    {ep.title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(ep.created_at)}
                    {ep.audio_duration && (
                      <span className="ml-2">• {formatDuration(ep.audio_duration)}</span>
                    )}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Generate button (if has episode) */}
      {currentEpisode && (
        <div className="flex justify-center">
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground hover:text-foreground bg-muted/50 hover:bg-muted rounded-full transition-colors disabled:opacity-50"
          >
            {isGenerating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Génération en cours...
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4" />
                Générer un nouveau podcast
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
