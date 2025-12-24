"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Play, Pause, Layers, X, ExternalLink, Link2, Loader2,
  Settings, LogOut, Sun, Moon, Monitor, User, SkipBack, SkipForward,
  Clock, ChevronDown, FileText, Calendar
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
  report_url?: string;
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

interface HistoryItem {
  id: string;
  title: string;
  audioUrl: string;
  duration: number;
  sourcesCount: number;
  reportUrl?: string;
  createdAt: string;
  date: string;
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

function getSourceMeta(url: string): { type: "video" | "podcast" | "article"; color: string; bgClass: string } {
  const domain = url.toLowerCase();
  
  if (domain.includes("youtube.com") || domain.includes("youtu.be") || 
      domain.includes("vimeo.com") || domain.includes("twitch.tv")) {
    return { type: "video", color: "#C5B358", bgClass: "bg-brass/5 dark:bg-brass/10" };
  }
  
  if (domain.includes("spotify.com") || domain.includes("podcasts.apple.com") ||
      domain.includes("podcasts.google.com") || domain.includes("soundcloud.com")) {
    return { type: "podcast", color: "#C5B358", bgClass: "bg-brass/5 dark:bg-brass/10" };
  }
  
  return { type: "article", color: "#A855F7", bgClass: "bg-violet-500/5 dark:bg-violet-500/10" };
}

function getFaviconUrl(url: string): string {
  try {
    const domain = new URL(url).hostname;
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;
  } catch {
    return "";
  }
}

// ============================================
// FLOATING ORBS
// ============================================

function FloatingOrbs() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted || resolvedTheme === "dark") return null;

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
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
    </div>
  );
}

// ============================================
// HISTORY MENU (NEW)
// ============================================

function HistoryMenu({ onSelectEpisode }: { onSelectEpisode?: (episode: HistoryItem) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && history.length === 0) {
      fetchHistory();
    }
  }, [isOpen]);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/history?period=week&limit=7");
      const data = await response.json();
      setHistory(data.history || []);
    } catch (error) {
      console.error("Failed to fetch history:", error);
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="relative">
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 rounded-full bg-[hsl(36_50%_92%)] text-[hsl(0_0%_10%)] hover:bg-[hsl(36_45%_88%)] transition-colors text-sm font-display font-medium"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <Clock className="w-4 h-4" />
        <span>Cette semaine</span>
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="w-4 h-4 opacity-60" />
        </motion.div>
      </motion.button>

      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              className="fixed inset-0 z-40"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
            />

            <motion.div
              className="absolute top-full left-0 mt-2 w-80 z-50 rounded-2xl bg-card border border-border shadow-xl overflow-hidden"
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ duration: 0.2 }}
            >
              <div className="px-4 py-3 border-b border-border bg-secondary/30">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-brass" />
                  <span className="font-display font-medium">Dernières générations</span>
                </div>
              </div>

              <div className="max-h-80 overflow-y-auto">
                {loading ? (
                  <div className="p-4 text-center text-muted-foreground">
                    <div className="animate-spin w-5 h-5 border-2 border-brass border-t-transparent rounded-full mx-auto" />
                  </div>
                ) : history.length === 0 ? (
                  <div className="p-4 text-center text-muted-foreground text-sm">
                    Aucune génération cette semaine
                  </div>
                ) : (
                  <div className="py-2">
                    {history.map((item, index) => (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="group"
                      >
                        <div className="px-4 py-3 hover:bg-secondary/50 transition-colors">
                          <div className="text-xs text-muted-foreground mb-1 font-mono">
                            {item.date}
                          </div>
                          
                          <div className="font-display font-medium text-sm mb-2 truncate">
                            {item.title}
                          </div>
                          
                          <div className="flex items-center gap-3 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Play className="w-3 h-3" />
                              {formatDuration(item.duration)}
                            </span>
                            <span>{item.sourcesCount} sources</span>
                          </div>
                          
                          <div className="flex items-center gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            {onSelectEpisode && (
                              <button
                                onClick={() => {
                                  onSelectEpisode(item);
                                  setIsOpen(false);
                                }}
                                className="flex items-center gap-1 px-2 py-1 rounded-lg bg-brass/10 text-brass text-xs hover:bg-brass/20 transition-colors"
                              >
                                <Play className="w-3 h-3" />
                                Écouter
                              </button>
                            )}
                            
                            {item.reportUrl && (
                              <a
                                href={item.reportUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 px-2 py-1 rounded-lg bg-secondary text-foreground text-xs hover:bg-secondary/80 transition-colors"
                              >
                                <FileText className="w-3 h-3" />
                                Rapport
                              </a>
                            )}
                          </div>
                        </div>
                        
                        {index < history.length - 1 && (
                          <div className="mx-4 border-b border-border/50" />
                        )}
                      </motion.div>
                    ))}
                  </div>
                )}
              </div>

              {history.length > 0 && (
                <div className="px-4 py-3 border-t border-border bg-secondary/30">
                  <Link 
                    href="/history"
                    className="flex items-center justify-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Voir tout l'historique
                    <ExternalLink className="w-3 h-3" />
                  </Link>
                </div>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
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
            <motion.div
              className="fixed inset-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
            />

            <motion.div
              className="absolute top-full right-0 mt-2 w-56 rounded-2xl bg-card border border-border shadow-xl overflow-hidden"
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
            >
              <div className="px-4 py-3 border-b border-border">
                <p className="font-medium truncate">{user.firstName || "User"}</p>
                <p className="text-xs text-muted-foreground truncate">{user.email}</p>
              </div>

              <div className="p-2">
                <div className="px-2 py-1 text-xs text-muted-foreground">Thème</div>
                <div className="flex gap-1 px-2 pb-2">
                  {[
                    { value: "light", icon: Sun },
                    { value: "dark", icon: Moon },
                    { value: "system", icon: Monitor },
                  ].map(({ value, icon: Icon }) => (
                    <button
                      key={value}
                      onClick={() => setTheme(value)}
                      className={`flex-1 p-2 rounded-lg flex items-center justify-center ${
                        theme === value ? "bg-secondary" : "hover:bg-secondary/50"
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                    </button>
                  ))}
                </div>

                <Link href="/settings">
                  <button className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-secondary text-left">
                    <Settings className="w-4 h-4" />
                    <span className="text-sm">Settings</span>
                  </button>
                </Link>

                <button
                  onClick={handleSignOut}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-secondary text-left text-red-500"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="text-sm">Sign out</span>
                </button>
              </div>
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
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleSubmit = async () => {
    if (!url.trim()) return;
    
    setLoading(true);
    try {
      const response = await fetch("/api/content", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });

      if (response.ok) {
        toast.success("Content added to queue");
        setUrl("");
        router.refresh();
      } else {
        toast.error("Failed to add content");
      }
    } catch {
      toast.error("Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div 
      className="magic-bar w-full max-w-xl mx-auto flex items-center gap-3 px-4 py-3"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste a link to add to your podcast..."
        className="flex-1 bg-transparent outline-none text-sm font-mono placeholder:text-muted-foreground/50"
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
      />
      <button
        onClick={handleSubmit}
        disabled={loading || !url.trim()}
        className="p-2 rounded-full hover:bg-secondary disabled:opacity-50 transition-colors"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
      </button>
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
// PLAYER POD
// ============================================

function PlayerPod({ episode }: { episode: Episode }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(episode.audio_duration || 0);
  const [showSources, setShowSources] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  const sources = episode.sources_data || [];
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

  return (
    <>
      <audio ref={audioRef} src={episode.audio_url} preload="metadata" />

      <AnimatePresence>
        {showSources && (
          <motion.div
            className="fixed bottom-28 left-1/2 z-40 w-[90%] max-w-[560px]"
            style={{ x: "-50%" }}
            initial={{ y: "100%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
          >
            <div className="sources-panel p-4 max-h-[50vh] overflow-y-auto scrollbar-hide">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-serif text-lg font-medium">Sources</h3>
                <button onClick={() => setShowSources(false)} className="p-2 rounded-full hover:bg-secondary">
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
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${meta.color}15` }}>
                          {favicon ? <img src={favicon} alt="" className="w-4 h-4" /> : <div className="w-3 h-3 rounded-full" style={{ backgroundColor: meta.color }} />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{source.title}</p>
                          <p className="text-xs text-muted-foreground font-mono">{source.domain}</p>
                        </div>
                        <ExternalLink className="w-4 h-4 opacity-0 group-hover:opacity-50 flex-shrink-0" />
                      </motion.a>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">No sources available</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        className="fixed bottom-6 left-1/2 z-50"
        style={{ x: "-50%" }}
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
      >
        <div className="player-pod w-[90vw] max-w-[620px] px-4 py-3">
          <div className="flex items-center gap-3">
            <motion.button onClick={() => skip(-15)} className="p-2 text-muted-foreground hover:text-foreground transition-colors" whileTap={{ scale: 0.9 }}>
              <SkipBack className="w-4 h-4" />
            </motion.button>

            <motion.button
              onClick={togglePlay}
              className="relative w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 bg-[hsl(36_40%_95%)]"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <span className="text-[hsl(0_0%_10%)]">
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
              </span>
            </motion.button>

            <motion.button onClick={() => skip(15)} className="p-2 text-muted-foreground hover:text-foreground transition-colors" whileTap={{ scale: 0.9 }}>
              <SkipForward className="w-4 h-4" />
            </motion.button>

            <div className="flex-1 min-w-0">
              <p className="font-serif text-sm font-medium truncate">{episode.title}</p>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 h-1 rounded-full bg-secondary/50 overflow-hidden">
                  <motion.div className="h-full rounded-full bg-[hsl(36_40%_95%)]" style={{ width: `${progress}%` }} />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground flex-shrink-0">
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              </div>
            </div>

            <motion.button
              onClick={cyclePlaybackRate}
              className="px-2 py-1 rounded-md text-xs font-mono text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              whileTap={{ scale: 0.95 }}
            >
              {playbackRate}x
            </motion.button>

            <motion.button
              onClick={() => setShowSources(!showSources)}
              className={`p-2 rounded-full flex-shrink-0 ${showSources ? "bg-brass/20 text-brass" : "hover:bg-secondary text-muted-foreground"}`}
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
      <button disabled className="w-full max-w-xs mx-auto block px-6 py-3 rounded-full bg-secondary text-muted-foreground text-sm font-mono">
        Add topics to get started
      </button>
    );
  }

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
  const [currentEpisode, setCurrentEpisode] = useState<Episode | null>(episode);

  const handleSelectHistoryEpisode = (historyItem: HistoryItem) => {
    setCurrentEpisode({
      id: historyItem.id,
      title: historyItem.title,
      audio_url: historyItem.audioUrl,
      audio_duration: historyItem.duration,
      sources_data: [],
      report_url: historyItem.reportUrl
    });
  };

  return (
    <div className="min-h-screen relative">
      <FloatingOrbs />
      <AvatarMenu user={user} />

      {/* History Menu - Top Left */}
      <div className="fixed top-6 left-6 z-50">
        <HistoryMenu onSelectEpisode={handleSelectHistoryEpisode} />
      </div>

      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6 py-20">
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

        <motion.div
          className="w-full mb-6"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <MagicBar />
        </motion.div>

        <motion.div
          className="w-full mb-10"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <TopicPills topics={topics} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <GenerateButton pendingCount={pendingCount} hasTopics={hasTopics} />
        </motion.div>
      </div>

      {currentEpisode && <PlayerPod episode={currentEpisode} />}
    </div>
  );
}
