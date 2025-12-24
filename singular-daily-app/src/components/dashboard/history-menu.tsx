"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Clock, 
  ChevronDown, 
  Play, 
  FileText, 
  ExternalLink,
  Calendar
} from "lucide-react";
import Link from "next/link";

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

interface HistoryMenuProps {
  onSelectEpisode?: (episode: HistoryItem) => void;
}

export function HistoryMenu({ onSelectEpisode }: HistoryMenuProps) {
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

  if (history.length === 0 && !loading && !isOpen) {
    return null;
  }

  return (
    <div className="relative">
      {/* Toggle Button */}
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 rounded-full bg-secondary/50 hover:bg-secondary transition-colors text-sm font-display"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <Clock className="w-4 h-4 text-sand" />
        <span>Cette semaine</span>
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        </motion.div>
      </motion.button>

      {/* Dropdown Menu */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              className="fixed inset-0 z-40"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
            />

            {/* Menu */}
            <motion.div
              className="absolute top-full left-0 mt-2 w-80 z-50 rounded-2xl bg-card border border-border shadow-xl overflow-hidden"
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ duration: 0.2 }}
            >
              {/* Header */}
              <div className="px-4 py-3 border-b border-border bg-secondary/30">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-brass" />
                  <span className="font-display font-medium">Dernières générations</span>
                </div>
              </div>

              {/* Content */}
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
                          {/* Date */}
                          <div className="text-xs text-muted-foreground mb-1 font-mono">
                            {item.date}
                          </div>
                          
                          {/* Title */}
                          <div className="font-display font-medium text-sm mb-2 truncate">
                            {item.title}
                          </div>
                          
                          {/* Meta */}
                          <div className="flex items-center gap-3 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Play className="w-3 h-3" />
                              {formatDuration(item.duration)}
                            </span>
                            <span>{item.sourcesCount} sources</span>
                          </div>
                          
                          {/* Actions */}
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

              {/* Footer */}
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
