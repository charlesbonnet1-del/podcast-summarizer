"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { 
  Play, 
  Pause, 
  SkipBack, 
  SkipForward, 
  Volume2, 
  VolumeX,
  Loader2,
  Headphones
} from "lucide-react";

interface Source {
  title: string;
  url: string;
  domain: string;
}

interface Episode {
  id: string;
  title: string;
  audio_url: string;
  summary_text?: string;
  sources_data?: Source[];
  created_at: string;
  audio_duration?: number;
}

interface AudioPlayerProps {
  episode: Episode | null;
}

export function AudioPlayer({ episode }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);

  // Format time (seconds to mm:ss)
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  // Setup MediaSession for lock screen controls
  useEffect(() => {
    if (!episode || !("mediaSession" in navigator)) return;

    navigator.mediaSession.metadata = new MediaMetadata({
      title: episode.title,
      artist: "Singular Daily",
      album: "Your Daily Podcast",
      artwork: [
        { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
        { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      ],
    });

    navigator.mediaSession.setActionHandler("play", () => {
      audioRef.current?.play();
      setIsPlaying(true);
    });

    navigator.mediaSession.setActionHandler("pause", () => {
      audioRef.current?.pause();
      setIsPlaying(false);
    });

    navigator.mediaSession.setActionHandler("seekbackward", () => {
      if (audioRef.current) {
        audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 15);
      }
    });

    navigator.mediaSession.setActionHandler("seekforward", () => {
      if (audioRef.current) {
        audioRef.current.currentTime = Math.min(duration, audioRef.current.currentTime + 15);
      }
    });

    navigator.mediaSession.setActionHandler("seekto", (details) => {
      if (audioRef.current && details.seekTime !== undefined) {
        audioRef.current.currentTime = details.seekTime;
      }
    });

    return () => {
      navigator.mediaSession.setActionHandler("play", null);
      navigator.mediaSession.setActionHandler("pause", null);
      navigator.mediaSession.setActionHandler("seekbackward", null);
      navigator.mediaSession.setActionHandler("seekforward", null);
      navigator.mediaSession.setActionHandler("seekto", null);
    };
  }, [episode, duration]);

  // Update MediaSession position state
  useEffect(() => {
    if ("mediaSession" in navigator && duration > 0) {
      navigator.mediaSession.setPositionState({
        duration: duration,
        playbackRate: 1,
        position: currentTime,
      });
    }
  }, [currentTime, duration]);

  // Audio event handlers
  const handleLoadStart = () => setIsLoading(true);
  const handleCanPlay = () => setIsLoading(false);
  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };
  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };
  const handleEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

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

  const handleSeek = (value: number[]) => {
    if (audioRef.current) {
      audioRef.current.currentTime = value[0];
      setCurrentTime(value[0]);
    }
  };

  const skipBackward = () => {
    if (audioRef.current) {
      audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 15);
    }
  };

  const skipForward = () => {
    if (audioRef.current) {
      audioRef.current.currentTime = Math.min(duration, audioRef.current.currentTime + 15);
    }
  };

  const toggleMute = () => {
    if (audioRef.current) {
      audioRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  const handleVolumeChange = (value: number[]) => {
    if (audioRef.current) {
      audioRef.current.volume = value[0];
      setVolume(value[0]);
      setIsMuted(value[0] === 0);
    }
  };

  // No episode state
  if (!episode) {
    return (
      <Card className="shadow-zen rounded-2xl border-border bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
        <CardContent className="p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center mx-auto mb-4">
            <Headphones className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="font-medium text-lg mb-1">No episodes yet</h3>
          <p className="text-sm text-muted-foreground">
            Add topics and content, then generate your first podcast!
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="shadow-zen rounded-2xl border-border overflow-hidden">
      {/* Hidden audio element */}
      <audio
        ref={audioRef}
        src={episode.audio_url}
        onLoadStart={handleLoadStart}
        onCanPlay={handleCanPlay}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      />

      {/* Player UI */}
      <CardContent className="p-6">
        {/* Episode info */}
        <div className="mb-6">
          <h3 className="font-semibold text-lg line-clamp-2 mb-1">
            {episode.title}
          </h3>
          <p className="text-sm text-muted-foreground">
            {new Date(episode.created_at).toLocaleDateString("fr-FR", {
              weekday: "long",
              day: "numeric",
              month: "long",
            })}
          </p>
        </div>

        {/* Progress bar */}
        <div className="mb-4">
          <Slider
            value={[currentTime]}
            max={duration || 100}
            step={1}
            onValueChange={handleSeek}
            className="cursor-pointer"
          />
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-center gap-4">
          {/* Skip back 15s */}
          <Button
            variant="ghost"
            size="icon"
            onClick={skipBackward}
            className="rounded-full h-10 w-10"
          >
            <SkipBack className="w-5 h-5" />
          </Button>

          {/* Play/Pause */}
          <Button
            onClick={togglePlay}
            disabled={isLoading}
            className="rounded-full h-14 w-14 bg-gradient-to-br from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600"
          >
            {isLoading ? (
              <Loader2 className="w-6 h-6 animate-spin" />
            ) : isPlaying ? (
              <Pause className="w-6 h-6" />
            ) : (
              <Play className="w-6 h-6 ml-1" />
            )}
          </Button>

          {/* Skip forward 15s */}
          <Button
            variant="ghost"
            size="icon"
            onClick={skipForward}
            className="rounded-full h-10 w-10"
          >
            <SkipForward className="w-5 h-5" />
          </Button>
        </div>

        {/* Volume control */}
        <div className="flex items-center gap-2 mt-6 max-w-[200px] mx-auto">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleMute}
            className="rounded-full h-8 w-8"
          >
            {isMuted || volume === 0 ? (
              <VolumeX className="w-4 h-4" />
            ) : (
              <Volume2 className="w-4 h-4" />
            )}
          </Button>
          <Slider
            value={[isMuted ? 0 : volume]}
            max={1}
            step={0.1}
            onValueChange={handleVolumeChange}
            className="flex-1"
          />
        </div>
      </CardContent>
    </Card>
  );
}
