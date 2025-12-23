"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Play, Pause, Layers, X, ExternalLink, Link2, Loader2,
  Settings, LogOut, Sun, Moon, Monitor, User, SkipBack, SkipForward
} from "lucide-react";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

// ============================================
// TYPES
// ============================================

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

interface Topic {
  id: string;
  keyword: string;
  display_name?: string;
}

interface ManualItem {
  id: string;
  url: string;
  title?: string;
}

interface KernelDashboardProps {
  user: {
    firstName: string;
    email: string;
    avatarUrl?: string;
  };
  episode: Episode | null;
  topics: Topic[];
  manualContent: ManualItem[];
  pendingCount: number;
}

// ============================================
// UTILITIES
// ============================================

// Get source type and color from URL
function getSourceMeta(url: string): { type: "video" | "podcast" | "article"; color: string; bgClass: string } {
  const domain = url.toLowerCase();
  
  // Video sources
  if (domain.includes("youtube.com") || domain.includes("youtu.be") || 
      domain.includes("vimeo.com") || domain.includes("twitch.tv")) {
    return { type: "video", color: "#C5B358", bgClass: "bg-brass/5 dark:bg-brass/10" };
  }
  
  // Podcast sources
  if (domain.includes("spotify.com") || domain.includes("podcasts.apple.com") ||
      domain.includes("podcasts.google.com") || domain.includes("soundcloud.com") ||
      domain.includes("anchor.fm") || domain.includes("overcast.fm")) {
    return { type: "podcast", color: "#C5B358", bgClass: "bg-brass/5 dark:bg-brass/10" };
  }
  
  // Articles (default)
  return { type: "article", color: "#A855F7", bgClass: "bg-violet-500/5 dark:bg-violet-500/10" };
}

// Get favicon URL
function getFaviconUrl(url: string): string {
  try {
    const domain = new URL(url).hostname;
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;
  } catch {
    return "";
  }
}

// ============================================
// FLOATING ORBS (Light mode only)
// ============================================

function FloatingOrbs() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted || resolvedTheme === "dark") return null;

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {/* Brass orb - top right */}
      <motion.div
        className="absolute w-[500px] h-[500px] rounded-full opacity-30"
        style={{
          background: "radial-gradient(circle, rgba(197, 179, 88, 0.4) 0%, transparent 70%)",
          filter: "blur(60px)",
          top: "-10%",
          right: "-5%",
        }}
        animate={{
          x: [0, 30, -20, 0],
          y: [0, -20, 30, 0],
          scale: [1, 1.05, 0.98, 1],
        }}
        transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
      />
      
      {/* Brass lighter orb - bottom left */}
      <motion.div
        className="absolute w-[400px] h-[400px] rounded-full opacity-25"
        style={{
          background: "radial-gradient(circle, rgba(197, 179, 88, 0.3) 0%, transparent 70%)",
          filter: "blur(50px)",
          bottom: "10%",
          left: "-5%",
        }}
        animate={{
          x: [0, -30, 20, 0],
          y: [0, 20, -30, 0],
          scale: [1, 0.95, 1.08, 1],
        }}
        transition={{ duration: 30, repeat: Infinity, ease: "easeInOut" }}
      />
      
      {/* Sand orb - center */}
      <motion.div
        className="absolute w-[300px] h-[300px] rounded-full opacity-20"
        style={{
          background: "radial-gradient(circle, rgba(247, 238, 221, 0.5) 0%, transparent 70%)",
          filter: "blur(40px)",
          top: "40%",
          left: "50%",
          transform: "translateX(-50%)",
        }}
        animate={{
          x: ["-50%", "-45%", "-55%", "-50%"],
          y: [0, 40, -20, 0],
        }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}

// ============================================
// AVATAR MENU
// ============================================

function AvatarMenu({ user }: { user: { firstName: string; email: string; avatarUrl?: string } }) {
  const [isOpen, setIsOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  const router = useRouter();
  const supabase = createClient();

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  const initials = user.firstName ? user.firstName[0].toUpperCase() : user.email[0].toUpperCase();

  return (
    <div className="fixed top-6 right-6 z-50">
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        className="w-10 h-10 rounded-full bg-secondary/80 backdrop-blur flex items-center justify-center text-sm font-medium hover:bg-secondary transition-colors"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        {user.avatarUrl ? (
          <img src={user.avatarUrl} alt="" className="w-full h-full rounded-full object-cover" />
        ) : (
          initials
        )}
      </motion.button>

      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              className="fixed inset-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
            />
            
            {/* Menu */}
            <motion.div
              className="absolute top-12 right-0 w-56 p-2 rounded-2xl bg-card/95 backdrop-blur-xl border border-border/50 shadow-xl"
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            >
              {/* User info */}
              <div className="px-3 py-2 mb-2">
                <p className="text-sm font-medium truncate">{user.firstName || "User"}</p>
                <p className="text-xs text-muted-foreground truncate">{user.email}</p>
              </div>

              <div className="h-px bg-border mb-2" />

              {/* Theme selector */}
              <div className="px-3 py-2">
                <p className="text-xs text-muted-foreground mb-2">Theme</p>
                <div className="flex gap-1">
                  {[
                    { value: "light", icon: Sun, label: "Light" },
                    { value: "dark", icon: Moon, label: "Dark" },
                    { value: "system", icon: Monitor, label: "System" },
                  ].map(({ value, icon: Icon }) => (
                    <button
                      key={value}
                      onClick={() => setTheme(value)}
                      className={`flex-1 p-2 rounded-lg transition-colors ${
                        theme === value
                          ? "bg-primary text-primary-foreground"
                          : "hover:bg-secondary"
                      }`}
                    >
                      <Icon className="w-4 h-4 mx-auto" />
                    </button>
                  ))}
                </div>
              </div>

              <div className="h-px bg-border my-2" />

              {/* Links */}
              <Link
                href="/settings"
                className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-secondary transition-colors"
                onClick={() => setIsOpen(false)}
              >
                <Settings className="w-4 h-4" />
                <span className="text-sm">Settings</span>
              </Link>

              <button
                onClick={handleSignOut}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-secondary transition-colors text-left"
              >
                <LogOut className="w-4 h-4" />
                <span className="text-sm">Sign out</span>
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

// ============================================
// MAGIC BAR
// ============================================

function MagicBar() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const isUrl = (text: string) => {
    try {
      new URL(text);
      return true;
    } catch {
      return text.includes(".") && !text.includes(" ");
    }
  };

  const handleSubmit = async () => {
    const value = input.trim();
    if (!value) return;

    setLoading(true);

    try {
      if (isUrl(value)) {
        let url = value;
        if (!url.startsWith("http")) url = "https://" + url;

        const response = await fetch("/api/queue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });

        if (!response.ok) throw new Error("Failed to add URL");
        toast.success("Link added");
      } else {
        const response = await fetch("/api/interests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keyword: value }),
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "Failed to add topic");
        }
        toast.success(`Topic "${value}" added`);
      }

      setInput("");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      className="magic-bar w-full max-w-xl mx-auto px-6 py-4"
      whileFocus={{ scale: 1.02 }}
    >
      <div className="flex items-center gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          placeholder="Paste a link or add a topic..."
          className="flex-1 bg-transparent text-center text-base placeholder:text-muted-foreground/50 focus:outline-none"
          disabled={loading}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !input.trim()}
          className="p-2 text-muted-foreground/50 hover:text-muted-foreground disabled:opacity-30"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
        </button>
      </div>
    </motion.div>
  );
}

// ============================================
// TOPIC PILLS
// ============================================

function TopicPills({ topics }: { topics: Topic[] }) {
  const [removing, setRemoving] = useState<string | null>(null);
  const router = useRouter();

  if (topics.length === 0) return null;

  const removeTopic = async (topic: Topic) => {
    setRemoving(topic.id);
    try {
      const response = await fetch(`/api/interests?keyword=${encodeURIComponent(topic.keyword)}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error();
      toast.success(`"${topic.display_name || topic.keyword}" removed`);
      router.refresh();
    } catch {
      toast.error("Failed to remove topic");
    } finally {
      setRemoving(null);
    }
  };

  return (
    <div className="flex flex-wrap justify-center gap-2 max-w-xl mx-auto">
      <AnimatePresence mode="popLayout">
        {topics.map((topic) => (
          <motion.span
            key={topic.id}
            layout
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="group tag-pill inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm"
          >
            <span className="text-[hsl(0_0%_10%)] opacity-60">#</span>
            <span>{topic.display_name || topic.keyword}</span>
            <motion.button
              onClick={() => removeTopic(topic)}
              disabled={removing === topic.id}
              className="opacity-0 group-hover:opacity-100 ml-0.5 -mr-1 p-0.5 rounded-full hover:bg-black/5 dark:hover:bg-white/10"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <X className="w-3 h-3" />
            </motion.button>
          </motion.span>
        ))}
      </AnimatePresence>
    </div>
  );
}

// ============================================
// PLAYER POD + SOURCES PANEL
// ============================================

function PlayerPod({ episode }: { episode: Episode }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(episode.audio_duration || 0);
  const [showSources, setShowSources] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  const sources = episode.sources_data || [];
  
  // Playback speed options
  const SPEED_OPTIONS = [1, 1.25, 1.5, 2];

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => setCurrentTime(audio.currentTime);
    const handleLoadedMetadata = () => setDuration(audio.duration);
    const handleEnded = () => setIsPlaying(false);

    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("loadedmetadata", handleLoadedMetadata);
    audio.addEventListener("ended", handleEnded);

    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: episode.title,
        artist: "Keernel",
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
    if (isPlaying) audio.pause();
    else audio.play();
    setIsPlaying(!isPlaying);
  };

  const skip = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, Math.min(duration, audio.currentTime + seconds));
  };

  const cyclePlaybackRate = () => {
    const audio = audioRef.current;
    if (!audio) return;
    
    const currentIndex = SPEED_OPTIONS.indexOf(playbackRate);
    const nextIndex = (currentIndex + 1) % SPEED_OPTIONS.length;
    const newRate = SPEED_OPTIONS[nextIndex];
    
    audio.playbackRate = newRate;
    setPlaybackRate(newRate);
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  const springConfig = { type: "spring" as const, stiffness: 300, damping: 30 };

  return (
    <>
      <audio ref={audioRef} src={episode.audio_url} preload="metadata" />

      {/* Sources Panel */}
      <AnimatePresence>
        {showSources && (
          <motion.div
            className="fixed bottom-28 left-1/2 z-40 w-[90%] max-w-[560px]"
            style={{ x: "-50%" }}
            initial={{ y: "100%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
            transition={springConfig}
          >
            <div className="sources-panel p-4 max-h-[50vh] overflow-y-auto scrollbar-hide">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-serif text-lg font-medium">Sources</h3>
                <button
                  onClick={() => setShowSources(false)}
                  className="p-2 rounded-full hover:bg-secondary"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {sources.length > 0 ? (
                <div className="space-y-2">
                  {sources.map((source, idx) => {
                    const meta = getSourceMeta(source.url);
                    const favicon = getFaviconUrl(source.url);

                    return (
                      <motion.a
                        key={idx}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`flex items-center gap-3 p-3 rounded-xl ${meta.bgClass} hover:opacity-80 transition-opacity group`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.05 }}
                      >
                        {/* Favicon */}
                        <div 
                          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                          style={{ backgroundColor: `${meta.color}15` }}
                        >
                          {favicon ? (
                            <img src={favicon} alt="" className="w-4 h-4" />
                          ) : (
                            <div 
                              className="w-3 h-3 rounded-full" 
                              style={{ backgroundColor: meta.color }}
                            />
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{source.title}</p>
                          <p className="text-xs text-muted-foreground font-mono">{source.domain}</p>
                        </div>

                        <ExternalLink 
                          className="w-4 h-4 opacity-0 group-hover:opacity-50 flex-shrink-0" 
                        />
                      </motion.a>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No sources available
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Player Pod */}
      <motion.div
        className="fixed bottom-6 left-1/2 z-50"
        style={{ x: "-50%" }}
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={springConfig}
      >
        <div className="player-pod w-[90vw] max-w-[620px] px-4 py-3">
          <div className="flex items-center gap-3">
            {/* Skip Back 15s */}
            <motion.button
              onClick={() => skip(-15)}
              className="p-2 text-muted-foreground hover:text-foreground transition-colors"
              whileTap={{ scale: 0.9 }}
              title="Reculer 15s"
            >
              <SkipBack className="w-4 h-4" />
            </motion.button>

            {/* Play Button - CREAM background */}
            <motion.button
              onClick={togglePlay}
              className="relative w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 bg-[hsl(36_40%_95%)] dark:bg-[hsl(36_40%_95%)]"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <span className="text-[hsl(0_0%_10%)]">
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
              </span>
            </motion.button>

            {/* Skip Forward 15s */}
            <motion.button
              onClick={() => skip(15)}
              className="p-2 text-muted-foreground hover:text-foreground transition-colors"
              whileTap={{ scale: 0.9 }}
              title="Avancer 15s"
            >
              <SkipForward className="w-4 h-4" />
            </motion.button>

            {/* Title + Progress */}
            <div className="flex-1 min-w-0">
              <p className="font-serif text-sm font-medium truncate">{episode.title}</p>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 h-1 rounded-full bg-secondary/50 overflow-hidden">
                  <motion.div
                    className="h-full rounded-full bg-[hsl(36_40%_95%)]"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground flex-shrink-0">
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              </div>
            </div>

            {/* Playback Speed */}
            <motion.button
              onClick={cyclePlaybackRate}
              className="px-2 py-1 rounded-md text-xs font-mono text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              whileTap={{ scale: 0.95 }}
              title="Vitesse de lecture"
            >
              {playbackRate}x
            </motion.button>

            {/* Sources Button */}
            <motion.button
              onClick={() => setShowSources(!showSources)}
              className={`p-2 rounded-full flex-shrink-0 ${
                showSources
                  ? "bg-[#C5B358]/20 text-[#C5B358]"
                  : "hover:bg-secondary text-muted-foreground"
              }`}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Layers className="w-4 h-4" />
            </motion.button>
          </div>
        </div>
      </motion.div>
    </>
  );
}

// ============================================
// GENERATE BUTTON
// ============================================

function GenerateButton({ pendingCount, hasTopics }: { pendingCount: number; hasTopics: boolean }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/generate", { method: "POST" });
      if (!response.ok) throw new Error();
      toast.success("Generating your Keernel...");
      setTimeout(() => router.refresh(), 3000);
    } catch {
      toast.error("Generation failed");
    } finally {
      setLoading(false);
    }
  };

  if (!hasTopics && pendingCount === 0) {
    return (
      <button
        disabled
        className="w-full max-w-xs mx-auto block px-6 py-3 rounded-full bg-secondary text-muted-foreground text-sm font-mono"
      >
        Add topics to get started
      </button>
    );
  }

  // btn-generate: bg charcoal, text laiton, halo charcoal
  return (
    <motion.button
      onClick={handleGenerate}
      disabled={loading || pendingCount === 0}
      className="w-full max-w-xs mx-auto block btn-generate px-6 py-3 text-sm"
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      {loading ? (
        <span className="flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Generating...
        </span>
      ) : (
        `Generate Keernel${pendingCount > 0 ? ` (${pendingCount})` : ""}`
      )}
    </motion.button>
  );
}

// ============================================
// MAIN DASHBOARD
// ============================================

export function KernelDashboard({ 
  user, 
  episode, 
  topics, 
  manualContent, 
  pendingCount 
}: KernelDashboardProps) {
  const hasTopics = topics.length > 0;
  const { resolvedTheme } = useTheme();

  return (
    <div className="min-h-screen relative">
      {/* Floating orbs - light mode only */}
      <FloatingOrbs />

      {/* Avatar menu - top right */}
      <AvatarMenu user={user} />

      {/* Main content - centered */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6 py-20">
        {/* Logo - SVG based on theme */}
        <motion.div
          className="mb-6"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <img 
            src={resolvedTheme === "dark" ? "/logo-sable.svg" : "/logo-charcoal.svg"}
            alt="Keernel"
            className="w-16 h-16"
          />
        </motion.div>

        {/* Greeting - Wittgenstein Semi Bold 600 */}
        <motion.div
          className="text-center mb-10"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <h1 className="title-keernel text-4xl md:text-5xl mb-2">
            Bonjour{user.firstName ? `, ${user.firstName}` : ""}
          </h1>
          <p className="text-muted-foreground text-sm tracking-wide font-mono">
            Votre podcast quotidien vous attend
          </p>
        </motion.div>

        {/* Magic Bar */}
        <motion.div
          className="w-full mb-6"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <MagicBar />
        </motion.div>

        {/* Topics */}
        <motion.div
          className="w-full mb-10"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <TopicPills topics={topics} />
        </motion.div>

        {/* Generate Button */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <GenerateButton pendingCount={pendingCount} hasTopics={hasTopics} />
        </motion.div>
      </div>

      {/* Player Pod */}
      {episode && <PlayerPod episode={episode} />}
    </div>
  );
}
