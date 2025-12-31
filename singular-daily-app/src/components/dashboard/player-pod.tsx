"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Pause, Layers, X, ExternalLink, SkipBack, SkipForward, List, ChevronRight } from "lucide-react";

interface Source {
  title: string;
  url: string;
  domain: string;
  type?: string;
}

interface Chapter {
  title: string;
  start_time: number;
  type: string;
  topic?: string;
  url?: string;
  multi_source?: boolean;
}

interface Episode {
  id: string;
  title: string;
  audio_url: string;
  audio_duration: number | null;
  sources_data?: Source[];
  chapters?: Chapter[];
}

interface PlayerPodProps {
  episode: Episode;
}

// Elegant color palette for sources - alternating warm neutrals
const SOURCE_COLORS = [
  { bg: "bg-[#F5F0E8]", text: "text-[#3D3D3D]", domain: "text-[#6B5B4F]" },      // Beige / Cream
  { bg: "bg-[#FAFAFA]", text: "text-[#2D2D2D]", domain: "text-[#7A7A7A]" },      // White / Light gray
  { bg: "bg-[#EDE8E0]", text: "text-[#4A4A4A]", domain: "text-[#8B7355]" },      // Sand / Taupe
  { bg: "bg-[#F8F6F3]", text: "text-[#3D3D3D]", domain: "text-[#9A8B7A]" },      // Off-white / Cream
  { bg: "bg-[#2D2D2D]", text: "text-[#F5F5F5]", domain: "text-[#A0A0A0]" },      // Charcoal
  { bg: "bg-[#1A1A1A]", text: "text-[#FFFFFF]", domain: "text-[#888888]" },      // Noir / Black
];

// Topic icons/colors for chapters (15 topics)
const TOPIC_STYLES: Record<string, { icon: string; color: string }> = {
  // V1 TECH
  ia: { icon: "🤖", color: "text-purple-500" },
  cyber: { icon: "🔐", color: "text-red-500" },
  deep_tech: { icon: "⚛️", color: "text-blue-500" },
  
  // V2 SCIENCE
  health: { icon: "🧬", color: "text-pink-500" },
  space: { icon: "🚀", color: "text-indigo-500" },
  energy: { icon: "⚡", color: "text-yellow-500" },
  
  // V3 ECONOMICS
  crypto: { icon: "₿", color: "text-orange-500" },
  macro: { icon: "🌍", color: "text-green-500" },
  deals: { icon: "💼", color: "text-purple-400" },
  
  // V4 WORLD
  asia: { icon: "🌏", color: "text-red-400" },
  regulation: { icon: "⚖️", color: "text-gray-500" },
  resources: { icon: "🪨", color: "text-amber-600" },
  
  // V5 INFLUENCE
  info: { icon: "📡", color: "text-cyan-500" },
  attention: { icon: "👁️", color: "text-violet-500" },
  persuasion: { icon: "🎯", color: "text-rose-500" },
  
  // System
  intro: { icon: "▶️", color: "text-tech-blue dark:text-cyan" },
  ephemeride: { icon: "📅", color: "text-amber-600" },
  default: { icon: "📰", color: "text-gray-500" },
};

export function PlayerPod({ episode }: PlayerPodProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(episode.audio_duration || 0);
  const [showSources, setShowSources] = useState(false);
  const [showChapters, setShowChapters] = useState(false);
  const [currentChapter, setCurrentChapter] = useState<Chapter | null>(null);

  const sources = episode.sources_data || [];
  const chapters = episode.chapters || [];

  const getSourceColor = (index: number) => {
    return SOURCE_COLORS[index % SOURCE_COLORS.length];
  };

  const getTopicStyle = (topic?: string, type?: string) => {
    if (type === "intro") return TOPIC_STYLES.intro;
    if (type === "ephemeride") return TOPIC_STYLES.ephemeride;
    return TOPIC_STYLES[topic || ""] || TOPIC_STYLES.default;
  };

  // Find current chapter based on playback position
  useEffect(() => {
    if (chapters.length === 0) return;
    
    // Find the chapter that contains current time
    let activeChapter = chapters[0];
    for (const chapter of chapters) {
      if (currentTime >= chapter.start_time) {
        activeChapter = chapter;
      } else {
        break;
      }
    }
    setCurrentChapter(activeChapter);
  }, [currentTime, chapters]);

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

  // Navigate to specific chapter
  const goToChapter = (chapter: Chapter) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = chapter.start_time;
    if (!isPlaying) {
      audio.play();
      setIsPlaying(true);
    }
    setShowChapters(false);
  };

  // Go to next/previous chapter
  const skipToNextChapter = () => {
    if (chapters.length === 0) return;
    const currentIdx = chapters.findIndex(c => c === currentChapter);
    if (currentIdx < chapters.length - 1) {
      goToChapter(chapters[currentIdx + 1]);
    }
  };

  const skipToPrevChapter = () => {
    if (chapters.length === 0) return;
    const currentIdx = chapters.findIndex(c => c === currentChapter);
    // If we're more than 3 seconds into the chapter, restart it
    // Otherwise go to previous
    if (currentChapter && currentTime - currentChapter.start_time > 3 && currentIdx >= 0) {
      goToChapter(currentChapter);
    } else if (currentIdx > 0) {
      goToChapter(chapters[currentIdx - 1]);
    } else {
      // Go to start
      const audio = audioRef.current;
      if (audio) audio.currentTime = 0;
    }
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

      {/* Chapters Panel - Slides from behind */}
      <AnimatePresence>
        {showChapters && chapters.length > 0 && (
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
                <h3 className="font-display text-lg font-medium">Chapitres</h3>
                <button
                  onClick={() => setShowChapters(false)}
                  className="p-2 rounded-full hover:bg-card transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Chapters List */}
              <div className="space-y-1">
                {chapters.map((chapter, idx) => {
                  const style = getTopicStyle(chapter.topic, chapter.type);
                  const isActive = chapter === currentChapter;
                  const nextChapter = chapters[idx + 1];
                  const chapterDuration = nextChapter 
                    ? nextChapter.start_time - chapter.start_time 
                    : duration - chapter.start_time;

                  return (
                    <motion.button
                      key={idx}
                      onClick={() => goToChapter(chapter)}
                      className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-left ${
                        isActive 
                          ? "bg-tech-blue/10 dark:bg-cyan/10 border border-tech-blue/30 dark:border-cyan/30" 
                          : "hover:bg-card"
                      }`}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.03 }}
                    >
                      {/* Topic icon */}
                      <span className="text-lg flex-shrink-0">{style.icon}</span>
                      
                      {/* Chapter info */}
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm font-medium truncate ${isActive ? "text-tech-blue dark:text-cyan" : ""}`}>
                          {chapter.title}
                        </p>
                        <p className="text-xs text-muted-foreground font-mono">
                          {formatTime(chapter.start_time)} • {Math.round(chapterDuration)}s
                        </p>
                      </div>

                      {/* Active indicator */}
                      {isActive && (
                        <motion.div
                          initial={{ scale: 0 }}
                          animate={{ scale: 1 }}
                          className="w-2 h-2 rounded-full bg-tech-blue dark:bg-cyan flex-shrink-0"
                        />
                      )}
                      
                      <ChevronRight className={`w-4 h-4 flex-shrink-0 ${isActive ? "text-tech-blue dark:text-cyan" : "text-muted-foreground"}`} />
                    </motion.button>
                  );
                })}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

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
                  {sources.map((source, idx) => {
                    const colors = getSourceColor(idx);
                    return (
                      <motion.a
                        key={idx}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`flex items-center justify-between p-3 rounded-xl ${colors.bg} hover:opacity-90 transition-all group shadow-sm`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.05 }}
                      >
                        <div className="flex-1 min-w-0 mr-3">
                          <p className={`text-sm font-medium truncate font-body ${colors.text}`}>
                            {source.title}
                          </p>
                          <p className={`text-xs font-mono ${colors.domain}`}>
                            {source.domain}
                          </p>
                        </div>
                        <ExternalLink className={`w-4 h-4 ${colors.text} opacity-0 group-hover:opacity-60 transition-opacity flex-shrink-0`} />
                      </motion.a>
                    );
                  })}
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
      <motion.div
        className="fixed bottom-6 left-1/2 z-50"
        style={{ x: "-50%" }}
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={springConfig}
      >
        <div className="player-pod w-[90vw] max-w-[600px] px-4 py-3">
          <div className="flex items-center gap-3">
            
            {/* Skip Back - Goes to previous chapter */}
            <motion.button
              onClick={skipToPrevChapter}
              className="p-2 rounded-full text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              title="Chapitre précédent"
            >
              <SkipBack className="w-4 h-4" />
            </motion.button>

            {/* Play Button - Cyan accent */}
            <motion.button
              onClick={togglePlay}
              className="player-btn-main relative flex items-center justify-center w-12 h-12 rounded-full flex-shrink-0 bg-tech-blue dark:bg-cyan shadow-glow-blue dark:shadow-glow-cyan"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <span className="text-white dark:text-ink">
                {isPlaying ? (
                  <Pause className="w-5 h-5" />
                ) : (
                  <Play className="w-5 h-5 ml-0.5" />
                )}
              </span>
            </motion.button>

            {/* Skip Forward - Goes to next chapter */}
            <motion.button
              onClick={skipToNextChapter}
              className="p-2 rounded-full text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              title="Chapitre suivant"
            >
              <SkipForward className="w-4 h-4" />
            </motion.button>

            {/* Center: Current Chapter + Progress */}
            <div className="flex-1 min-w-0">
              {/* Current chapter or episode title */}
              <p className="font-display text-sm font-medium truncate text-tech-blue dark:text-cyan">
                {currentChapter?.type === "news" 
                  ? currentChapter.title 
                  : episode.title}
              </p>
              
              {/* Progress bar with chapter markers */}
              <div className="mt-1.5 flex items-center gap-2">
                <div className="flex-1 progress-thin relative">
                  {/* Chapter markers */}
                  {chapters.map((chapter, idx) => {
                    const markerPos = duration > 0 ? (chapter.start_time / duration) * 100 : 0;
                    if (markerPos === 0) return null;
                    return (
                      <div
                        key={idx}
                        className="absolute top-0 w-0.5 h-full bg-brass/40"
                        style={{ left: `${markerPos}%` }}
                      />
                    );
                  })}
                  <motion.div
                    className="progress-thin-fill"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                {/* Time - Bronze color */}
                <span className="text-[10px] font-mono text-[#C5B358]/70 flex-shrink-0">
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              </div>
            </div>

            {/* Chapters Button */}
            {chapters.length > 0 && (
              <motion.button
                onClick={() => {
                  setShowChapters(!showChapters);
                  setShowSources(false);
                }}
                className={`p-3 rounded-full transition-colors flex-shrink-0 ${
                  showChapters 
                    ? "bg-brass/20 text-brass" 
                    : "hover:bg-card text-muted-foreground hover:text-brass"
                }`}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                title="Chapitres"
              >
                <List className="w-5 h-5" />
              </motion.button>
            )}

            {/* Sources Button - Brass accent */}
            <motion.button
              onClick={() => {
                setShowSources(!showSources);
                setShowChapters(false);
              }}
              className={`p-3 rounded-full transition-colors flex-shrink-0 ${
                showSources 
                  ? "bg-brass/20 text-brass" 
                  : "hover:bg-card text-muted-foreground hover:text-brass"
              }`}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              title="Sources"
            >
              <Layers className="w-5 h-5" />
            </motion.button>
          </div>
        </div>
      </motion.div>
    </>
  );
}
