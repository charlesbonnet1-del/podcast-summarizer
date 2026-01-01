"use client";

import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Play, Pause, Layers, X, ExternalLink, Link2, Loader2,
  Settings, LogOut, Sun, Moon, Monitor, User, SkipBack, SkipForward,
  Clock, ChevronDown, FileText, Calendar, Plus
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
  signalWeights?: Record<string, number>;
}

// ============================================
// UTILITIES
// ============================================

// Elegant color palette for sources - alternating warm neutrals
const SOURCE_COLORS = [
  { bg: "bg-[#F5F5F7]", text: "text-[#3D3D3D]", domain: "text-muted-foreground", iconBg: "#E5E5E7" },      // Beige / Cream
  { bg: "bg-[#FAFAFA]", text: "text-[#2D2D2D]", domain: "text-[#7A7A7A]", iconBg: "#F0F0F0" },      // White / Light gray
  { bg: "bg-[#E5E5E7]", text: "text-[#4A4A4A]", domain: "text-tech-blue", iconBg: "#D4D4D8" },      // Sand / Taupe
  { bg: "bg-[#F8F6F3]", text: "text-[#3D3D3D]", domain: "text-[#9A8B7A]", iconBg: "#E5E0D8" },      // Off-white / Cream
  { bg: "bg-[#2D2D2D]", text: "text-[#F5F5F5]", domain: "text-[#A0A0A0]", iconBg: "#404040" },      // Charcoal
  { bg: "bg-[#1A1A1A]", text: "text-[#FFFFFF]", domain: "text-[#888888]", iconBg: "#333333" },      // Noir / Black
];

function getSourceColor(index: number) {
  return SOURCE_COLORS[index % SOURCE_COLORS.length];
}

function getSourceMeta(url: string): { type: "video" | "podcast" | "article"; color: string; bgClass: string } {
  const domain = url.toLowerCase();
  
  if (domain.includes("youtube.com") || domain.includes("youtu.be") || 
      domain.includes("vimeo.com") || domain.includes("twitch.tv")) {
    return { type: "video", color: "#00F0FF", bgClass: "bg-primary/5 dark:bg-primary/10" };
  }
  
  if (domain.includes("spotify.com") || domain.includes("podcasts.apple.com") ||
      domain.includes("podcasts.google.com") || domain.includes("soundcloud.com")) {
    return { type: "podcast", color: "#00F0FF", bgClass: "bg-primary/5 dark:bg-primary/10" };
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

// ============================================
// AURORA BACKGROUND - Premium animated gradient
// ============================================

function AuroraBackground() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  const isDark = resolvedTheme === "dark";

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {/* Base gradient mesh */}
      <div 
        className="absolute inset-0"
        style={{
          background: isDark 
            ? 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 240, 255, 0.15), transparent)'
            : 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 122, 255, 0.08), transparent)'
        }}
      />
      
      {/* Animated aurora blobs */}
      <motion.div
        className="absolute w-[800px] h-[800px] rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(0, 240, 255, 0.2) 0%, rgba(0, 150, 255, 0.1) 40%, transparent 70%)'
            : 'radial-gradient(circle, rgba(0, 122, 255, 0.12) 0%, rgba(0, 200, 255, 0.06) 40%, transparent 70%)',
          filter: 'blur(80px)',
          top: '-20%',
          right: '-10%',
        }}
        animate={{
          x: [0, 50, -30, 0],
          y: [0, -30, 50, 0],
          scale: [1, 1.1, 0.95, 1],
          rotate: [0, 10, -5, 0],
        }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      
      <motion.div
        className="absolute w-[600px] h-[600px] rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(120, 0, 255, 0.15) 0%, rgba(0, 240, 255, 0.08) 40%, transparent 70%)'
            : 'radial-gradient(circle, rgba(100, 0, 255, 0.08) 0%, rgba(0, 200, 255, 0.04) 40%, transparent 70%)',
          filter: 'blur(60px)',
          bottom: '0%',
          left: '-10%',
        }}
        animate={{
          x: [0, -40, 30, 0],
          y: [0, 40, -20, 0],
          scale: [1, 0.9, 1.15, 1],
          rotate: [0, -15, 10, 0],
        }}
        transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
      />

      <motion.div
        className="absolute w-[500px] h-[500px] rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(0, 255, 200, 0.12) 0%, transparent 60%)'
            : 'radial-gradient(circle, rgba(0, 200, 150, 0.06) 0%, transparent 60%)',
          filter: 'blur(70px)',
          top: '40%',
          left: '50%',
          transform: 'translateX(-50%)',
        }}
        animate={{
          scale: [1, 1.2, 0.9, 1],
          opacity: [0.5, 0.8, 0.4, 0.5],
        }}
        transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Noise texture overlay for grain effect */}
      <div 
        className="absolute inset-0 opacity-[0.015]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />
    </div>
  );
}

// ============================================
// PULSING LOGO - Animated concentric circles
// ============================================

function PulsingLogo() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  
  return (
    <div className="relative w-24 h-24 flex items-center justify-center">
      {/* Glow behind logo */}
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{
          background: isDark 
            ? 'radial-gradient(circle, rgba(0, 240, 255, 0.3) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(0, 122, 255, 0.2) 0%, transparent 70%)',
          filter: 'blur(20px)',
        }}
        animate={{
          scale: [1, 1.2, 1],
          opacity: [0.5, 0.8, 0.5],
        }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      />
      
      {/* SVG Animated Logo */}
      <svg viewBox="0 0 100 100" className="w-20 h-20 relative z-10">
        <defs>
          <linearGradient id="logoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={isDark ? "#00F0FF" : "#007AFF"} />
            <stop offset="100%" stopColor={isDark ? "#00D4AA" : "#00C6FF"} />
          </linearGradient>
        </defs>
        
        {/* Concentric circles with staggered pulse */}
        {[40, 32, 24, 16].map((r, i) => (
          <motion.circle
            key={r}
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke="url(#logoGradient)"
            strokeWidth={i === 3 ? 0 : 2}
            initial={{ scale: 1, opacity: 0.8 }}
            animate={{ 
              scale: [1, 1.05, 1],
              opacity: [0.6 + i * 0.1, 0.9, 0.6 + i * 0.1],
            }}
            transition={{ 
              duration: 2,
              delay: i * 0.2,
              repeat: Infinity,
              ease: "easeInOut"
            }}
            style={{ transformOrigin: '50px 50px' }}
          />
        ))}
        
        {/* Center filled circle */}
        <motion.circle
          cx="50"
          cy="50"
          r="12"
          fill="url(#logoGradient)"
          animate={{ 
            scale: [1, 1.1, 1],
          }}
          transition={{ 
            duration: 2,
            repeat: Infinity,
            ease: "easeInOut"
          }}
          style={{ transformOrigin: '50px 50px' }}
        />
      </svg>
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
  const [showDigest, setShowDigest] = useState<string | null>(null);
  const [digestData, setDigestData] = useState<Record<string, any[]>>({});
  const [loadingDigest, setLoadingDigest] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && history.length === 0) {
      fetchHistory();
    }
  }, [isOpen]);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/history?period=month&limit=30");
      const data = await response.json();
      setHistory(data.history || []);
    } catch (error) {
      console.error("Failed to fetch history:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDigest = async (episodeId: string) => {
    if (digestData[episodeId]) {
      setShowDigest(showDigest === episodeId ? null : episodeId);
      return;
    }
    
    setLoadingDigest(episodeId);
    try {
      const response = await fetch(`/api/digests?episode_id=${episodeId}`);
      const data = await response.json();
      setDigestData(prev => ({ ...prev, [episodeId]: data.digests || [] }));
      setShowDigest(episodeId);
    } catch (error) {
      console.error("Failed to fetch digest:", error);
    } finally {
      setLoadingDigest(null);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const isOlderThan7Days = (dateStr: string) => {
    const episodeDate = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - episodeDate.getTime()) / (1000 * 60 * 60 * 24));
    return diffDays > 7;
  };

  return (
    <div className="relative">
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 rounded-full bg-card border border-border text-foreground hover:bg-muted transition-colors text-sm font-display font-medium"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <Clock className="w-4 h-4" />
        <span>Historique</span>
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
              className="absolute top-full left-0 mt-2 w-96 z-50 rounded-2xl bg-card border border-border shadow-xl overflow-hidden"
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ duration: 0.2 }}
            >
              <div className="px-4 py-3 border-b border-border bg-secondary/30">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-primary" />
                  <span className="font-display font-medium">Vos épisodes</span>
                </div>
              </div>

              <div className="max-h-[60vh] overflow-y-auto">
                {loading ? (
                  <div className="p-4 text-center text-muted-foreground">
                    <div className="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
                  </div>
                ) : history.length === 0 ? (
                  <div className="p-4 text-center text-muted-foreground text-sm">
                    Aucun épisode
                  </div>
                ) : (
                  <div className="py-2">
                    {history.map((item, index) => {
                      const isOld = isOlderThan7Days(item.createdAt);
                      const digests = digestData[item.id] || [];
                      const isDigestOpen = showDigest === item.id;
                      
                      return (
                        <motion.div
                          key={item.id}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: index * 0.03 }}
                          className="group"
                        >
                          <div className="px-4 py-3 hover:bg-secondary/50 transition-colors">
                            <div className="flex items-center justify-between mb-1">
                              <div className="text-xs text-muted-foreground font-mono">
                                {item.date}
                              </div>
                              {isOld && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#E5E5E7] dark:bg-[#333] text-muted-foreground dark:text-[#999]">
                                  Archive
                                </span>
                              )}
                            </div>
                            
                            <div className="font-display font-medium text-sm mb-2 truncate">
                              {item.title}
                            </div>
                            
                            <div className="flex items-center gap-3 text-xs text-muted-foreground mb-2">
                              <span className="flex items-center gap-1">
                                <Play className="w-3 h-3" />
                                {formatDuration(item.duration)}
                              </span>
                              <span>{item.sourcesCount} sources</span>
                            </div>
                            
                            <div className="flex items-center gap-2">
                              {/* Écouter - seulement si < 7 jours */}
                              {!isOld && onSelectEpisode && (
                                <button
                                  onClick={() => {
                                    onSelectEpisode(item);
                                    setIsOpen(false);
                                  }}
                                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-primary/10 text-primary text-xs hover:bg-primary/20 transition-colors"
                                >
                                  <Play className="w-3 h-3" />
                                  Écouter
                                </button>
                              )}
                              
                              {/* Digest - toujours visible */}
                              <button
                                onClick={() => fetchDigest(item.id)}
                                className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
                                  isDigestOpen 
                                    ? "bg-[#2D2D2D] text-white" 
                                    : "bg-[#F5F5F7] dark:bg-[#333] text-[#3D3D3D] dark:text-[#DDD] hover:bg-[#E5E5E7] dark:hover:bg-[#444]"
                                }`}
                              >
                                {loadingDigest === item.id ? (
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                  <FileText className="w-3 h-3" />
                                )}
                                Digest
                              </button>
                              
                              {/* Rapport si disponible */}
                              {item.reportUrl && (
                                <a
                                  href={item.reportUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-secondary text-foreground text-xs hover:bg-secondary/80 transition-colors"
                                >
                                  <ExternalLink className="w-3 h-3" />
                                </a>
                              )}
                            </div>
                          </div>
                          
                          {/* Digest panel */}
                          <AnimatePresence>
                            {isDigestOpen && (
                              <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="overflow-hidden bg-[#FAF9F7] dark:bg-[#1A1A1A] border-y border-border/50"
                              >
                                <div className="px-4 py-3 space-y-3">
                                  {digests.length === 0 ? (
                                    <p className="text-xs text-muted-foreground text-center py-2">
                                      Pas de digest disponible
                                    </p>
                                  ) : (
                                    digests.map((digest: any, idx: number) => (
                                      <div 
                                        key={digest.id}
                                        className={`p-3 rounded-xl ${SOURCE_COLORS[idx % SOURCE_COLORS.length].bg}`}
                                      >
                                        <div className="flex items-start justify-between gap-2 mb-2">
                                          <p className={`text-sm font-medium ${SOURCE_COLORS[idx % SOURCE_COLORS.length].text}`}>
                                            {digest.title}
                                          </p>
                                          <a
                                            href={digest.source_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="p-1 rounded hover:bg-black/5 transition-colors flex-shrink-0"
                                          >
                                            <ExternalLink className={`w-3 h-3 ${SOURCE_COLORS[idx % SOURCE_COLORS.length].domain}`} />
                                          </a>
                                        </div>
                                        
                                        {digest.key_insights && digest.key_insights.length > 0 && (
                                          <div className="space-y-1">
                                            {digest.key_insights.slice(0, 3).map((insight: string, i: number) => (
                                              <div key={i} className={`flex items-start gap-1.5 text-xs ${SOURCE_COLORS[idx % SOURCE_COLORS.length].text}`}>
                                                <span className="mt-1.5 w-1 h-1 rounded-full bg-current opacity-40 flex-shrink-0" />
                                                {insight}
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    ))
                                  )}
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                          
                          {index < history.length - 1 && !isDigestOpen && (
                            <div className="mx-4 border-b border-border/50" />
                          )}
                        </motion.div>
                      );
                    })}
                  </div>
                )}
              </div>
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
  const [isFocused, setIsFocused] = useState(false);
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
      className="w-full max-w-xl mx-auto relative"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      {/* Animated gradient border */}
      <motion.div
        className="absolute -inset-[1px] rounded-2xl opacity-0"
        style={{
          background: 'linear-gradient(90deg, #00F0FF, #007AFF, #00F0FF)',
          backgroundSize: '200% 100%',
        }}
        animate={isFocused ? {
          opacity: 1,
          backgroundPosition: ['0% 50%', '100% 50%', '0% 50%'],
        } : { opacity: 0 }}
        transition={{ 
          backgroundPosition: { duration: 3, repeat: Infinity, ease: "linear" },
          opacity: { duration: 0.3 }
        }}
      />
      
      {/* Glow effect on focus */}
      <motion.div
        className="absolute -inset-2 rounded-3xl pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(0, 240, 255, 0.15) 0%, transparent 70%)',
          filter: 'blur(20px)',
        }}
        animate={{ opacity: isFocused ? 1 : 0 }}
        transition={{ duration: 0.3 }}
      />
      
      {/* Input container */}
      <div className="relative flex items-center gap-3 px-5 py-4 rounded-2xl bg-card/80 backdrop-blur-xl border border-border/50">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder="Paste a link to add to your podcast..."
          className="flex-1 bg-transparent outline-none text-sm font-mono placeholder:text-muted-foreground/50"
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
        <motion.button
          onClick={handleSubmit}
          disabled={loading || !url.trim()}
          className="p-2.5 rounded-xl bg-primary/10 hover:bg-primary/20 disabled:opacity-50 transition-all"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-primary" />
          ) : (
            <Link2 className="w-4 h-4 text-primary" />
          )}
        </motion.button>
      </div>
    </motion.div>
  );
}

// ============================================
// SIGNAL RADAR WIDGET (replaces TopicPills)
// ============================================

function SignalRadarWidget({ weights }: { weights: Record<string, number> }) {
  const [showMixer, setShowMixer] = useState(false);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  // Calculate average weight per vertical (V13 - 16 Topics)
  const VERTICALS = [
    { id: "tech", label: "Tech", topics: ["ia", "cyber", "deep_tech"] },
    { id: "science", label: "Science", topics: ["health", "space", "energy"] },
    { id: "economie", label: "Économie", topics: ["crypto", "macro", "deals"] },
    { id: "monde", label: "Monde", topics: ["asia", "regulation", "resources"] },
    { id: "influence", label: "Influence", topics: ["info", "attention", "persuasion"] },
  ];

  const verticalWeights = VERTICALS.map(v => {
    const topicWeights = v.topics.map(t => weights[t] ?? 50);
    const avg = Math.round(topicWeights.reduce((a, b) => a + b, 0) / topicWeights.length);
    return { ...v, weight: avg };
  });

  // Radar chart calculations
  const size = 200;
  const centerX = size / 2;
  const centerY = size / 2;
  const maxRadius = (size / 2) - 40;

  const getPoint = (index: number, value: number) => {
    const angle = (Math.PI * 2 * index) / 5 - Math.PI / 2;
    const radius = (value / 100) * maxRadius;
    return {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  };

  const dataPoints = verticalWeights.map((v, i) => getPoint(i, v.weight));
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  const labelRadius = maxRadius + 30;
  const labelPositions = verticalWeights.map((_, i) => {
    const angle = (Math.PI * 2 * i) / 5 - Math.PI / 2;
    return {
      x: centerX + labelRadius * Math.cos(angle),
      y: centerY + labelRadius * Math.sin(angle),
    };
  });

  return (
    <>
      <motion.button
        onClick={() => setShowMixer(true)}
        className="relative group mx-auto"
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.98 }}
      >
        {/* Outer glow on hover */}
        <motion.div
          className="absolute -inset-8 rounded-full pointer-events-none"
          style={{
            background: `radial-gradient(circle, ${isDark ? 'rgba(0, 240, 255, 0.1)' : 'rgba(0, 122, 255, 0.08)'} 0%, transparent 70%)`,
            filter: 'blur(20px)',
          }}
          initial={{ opacity: 0 }}
          whileHover={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        />

        <div className="relative" style={{ width: size, height: size }}>
          <svg width={size} height={size} className="overflow-visible">
            <defs>
              {/* Gradient for filled area */}
              <linearGradient id="radarGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor={isDark ? "#00F0FF" : "#007AFF"} stopOpacity="0.3" />
                <stop offset="50%" stopColor={isDark ? "#00D4AA" : "#00C6FF"} stopOpacity="0.15" />
                <stop offset="100%" stopColor={isDark ? "#7B00FF" : "#0066FF"} stopOpacity="0.2" />
              </linearGradient>
              
              {/* Glow filter */}
              <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                <feMerge>
                  <feMergeNode in="coloredBlur"/>
                  <feMergeNode in="SourceGraphic"/>
                </feMerge>
              </filter>
            </defs>

            {/* Grid rings - dotted style */}
            {[20, 40, 60, 80, 100].map((ring) => {
              const points = Array.from({ length: 5 }, (_, i) => {
                const p = getPoint(i, ring);
                return `${p.x},${p.y}`;
              }).join(' ');
              return (
                <polygon
                  key={ring}
                  points={points}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={0.06}
                  strokeWidth={1}
                  strokeDasharray="2 4"
                />
              );
            })}

            {/* Axis lines - very subtle */}
            {verticalWeights.map((_, i) => {
              const endPoint = getPoint(i, 100);
              return (
                <line
                  key={i}
                  x1={centerX}
                  y1={centerY}
                  x2={endPoint.x}
                  y2={endPoint.y}
                  stroke="currentColor"
                  strokeOpacity={0.05}
                  strokeWidth={1}
                />
              );
            })}

            {/* Animated data shape with gradient fill */}
            <motion.path
              d={dataPath}
              fill="url(#radarGradient)"
              stroke={isDark ? "#00F0FF" : "#007AFF"}
              strokeWidth={2.5}
              filter="url(#glow)"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 1, ease: "easeOut" }}
            />

            {/* Animated data points with pulsing glow */}
            {dataPoints.map((point, i) => (
              <g key={i}>
                {/* Glow behind point */}
                <motion.circle
                  cx={point.x}
                  cy={point.y}
                  r={8}
                  fill={isDark ? "#00F0FF" : "#007AFF"}
                  opacity={0.3}
                  initial={{ scale: 0 }}
                  animate={{ 
                    scale: [1, 1.5, 1],
                    opacity: [0.3, 0.1, 0.3],
                  }}
                  transition={{ 
                    delay: 0.5 + i * 0.1,
                    duration: 2,
                    repeat: Infinity,
                    ease: "easeInOut"
                  }}
                />
                {/* Main point */}
                <motion.circle
                  cx={point.x}
                  cy={point.y}
                  r={5}
                  fill={isDark ? "#00F0FF" : "#007AFF"}
                  stroke="white"
                  strokeWidth={2}
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.3 + i * 0.1, duration: 0.4, type: "spring" }}
                />
              </g>
            ))}

            {/* Center decoration */}
            <circle cx={centerX} cy={centerY} r={3} fill="currentColor" opacity={0.1} />
          </svg>

          {/* Labels with enhanced styling */}
          {verticalWeights.map((vertical, i) => {
            const pos = labelPositions[i];
            return (
              <motion.div
                key={vertical.id}
                className="absolute pointer-events-none"
                style={{ 
                  left: pos.x, 
                  top: pos.y,
                  transform: 'translate(-50%, -50%)'
                }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 + i * 0.1 }}
              >
                <div className="flex flex-col items-center">
                  <span className="text-[11px] font-display font-semibold text-foreground whitespace-nowrap">
                    {vertical.label}
                  </span>
                  <span 
                    className="text-[10px] font-mono font-medium"
                    style={{ color: isDark ? '#00F0FF' : '#007AFF' }}
                  >
                    {vertical.weight}%
                  </span>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Hover overlay with + button */}
        <motion.div 
          className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300"
        >
          <motion.div 
            className="w-12 h-12 rounded-full flex items-center justify-center shadow-lg"
            style={{
              background: isDark 
                ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 100%)'
                : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 100%)',
              boxShadow: isDark 
                ? '0 0 30px rgba(0, 240, 255, 0.4)'
                : '0 0 30px rgba(0, 122, 255, 0.3)',
            }}
            whileHover={{ scale: 1.1 }}
          >
            <Plus className="w-6 h-6 text-white" />
          </motion.div>
        </motion.div>
      </motion.button>

      {/* Signal Mixer Modal */}
      <SignalMixerModal 
        isOpen={showMixer}
        onClose={() => setShowMixer(false)}
        weights={weights}
      />
    </>
  );
}


// ============================================
// SIGNAL MIXER MODAL - Vertical-First Design
// ============================================

// Verticals with their topics
const VERTICALS = [
  {
    id: "tech",
    name: "Tech",
    topics: [
      { id: "ia", label: "IA, Robotique & Hardware", description: "AGI, LLMs, robots et puces" },
      { id: "cyber", label: "Cybersécurité", description: "Menaces, zero-days et défenses" },
      { id: "deep_tech", label: "Deep Tech", description: "Quantum, fusion et matériaux" },
    ]
  },
  {
    id: "science",
    name: "Science",
    topics: [
      { id: "health", label: "Santé & Longévité", description: "Biotech, anti-âge et biohacking" },
      { id: "space", label: "Espace", description: "Économie orbitale et exploration" },
      { id: "energy", label: "Énergie", description: "Mix énergétique et stockage" },
    ]
  },
  {
    id: "economics",
    name: "Économie",
    topics: [
      { id: "crypto", label: "Crypto", description: "Protocoles et décentralisation" },
      { id: "macro", label: "Macro-économie", description: "Banques centrales et tendances" },
      { id: "deals", label: "M&A & VC", description: "Levées, acquisitions et marchés" },
    ]
  },
  {
    id: "world",
    name: "Monde",
    topics: [
      { id: "asia", label: "Asie", description: "Tech chinoise et émergents" },
      { id: "regulation", label: "Régulation", description: "Lois et compliance" },
      { id: "resources", label: "Ressources", description: "Matières et supply chains" },
    ]
  },
  {
    id: "influence",
    name: "Influence",
    topics: [
      { id: "info", label: "Guerre de l'Information", description: "Désinformation et influence ops" },
      { id: "attention", label: "Marchés de l'Attention", description: "Algorithmes et plateformes" },
      { id: "persuasion", label: "Stratégies de Persuasion", description: "Nudges et design cognitif" },
    ]
  }
];

// Flatten topics for weight management
const ALL_TOPICS = VERTICALS.flatMap(v => v.topics.map(t => ({ ...t, category: v.name })));

function getSignalLabel(weight: number) {
  if (weight >= 80) return { label: "Focus", color: "text-[#00F0FF]" };      // brass
  if (weight >= 50) return { label: "Actif", color: "text-tech-blue" };      // sand
  if (weight >= 20) return { label: "Passif", color: "text-muted-foreground" };     // taupe
  if (weight > 0) return { label: "Faible", color: "text-muted-foreground" };
  return { label: "Off", color: "text-muted-foreground/50" };
}

function SignalMixerModal({ 
  isOpen, 
  onClose, 
  weights: initialWeights 
}: { 
  isOpen: boolean; 
  onClose: () => void;
  weights: Record<string, number>;
}) {
  const [weights, setWeights] = useState<Record<string, number>>(() => {
    const defaults: Record<string, number> = {};
    ALL_TOPICS.forEach(t => defaults[t.id] = 50);
    return { ...defaults, ...initialWeights };
  });
  const [expandedVertical, setExpandedVertical] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [mounted, setMounted] = useState(false);
  const router = useRouter();

  // Portal needs to wait for client-side mount
  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isOpen) {
      const defaults: Record<string, number> = {};
      ALL_TOPICS.forEach(t => defaults[t.id] = 50);
      setWeights({ ...defaults, ...initialWeights });
      setExpandedVertical(null);
    }
  }, [isOpen, initialWeights]);

  // Calculate vertical average weight
  const getVerticalWeight = (verticalId: string) => {
    const vertical = VERTICALS.find(v => v.id === verticalId);
    if (!vertical) return 50;
    const topicWeights = vertical.topics.map(t => weights[t.id] ?? 50);
    return Math.round(topicWeights.reduce((a, b) => a + b, 0) / topicWeights.length);
  };

  // Update all topics in a vertical
  const updateVerticalWeight = (verticalId: string, value: number) => {
    const vertical = VERTICALS.find(v => v.id === verticalId);
    if (!vertical) return;
    
    setWeights(prev => {
      const newWeights = { ...prev };
      vertical.topics.forEach(t => {
        newWeights[t.id] = value;
      });
      return newWeights;
    });
  };

  // Update single topic
  const updateTopicWeight = (topicId: string, value: number) => {
    setWeights(prev => ({ ...prev, [topicId]: value }));
  };

  const saveWeights = async () => {
    setSaving(true);
    try {
      const response = await fetch("/api/signal-weights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weights }),
      });
      if (!response.ok) throw new Error();
      toast.success("Signal Mixer sauvegardé");
      router.refresh();
      onClose();
    } catch {
      toast.error("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen || !mounted) return null;

  // Use Portal to render at document.body level, above all other elements
  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop that covers EVERYTHING including fixed headers */}
          <motion.div
            className="fixed inset-0 bg-[hsl(var(--background))] dark:bg-[#1A1A1A]"
            style={{ zIndex: 99998 }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          
          {/* Modal Content */}
          <motion.div
            className="fixed inset-0 flex flex-col"
            style={{ zIndex: 99999, paddingBottom: '96px' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            {/* Header - Fixed */}
            <div className="shrink-0 px-4 pt-6 pb-2 bg-[hsl(var(--background))] dark:bg-[#1A1A1A]">
              <div className="max-w-lg mx-auto flex items-start justify-between">
                <div>
                  <h2 className="font-display text-2xl font-bold">Signal Mixer</h2>
                  <p className="text-sm text-muted-foreground mt-1">
                    Ajustez par verticale, affinez par topic
                  </p>
                </div>
                <button
                  onClick={onClose}
                  className="w-10 h-10 rounded-full bg-[#E5E5E7] dark:bg-[#333] flex items-center justify-center hover:bg-[#DDD0BC] dark:hover:bg-[#444] transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

          {/* Scrollable Content Area */}
          <div className="flex-1 overflow-y-auto px-4">
            <div className="max-w-lg mx-auto space-y-3 pb-4">
              {/* Verticals */}
              {VERTICALS.map((vertical) => {
                const verticalWeight = getVerticalWeight(vertical.id);
                const signal = getSignalLabel(verticalWeight);
                const isExpanded = expandedVertical === vertical.id;
                
                return (
                  <motion.div
                    key={vertical.id}
                    className="rounded-xl bg-[#F0E6D3] dark:bg-[#252525] border border-[#E5E5E7] dark:border-[#333] overflow-hidden"
                    layout
                  >
                    {/* Vertical Header with Slider */}
                    <div className="p-4">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="font-display font-semibold text-base">
                            {vertical.name}
                          </span>
                          <span className={`text-xs font-mono ${signal.color}`}>
                            {verticalWeight}%
                          </span>
                        </div>
                        <button
                          onClick={() => setExpandedVertical(isExpanded ? null : vertical.id)}
                          className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
                        >
                          {isExpanded ? "Réduire" : "Détailler"}
                          <ChevronDown className={`w-3 h-3 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                        </button>
                      </div>

                      {/* Vertical Slider */}
                      <input
                        type="range"
                        min="0"
                        max="100"
                        step="10"
                        value={verticalWeight}
                        onChange={(e) => updateVerticalWeight(vertical.id, parseInt(e.target.value))}
                        className="w-full h-2 rounded-full appearance-none cursor-pointer bg-[#E5E5E7] dark:bg-[#333]
                          [&::-webkit-slider-thumb]:appearance-none
                          [&::-webkit-slider-thumb]:w-5
                          [&::-webkit-slider-thumb]:h-5
                          [&::-webkit-slider-thumb]:rounded-full
                          [&::-webkit-slider-thumb]:bg-white
                          [&::-webkit-slider-thumb]:border-2
                          [&::-webkit-slider-thumb]:border-[#00F0FF]
                          [&::-webkit-slider-thumb]:shadow-md
                          [&::-webkit-slider-thumb]:cursor-pointer"
                        style={{
                          background: `linear-gradient(to right, 
                            ${verticalWeight >= 80 ? '#00F0FF' : verticalWeight >= 50 ? '#007AFF' : verticalWeight >= 20 ? '#4DA3FF' : '#9ca3af'} 0%, 
                            ${verticalWeight >= 80 ? '#00F0FF' : verticalWeight >= 50 ? '#007AFF' : verticalWeight >= 20 ? '#4DA3FF' : '#9ca3af'} ${verticalWeight}%, 
                            #E5E5E7 ${verticalWeight}%, 
                            #E5E5E7 100%)`
                        }}
                      />
                    </div>

                    {/* Expanded Topics */}
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="border-t border-[#E5E5E7] dark:border-[#333]"
                        >
                          <div className="p-3 space-y-2 bg-[#EBE1CF] dark:bg-[#222]">
                            {vertical.topics.map((topic) => {
                              const topicWeight = weights[topic.id] ?? 50;
                              const topicSignal = getSignalLabel(topicWeight);
                              
                              return (
                                <div key={topic.id} className="flex items-center gap-3">
                                  <div className="min-w-[90px]">
                                    <span className="text-sm font-medium">{topic.label}</span>
                                    <p className="text-[10px] text-muted-foreground leading-tight">
                                      {topic.description}
                                    </p>
                                  </div>
                                  
                                  <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    step="10"
                                    value={topicWeight}
                                    onChange={(e) => updateTopicWeight(topic.id, parseInt(e.target.value))}
                                    className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer bg-[#E5E5E7] dark:bg-[#333]
                                      [&::-webkit-slider-thumb]:appearance-none
                                      [&::-webkit-slider-thumb]:w-4
                                      [&::-webkit-slider-thumb]:h-4
                                      [&::-webkit-slider-thumb]:rounded-full
                                      [&::-webkit-slider-thumb]:bg-white
                                      [&::-webkit-slider-thumb]:border-2
                                      [&::-webkit-slider-thumb]:border-[#00F0FF]
                                      [&::-webkit-slider-thumb]:shadow-sm
                                      [&::-webkit-slider-thumb]:cursor-pointer"
                                    style={{
                                      background: `linear-gradient(to right, 
                                        ${topicWeight >= 80 ? '#00F0FF' : topicWeight >= 50 ? '#007AFF' : topicWeight >= 20 ? '#4DA3FF' : '#9ca3af'} 0%, 
                                        ${topicWeight >= 80 ? '#00F0FF' : topicWeight >= 50 ? '#007AFF' : topicWeight >= 20 ? '#4DA3FF' : '#9ca3af'} ${topicWeight}%, 
                                        #E5E5E7 ${topicWeight}%, 
                                        #E5E5E7 100%)`
                                    }}
                                  />
                                  
                                  <span className={`text-xs font-mono min-w-[35px] text-right ${topicSignal.color}`}>
                                    {topicWeight}%
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                );
              })}

              {/* Wildcard info */}
              <div className="p-3 rounded-xl bg-[#00F0FF]/10 border border-[#00F0FF]/20">
                <p className="text-xs text-center text-muted-foreground">
                  <span className="text-[#00F0FF] font-medium">Wildcard</span> : Un sujet à 0% peut surgir pour casser la bulle
                </p>
              </div>
            </div>
          </div>

          {/* Footer - Fixed Save Button */}
          <div className="shrink-0 px-4 py-3 bg-[hsl(var(--background))] dark:bg-[#1A1A1A] border-t border-[#E5E5E7] dark:border-[#333]">
            <div className="max-w-lg mx-auto">
              <motion.button
                onClick={saveWeights}
                disabled={saving}
                className="w-full py-3 rounded-xl bg-charcoal dark:bg-cream text-cream dark:text-charcoal font-display font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
                whileTap={{ scale: 0.98 }}
              >
                {saving ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Sauvegarde...
                  </span>
                ) : (
                  "Sauvegarder"
                )}
              </motion.button>
            </div>
          </div>
        </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body
  );
}


// ============================================
// TOPIC SELECTOR MODAL (V13 - 15 Topics)
// ============================================

const TOPIC_CATEGORIES = [
  {
    id: "tech",
    name: "Tech",
    topics: [
      { id: "ia", label: "IA, Robotique & Hardware", description: "AGI, LLMs, robots et puces qui transforment la société." },
      { id: "cyber", label: "Cybersécurité", description: "Menaces, zero-days et défenses de la souveraineté numérique." },
      { id: "deep_tech", label: "Deep Tech", description: "Quantum, fusion et nouveaux matériaux de rupture." },
    ]
  },
  {
    id: "science",
    name: "Science",
    topics: [
      { id: "health", label: "Santé & Longévité", description: "Biotech, anti-âge et biohacking pour étendre la vie active." },
      { id: "space", label: "Espace", description: "Économie orbitale vers une humanité multi-planétaire." },
      { id: "energy", label: "Énergie", description: "Mix énergétique, nucléaire et innovations de stockage." },
    ]
  },
  {
    id: "economics",
    name: "Économie",
    topics: [
      { id: "crypto", label: "Crypto", description: "Protocoles blockchain et redéfinition de la valeur." },
      { id: "macro", label: "Macro-économie", description: "Banques centrales, flux de capitaux et tendances." },
      { id: "deals", label: "M&A & VC", description: "Levées de fonds, acquisitions, IPO et mouvements de capital." },
    ]
  },
  {
    id: "world",
    name: "Monde",
    topics: [
      { id: "asia", label: "Asie", description: "Tech chinoise et marchés émergents asiatiques." },
      { id: "regulation", label: "Régulation", description: "Lois, compliance et arbitrages réglementaires." },
      { id: "resources", label: "Ressources", description: "Matières premières et supply chains critiques." },
    ]
  },
  {
    id: "influence",
    name: "Influence",
    topics: [
      { id: "info", label: "Guerre de l'Information", description: "Désinformation et cyber-opérations mondiales." },
      { id: "attention", label: "Marchés de l'Attention", description: "Algorithmes et capture de l'attention humaine." },
      { id: "persuasion", label: "Stratégies de Persuasion", description: "Nudges et design cognitif pour forger l'opinion." },
    ]
  }
];

function TopicSelectorModal({ 
  isOpen, 
  onClose, 
  currentTopics 
}: { 
  isOpen: boolean; 
  onClose: () => void;
  currentTopics: Topic[];
}) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const router = useRouter();

  useEffect(() => {
    setSelectedIds(currentTopics.map(t => t.keyword));
  }, [currentTopics, isOpen]);

  const toggleTopic = async (topicId: string, topicLabel: string) => {
    const isSelected = selectedIds.includes(topicId);
    setSaving(true);

    try {
      if (isSelected) {
        const response = await fetch(`/api/interests?keyword=${encodeURIComponent(topicId)}`, {
          method: "DELETE",
        });
        if (!response.ok) throw new Error();
        setSelectedIds(prev => prev.filter(id => id !== topicId));
        toast.success(`"${topicLabel}" retiré`);
      } else {
        if (selectedIds.length >= 4) {
          toast.error("Maximum 4 thèmes");
          setSaving(false);
          return;
        }
        const response = await fetch("/api/interests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            keyword: topicId, 
            display_name: topicLabel 
          }),
        });
        if (!response.ok) throw new Error();
        setSelectedIds(prev => [...prev, topicId]);
        toast.success(`"${topicLabel}" ajouté`);
      }
      router.refresh();
    } catch {
      toast.error("Erreur");
    } finally {
      setSaving(false);
    }
  };

  // Flatten all topics for floating display
  const allTopics = TOPIC_CATEGORIES.flatMap(cat => 
    cat.topics.map(t => ({ ...t, category: cat.name }))
  );

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          {/* Blurred background matching theme */}
          <motion.div
            className="absolute inset-0 bg-[hsl(var(--background))]/90 dark:bg-[#1A1A1A]/90 backdrop-blur-xl"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Close button - LEFT */}
          <motion.button
            onClick={onClose}
            className="absolute top-6 left-6 z-10 w-12 h-12 rounded-full bg-card/80 backdrop-blur-sm border border-border/50 flex items-center justify-center hover:bg-card transition-colors shadow-lg"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <X className="w-5 h-5" />
          </motion.button>

          {/* Counter - RIGHT */}
          <motion.div
            className="absolute top-6 right-6 z-10 px-4 py-2 rounded-full bg-card/80 backdrop-blur-sm border border-border/50 shadow-lg"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            <span className="font-display text-sm font-medium">
              {selectedIds.length}/4 thèmes
            </span>
          </motion.div>

          {/* Floating topics - Cloud style */}
          <div className="relative z-10 w-full max-w-5xl px-4 sm:px-6 overflow-y-auto max-h-[70vh] py-8">
            {/* Desktop: True cloud layout with varied positions */}
            <div className="hidden sm:block relative min-h-[400px]">
              {allTopics.map((topic, idx) => {
                const isSelected = selectedIds.includes(topic.id);
                const isDisabled = !isSelected && selectedIds.length >= 4;
                
                // Cloud positioning - organic scattered layout
                const positions = [
                  { top: '5%', left: '15%' },    // IA
                  { top: '8%', left: '55%' },    // Quantum
                  { top: '2%', left: '78%' },    // Robotique
                  { top: '28%', left: '5%' },    // Asie
                  { top: '25%', left: '38%' },   // Régulation
                  { top: '22%', left: '70%' },   // Ressources
                  { top: '48%', left: '12%' },   // Crypto
                  { top: '45%', left: '45%' },   // Macro
                  { top: '42%', left: '75%' },   // Bourse
                  { top: '65%', left: '3%' },    // Énergie
                  { top: '68%', left: '35%' },   // Santé
                  { top: '62%', left: '65%' },   // Espace
                  { top: '85%', left: '18%' },   // Cinéma
                  { top: '82%', left: '48%' },   // Gaming
                  { top: '88%', left: '75%' },   // Lifestyle
                ];
                const pos = positions[idx] || { top: '50%', left: '50%' };
                
                return (
                  <motion.button
                    key={topic.id}
                    onClick={() => toggleTopic(topic.id, topic.label)}
                    disabled={saving || isDisabled}
                    style={{ top: pos.top, left: pos.left }}
                    className={`absolute max-w-[200px] px-4 py-3 rounded-2xl backdrop-blur-sm border transition-all ${
                      isSelected
                        ? "bg-[#00F0FF] border-[#00F0FF] text-white shadow-lg shadow-[#00F0FF]/30"
                        : isDisabled
                          ? "bg-card/30 border-border/30 text-muted-foreground/50 cursor-not-allowed"
                          : "bg-card/60 border-border/50 text-foreground hover:bg-card/80 hover:border-border hover:shadow-md"
                    }`}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ delay: idx * 0.04, type: "spring", stiffness: 200 }}
                    whileHover={!isDisabled ? { scale: 1.05, zIndex: 10 } : {}}
                    whileTap={!isDisabled ? { scale: 0.98 } : {}}
                  >
                    <div className="flex flex-col items-start text-left">
                      <span className={`font-display font-semibold text-sm ${isSelected ? "text-white" : ""}`}>
                        {isSelected && <span className="mr-1">✓</span>}
                        {topic.label}
                      </span>
                      <span className={`text-[11px] mt-1 leading-tight line-clamp-2 ${
                        isSelected ? "text-white/80" : "text-muted-foreground"
                      }`}>
                        {topic.description}
                      </span>
                    </div>
                  </motion.button>
                );
              })}
            </div>

            {/* Mobile: Compact cloud grid */}
            <div className="sm:hidden grid grid-cols-2 gap-2">
              {allTopics.map((topic, idx) => {
                const isSelected = selectedIds.includes(topic.id);
                const isDisabled = !isSelected && selectedIds.length >= 4;
                
                return (
                  <motion.button
                    key={topic.id}
                    onClick={() => toggleTopic(topic.id, topic.label)}
                    disabled={saving || isDisabled}
                    className={`px-3 py-2.5 rounded-xl backdrop-blur-sm border transition-all text-left ${
                      isSelected
                        ? "bg-[#00F0FF] border-[#00F0FF] text-white shadow-md shadow-[#00F0FF]/20"
                        : isDisabled
                          ? "bg-card/30 border-border/30 text-muted-foreground/50"
                          : "bg-card/60 border-border/50 text-foreground active:bg-card/80"
                    }`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.03 }}
                    whileTap={!isDisabled ? { scale: 0.97 } : {}}
                  >
                    <span className={`font-display font-semibold text-sm block ${isSelected ? "text-white" : ""}`}>
                      {isSelected && <span className="mr-1">✓</span>}
                      {topic.label}
                    </span>
                    <span className={`text-[10px] mt-0.5 leading-tight line-clamp-2 block ${
                      isSelected ? "text-white/70" : "text-muted-foreground"
                    }`}>
                      {topic.description}
                    </span>
                  </motion.button>
                );
              })}
            </div>

            {/* Done button at bottom */}
            <motion.div
              className="flex justify-center mt-6 sm:mt-8 sticky bottom-0 pb-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
            >
              <button
                onClick={onClose}
                className="px-8 py-3 rounded-full bg-charcoal dark:bg-cream text-cream dark:text-charcoal font-display font-medium hover:opacity-90 transition-opacity shadow-lg"
              >
                Terminé
              </button>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
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
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

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
            className="fixed bottom-32 left-1/2 z-40 w-[90%] max-w-[560px]"
            style={{ x: "-50%" }}
            initial={{ y: "100%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
          >
            <div className="rounded-3xl bg-card/90 backdrop-blur-2xl border border-border/30 p-4 max-h-[50vh] overflow-y-auto scrollbar-hide shadow-2xl">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display text-lg font-semibold">Sources</h3>
                <button onClick={() => setShowSources(false)} className="p-2 rounded-full hover:bg-secondary transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>

              {sources.length > 0 ? (
                <div className="space-y-2">
                  {sources.map((source, idx) => {
                    const colors = getSourceColor(idx);
                    const favicon = getFaviconUrl(source.url);

                    return (
                      <motion.a
                        key={idx}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`flex items-center gap-3 p-3 rounded-xl ${colors.bg} hover:opacity-90 transition-all group shadow-sm`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.05 }}
                      >
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: colors.iconBg }}>
                          {favicon ? <img src={favicon} alt="" className="w-4 h-4" /> : <div className="w-3 h-3 rounded-full bg-current opacity-40" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className={`text-sm font-medium truncate ${colors.text}`}>{source.title}</p>
                          <p className={`text-xs font-mono ${colors.domain}`}>{source.domain}</p>
                        </div>
                        <ExternalLink className={`w-4 h-4 ${colors.text} opacity-0 group-hover:opacity-60 flex-shrink-0`} />
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
        {/* Glow effect under player */}
        <div 
          className="absolute -inset-4 rounded-[32px] pointer-events-none"
          style={{
            background: isDark 
              ? 'radial-gradient(ellipse at center bottom, rgba(0, 240, 255, 0.15) 0%, transparent 70%)'
              : 'radial-gradient(ellipse at center bottom, rgba(0, 122, 255, 0.1) 0%, transparent 70%)',
            filter: 'blur(20px)',
          }}
        />

        <div className="relative w-[90vw] max-w-[620px] px-5 py-4 rounded-2xl bg-card/80 backdrop-blur-2xl border border-border/30 shadow-2xl">
          <div className="flex items-center gap-4">
            {/* Skip back */}
            <motion.button 
              onClick={() => skip(-15)} 
              className="p-2 text-muted-foreground hover:text-foreground transition-colors" 
              whileTap={{ scale: 0.9 }}
            >
              <SkipBack className="w-4 h-4" />
            </motion.button>

            {/* Play button - Premium cyan with glow */}
            <motion.button
              onClick={togglePlay}
              className="relative w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: isDark 
                  ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 100%)'
                  : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 100%)',
                boxShadow: isDark 
                  ? '0 0 20px rgba(0, 240, 255, 0.4)'
                  : '0 0 20px rgba(0, 122, 255, 0.3)',
              }}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.95 }}
            >
              {/* Pulse animation when playing */}
              {isPlaying && (
                <motion.div
                  className="absolute inset-0 rounded-full"
                  style={{
                    background: isDark 
                      ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 100%)'
                      : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 100%)',
                  }}
                  animate={{ scale: [1, 1.2, 1], opacity: [0.5, 0, 0.5] }}
                  transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                />
              )}
              <span className="relative text-white">
                {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </span>
            </motion.button>

            {/* Skip forward */}
            <motion.button 
              onClick={() => skip(15)} 
              className="p-2 text-muted-foreground hover:text-foreground transition-colors" 
              whileTap={{ scale: 0.9 }}
            >
              <SkipForward className="w-4 h-4" />
            </motion.button>

            {/* Title and progress */}
            <div className="flex-1 min-w-0">
              <p 
                className="font-display text-sm font-semibold truncate"
                style={{ color: isDark ? '#00F0FF' : '#007AFF' }}
              >
                {episode.title}
              </p>
              <div className="mt-2 flex items-center gap-3">
                {/* Progress bar with shimmer */}
                <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden relative">
                  <motion.div 
                    className="h-full rounded-full relative overflow-hidden"
                    style={{ 
                      width: `${progress}%`,
                      background: isDark 
                        ? 'linear-gradient(90deg, #00F0FF 0%, #00D4AA 100%)'
                        : 'linear-gradient(90deg, #007AFF 0%, #00C6FF 100%)',
                    }}
                  >
                    {/* Shimmer effect */}
                    <motion.div
                      className="absolute inset-0"
                      style={{
                        background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.3) 50%, transparent 100%)',
                      }}
                      animate={{ x: ['-100%', '100%'] }}
                      transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                    />
                  </motion.div>
                </div>
                <span 
                  className="text-[10px] font-mono flex-shrink-0"
                  style={{ color: isDark ? 'rgba(0, 240, 255, 0.7)' : 'rgba(0, 122, 255, 0.7)' }}
                >
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              </div>
            </div>

            {/* Playback rate */}
            <motion.button
              onClick={cyclePlaybackRate}
              className="px-2.5 py-1.5 rounded-lg text-xs font-mono text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              whileTap={{ scale: 0.95 }}
            >
              {playbackRate}x
            </motion.button>

            {/* Sources button */}
            <motion.button
              onClick={() => setShowSources(!showSources)}
              className={`p-2.5 rounded-xl flex-shrink-0 transition-all ${
                showSources 
                  ? "bg-primary/20 text-primary" 
                  : "hover:bg-muted/50 text-muted-foreground hover:text-foreground"
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
  const [isHovered, setIsHovered] = useState(false);
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

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

  return (
    <motion.button
      onClick={handleGenerate}
      disabled={loading}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className="relative w-full max-w-xs mx-auto block overflow-hidden rounded-2xl text-sm font-display font-semibold"
      whileHover={{ scale: 1.02, y: -2 }}
      whileTap={{ scale: 0.98 }}
    >
      {/* Background gradient */}
      <motion.div
        className="absolute inset-0"
        style={{
          background: isDark
            ? 'linear-gradient(135deg, #111 0%, #1a1a1a 50%, #111 100%)'
            : 'linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 50%, #1a1a1a 100%)',
        }}
      />

      {/* Animated shimmer effect */}
      <motion.div
        className="absolute inset-0 opacity-0"
        style={{
          background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.1) 50%, transparent 100%)',
        }}
        animate={isHovered ? {
          opacity: 1,
          x: ['-100%', '100%'],
        } : { opacity: 0, x: '-100%' }}
        transition={{
          x: { duration: 0.8, ease: "easeInOut" },
          opacity: { duration: 0.2 }
        }}
      />

      {/* Border glow on hover */}
      <motion.div
        className="absolute inset-0 rounded-2xl"
        style={{
          boxShadow: isDark 
            ? '0 0 0 1px rgba(0, 240, 255, 0.3), 0 0 30px rgba(0, 240, 255, 0.2)'
            : '0 0 0 1px rgba(0, 122, 255, 0.3), 0 0 30px rgba(0, 122, 255, 0.15)',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: isHovered ? 1 : 0 }}
        transition={{ duration: 0.3 }}
      />

      {/* Content */}
      <div className="relative px-8 py-4 text-white">
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Generating...
          </span>
        ) : (
          <span className="flex items-center justify-center gap-3">
            <span>Generate Keernel</span>
            {pendingCount > 0 && (
              <span 
                className="px-2.5 py-1 rounded-full text-xs font-mono"
                style={{
                  background: isDark 
                    ? 'rgba(0, 240, 255, 0.2)' 
                    : 'rgba(255, 255, 255, 0.15)',
                  color: isDark ? '#00F0FF' : 'white',
                }}
              >
                {pendingCount} segments
              </span>
            )}
          </span>
        )}
      </div>
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
  pendingCount,
  signalWeights = {}
}: KernelDashboardProps) {
  const hasTopics = topics.length > 0 || Object.keys(signalWeights).length > 0;
  const { resolvedTheme } = useTheme();
  const [currentEpisode, setCurrentEpisode] = useState<Episode | null>(episode);
  const isDark = resolvedTheme === "dark";

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
    <div className="min-h-screen relative overflow-hidden">
      {/* Aurora animated background */}
      <AuroraBackground />
      
      <AvatarMenu user={user} />

      {/* History Menu - Top Left */}
      <div className="fixed top-6 left-6 z-50">
        <HistoryMenu onSelectEpisode={handleSelectHistoryEpisode} />
      </div>

      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6 py-20">
        {/* Animated Pulsing Logo */}
        <motion.div
          className="mb-8"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <PulsingLogo />
        </motion.div>

        {/* Title with gradient name */}
        <motion.div
          className="text-center mb-12"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <h1 className="title-keernel text-4xl md:text-5xl mb-3">
            <span>Bonjour</span>
            {user.firstName && (
              <>
                <span>, </span>
                <span 
                  className="bg-clip-text text-transparent"
                  style={{
                    backgroundImage: isDark 
                      ? 'linear-gradient(135deg, #00F0FF 0%, #00D4AA 50%, #7B00FF 100%)'
                      : 'linear-gradient(135deg, #007AFF 0%, #00C6FF 50%, #0066FF 100%)',
                  }}
                >
                  {user.firstName}
                </span>
              </>
            )}
          </h1>
          <motion.p 
            className="text-muted-foreground text-sm tracking-wide font-mono"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.5 }}
          >
            Votre podcast quotidien vous attend
          </motion.p>
        </motion.div>

        {/* Magic Bar with animated border */}
        <motion.div
          className="w-full mb-10"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <MagicBar />
        </motion.div>

        {/* Premium Radar Chart */}
        <motion.div
          className="w-full mb-12 flex justify-center"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          <SignalRadarWidget weights={signalWeights} />
        </motion.div>

        {/* Generate Button with shimmer */}
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
