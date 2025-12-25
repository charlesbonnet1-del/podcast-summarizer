"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Search, BookOpen, Loader2, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { DigestCard } from "@/components/dashboard/digest-card";

interface Digest {
  id: string;
  episode_id: string;
  source_url: string;
  title: string;
  author?: string | null;
  published_date?: string | null;
  summary?: string | null;
  key_insights?: string[] | null;
  historical_context?: string | null;
  created_at: string;
  episodes?: {
    title: string;
    created_at: string;
  };
}

export default function LibraryPage() {
  const [digests, setDigests] = useState<Digest[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Fetch digests
  useEffect(() => {
    async function fetchDigests() {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (debouncedSearch) params.set("search", debouncedSearch);
        
        const res = await fetch(`/api/digests?${params}`);
        const data = await res.json();
        
        if (data.digests) {
          setDigests(data.digests);
        }
      } catch (error) {
        console.error("Failed to fetch digests:", error);
      } finally {
        setLoading(false);
      }
    }

    fetchDigests();
  }, [debouncedSearch]);

  return (
    <div className="min-h-screen bg-[#FAF9F7] dark:bg-[#1A1A1A]">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-[#FAF9F7]/80 dark:bg-[#1A1A1A]/80 backdrop-blur-lg border-b border-black/5 dark:border-white/5">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center gap-4 mb-4">
            <Link 
              href="/dashboard"
              className="p-2 rounded-xl hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#E8DFD0] dark:bg-[#333] flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-[#6B5B4F] dark:text-[#A0A0A0]" />
              </div>
              <div>
                <h1 className="text-xl font-medium text-[#2D2D2D] dark:text-white">
                  Bibliothèque
                </h1>
                <p className="text-sm text-[#6B6B6B] dark:text-[#888]">
                  {digests.length} article{digests.length > 1 ? "s" : ""} analysé{digests.length > 1 ? "s" : ""}
                </p>
              </div>
            </div>
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8B8B8B]" />
            <input
              type="text"
              placeholder="Rechercher un article..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-3 rounded-xl bg-white dark:bg-[#2D2D2D] border border-black/5 dark:border-white/5 text-[#2D2D2D] dark:text-white placeholder-[#8B8B8B] focus:outline-none focus:ring-2 focus:ring-[#C5B358]/30"
            />
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 animate-spin text-[#8B8B8B]" />
          </div>
        ) : digests.length === 0 ? (
          <motion.div
            className="text-center py-20"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="w-16 h-16 rounded-2xl bg-[#E8DFD0] dark:bg-[#333] flex items-center justify-center mx-auto mb-4">
              <BookOpen className="w-8 h-8 text-[#6B5B4F] dark:text-[#A0A0A0]" />
            </div>
            <h2 className="text-lg font-medium text-[#2D2D2D] dark:text-white mb-2">
              {search ? "Aucun résultat" : "Bibliothèque vide"}
            </h2>
            <p className="text-sm text-[#6B6B6B] dark:text-[#888]">
              {search 
                ? "Essayez avec d'autres mots-clés" 
                : "Les digests de vos épisodes apparaîtront ici"
              }
            </p>
          </motion.div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {digests.map((digest, index) => (
              <DigestCard key={digest.id} digest={digest} index={index} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
