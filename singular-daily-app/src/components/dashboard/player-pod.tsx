"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Pause, Layers, X, ExternalLink, SkipBack, SkipForward } from "lucide-react";

interface Source {
  title: string;
  url: string;
  domain: string;
  type?: string;
}

interface Episode {
  id: string;
  title: string;
  audio_url: string;
  audio_duration: number | null;
  sources_data?: Source[];
}

interface PlayerPodProps {
  episode: Episode;
}

export function PlayerPod({ episode }: PlayerPodProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(episode.audio_duration || 0);
  const [showSources, setShowSources] = useState(false);

  const sources = episode.sources_data || [];

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => setCurrentTime(audio.currentTime);
    const handleLoadedMetadata = () => setDuration(audio.duration);
    const handleEnded = () => setIsPlaying(false);

    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("loadedmetadata", handleLoadedMetadata);
    audio.addEventListener("ended", handleEnded);

    // MediaSession API
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: episode.title,
        artist: "Keernel",
        album: "Daily Podcast",
      });

      navigator.mediaSession.setActionHandler("play", () => {
        audio.play();
        setIsPlaying(true);
      });
      navigator.mediaSession.setActionHandler("pause", () => {
        audio.pause();
        setIsPlaying(false);
      });
    }

    return () => {
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
      audio.removeEventListener("ended", handleEnded);
    };
  }, [episode]);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
    } else {
      audio.play();
    }
    setIsPlaying(!isPlaying);
  };

  const skip = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, Math.min(audio.currentTime + seconds, duration));
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  // iOS-like spring config
  const springConfig = {
    type: "spring" as const,
    stiffness: 350,
    damping: 35,
  };

  return (
    <>
      <audio ref={audioRef} src={episode.audio_url} preload="metadata" />

      {/* Sources Panel - Slides from behind */}
      <AnimatePresence>
        {showSources && (
          <motion.div
            className="fixed bottom-28 left-1/2 z-40 w-[90%] max-w-[580px]"
            style={{ x: "-50%" }}
            initial={{ y: "100%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
            transition={springConfig}
          >
            <div className="sources-panel p-4 max-h-[50vh] overflow-y-auto scrollbar-hide">
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display text-lg font-medium">Sources</h3>
                <button
                  onClick={() => setShowSources(false)}
                  className="p-2 rounded-full hover:bg-card transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Sources List */}
              {sources.length > 0 ? (
                <div className="space-y-2">
                  {sources.map((source, idx) => (
                    <motion.a
                      key={idx}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-between p-3 rounded-xl bg-card hover:bg-card/80 border border-brass/10 transition-colors group"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.05 }}
                    >
                      <div className="flex-1 min-w-0 mr-3">
                        <p className="text-sm font-medium truncate font-body">
                          {source.title}
                        </p>
                        <p className="text-xs text-muted-foreground font-mono">
                          {source.domain}
                        </p>
                      </div>
                      <ExternalLink className="w-4 h-4 text-brass opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                    </motion.a>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4 font-mono">
                  Aucune source disponible
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Player Pod - Floating Capsule */}
      {/* Light: fond crème, bouton charcoal */}
      {/* Dark: fond charcoal, bouton crème */}
      <motion.div
        className="fixed bottom-6 left-1/2 z-50"
        style={{ x: "-50%" }}
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={springConfig}
      >
        <div className="player-pod w-[90vw] max-w-[600px] px-4 py-3">
          <div className="flex items-center gap-3">
            
            {/* Skip Back - Lighter color */}
            <motion.button
              onClick={() => skip(-15)}
              className="p-2 rounded-full text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <SkipBack className="w-4 h-4" />
            </motion.button>

            {/* Play Button - Charcoal in light, Cream in dark */}
            <motion.button
              onClick={togglePlay}
              className="player-btn-main relative flex items-center justify-center w-12 h-12 rounded-full flex-shrink-0 bg-charcoal dark:bg-cream"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <span className="text-cream dark:text-charcoal">
                {isPlaying ? (
                  <Pause className="w-5 h-5" />
                ) : (
                  <Play className="w-5 h-5 ml-0.5" />
                )}
              </span>
            </motion.button>

            {/* Skip Forward - Lighter color */}
            <motion.button
              onClick={() => skip(30)}
              className="p-2 rounded-full text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <SkipForward className="w-4 h-4" />
            </motion.button>

            {/* Center: Title + Progress */}
            <div className="flex-1 min-w-0">
              {/* Episode Title - Display font */}
              <p className="font-display text-sm font-medium truncate">
                {episode.title}
              </p>
              
              {/* Progress bar */}
              <div className="mt-1.5 flex items-center gap-2">
                <div className="flex-1 progress-thin">
                  <motion.div
                    className="progress-thin-fill"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                {/* Time - Lighter muted color */}
                <span className="text-[10px] font-mono text-muted-foreground/70 flex-shrink-0">
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              </div>
            </div>

            {/* Sources Button - Brass accent */}
            <motion.button
              onClick={() => setShowSources(!showSources)}
              className={`p-3 rounded-full transition-colors flex-shrink-0 ${
                showSources 
                  ? "bg-brass/20 text-brass" 
                  : "hover:bg-card text-muted-foreground hover:text-brass"
              }`}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Layers className="w-5 h-5" />
            </motion.button>
          </div>
        </div>
      </motion.div>
    </>
  );
}
