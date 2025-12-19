"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Play, Pause, SkipBack, SkipForward } from "lucide-react";

interface Episode {
  id: string;
  title: string;
  audio_url: string;
  audio_duration: number | null;
  created_at: string;
}

interface StickyPlayerProps {
  episode: Episode;
}

export function StickyPlayer({ episode }: StickyPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(episode.audio_duration || 0);
  const [playbackRate, setPlaybackRate] = useState(1);

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
      navigator.mediaSession.setActionHandler("seekbackward", () => {
        audio.currentTime = Math.max(0, audio.currentTime - 15);
      });
      navigator.mediaSession.setActionHandler("seekforward", () => {
        audio.currentTime = Math.min(duration, audio.currentTime + 30);
      });
    }

    return () => {
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
      audio.removeEventListener("ended", handleEnded);
    };
  }, [episode, duration]);

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
    audio.currentTime = Math.max(0, Math.min(duration, audio.currentTime + seconds));
  };

  const cyclePlaybackRate = () => {
    const rates = [1, 1.25, 1.5, 1.75, 2];
    const currentIndex = rates.indexOf(playbackRate);
    const nextIndex = (currentIndex + 1) % rates.length;
    const newRate = rates[nextIndex];
    setPlaybackRate(newRate);
    if (audioRef.current) {
      audioRef.current.playbackRate = newRate;
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <>
      <audio ref={audioRef} src={episode.audio_url} preload="metadata" />
      
      {/* Sticky Player Bar */}
      <motion.div 
        className="fixed bottom-4 left-4 right-4 z-50"
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
      >
        <div className="player-bar max-w-2xl mx-auto px-4 py-3">
          {/* Progress Bar - Thin */}
          <div className="progress-thin mb-3">
            <motion.div
              className="progress-thin-fill"
              style={{ width: `${progress}%` }}
              layoutId="progress"
            />
          </div>

          <div className="flex items-center gap-4">
            {/* Play Button - Gradient in light, solid in dark */}
            <motion.button
              onClick={togglePlay}
              className="relative flex items-center justify-center w-12 h-12 rounded-full"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {/* Gradient background for light mode */}
              <div 
                className="absolute inset-0 rounded-full dark:hidden"
                style={{
                  background: "linear-gradient(135deg, #00F5FF 0%, #00D4E0 100%)",
                  boxShadow: "0 4px 16px rgba(0, 245, 255, 0.3)",
                }}
              />
              {/* Solid background for dark mode */}
              <div className="absolute inset-0 rounded-full hidden dark:block bg-[#1E1E1E] border border-white/10" />
              
              <span className="relative z-10 text-white dark:text-[#00F5FF]">
                {isPlaying ? (
                  <Pause className="w-5 h-5" />
                ) : (
                  <Play className="w-5 h-5 ml-0.5" />
                )}
              </span>
            </motion.button>

            {/* Skip Backward */}
            <motion.button
              onClick={() => skip(-15)}
              className="p-2 text-muted-foreground hover:text-foreground transition-colors"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <SkipBack className="w-4 h-4" />
            </motion.button>

            {/* Episode Info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{episode.title}</p>
              <p className="text-xs text-muted-foreground">
                {formatTime(currentTime)} / {formatTime(duration)}
              </p>
            </div>

            {/* Skip Forward */}
            <motion.button
              onClick={() => skip(30)}
              className="p-2 text-muted-foreground hover:text-foreground transition-colors"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <SkipForward className="w-4 h-4" />
            </motion.button>

            {/* Playback Speed */}
            <motion.button
              onClick={cyclePlaybackRate}
              className="px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground bg-secondary/50 dark:bg-white/5 rounded-md transition-colors"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {playbackRate}x
            </motion.button>
          </div>
        </div>
      </motion.div>
    </>
  );
}
