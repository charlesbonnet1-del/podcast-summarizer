"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { createClient } from "@/lib/supabase/client";
import { Link2, Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

export function MagicBar() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const isUrl = (text: string) => {
    try {
      new URL(text);
      return true;
    } catch {
      return text.startsWith("http://") || text.startsWith("https://") || text.includes(".");
    }
  };

  const handleSubmit = async () => {
    const value = input.trim();
    if (!value) return;

    setLoading(true);

    try {
      if (isUrl(value)) {
        let url = value;
        if (!url.startsWith("http")) {
          url = "https://" + url;
        }

        const response = await fetch("/api/queue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "Failed to add URL");
        }

        toast.success("Link added to your next Keernel");
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="relative">
      {/* Animated border glow on focus - Light mode only */}
      <AnimatePresence>
        {isFocused && (
          <motion.div
            className="absolute -inset-1 rounded-3xl dark:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              background: "linear-gradient(135deg, rgba(0, 245, 255, 0.3), rgba(204, 255, 0, 0.3))",
              filter: "blur(8px)",
            }}
          />
        )}
      </AnimatePresence>

      {/* Main container */}
      <motion.div
        className="magic-input-container relative px-6 py-5"
        animate={{
          scale: isFocused ? 1.01 : 1,
        }}
        transition={{ duration: 0.2 }}
      >
        <div className="flex items-center gap-4">
          {/* Input */}
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder="Paste a link or add a topic..."
            className="flex-1 bg-transparent text-lg text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
            disabled={loading}
          />

          {/* Action button */}
          <motion.button
            onClick={handleSubmit}
            disabled={loading || !input.trim()}
            className="flex items-center justify-center w-10 h-10 rounded-xl bg-secondary/50 dark:bg-white/5 text-muted-foreground hover:text-foreground hover:bg-secondary dark:hover:bg-white/10 disabled:opacity-30 transition-colors"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : input.trim() && isUrl(input.trim()) ? (
              <Link2 className="w-5 h-5" />
            ) : (
              <Sparkles className="w-5 h-5" />
            )}
          </motion.button>
        </div>

        {/* Floating particles on focus - Light mode only */}
        <AnimatePresence>
          {isFocused && (
            <>
              {[...Array(6)].map((_, i) => (
                <motion.div
                  key={i}
                  className="absolute w-1.5 h-1.5 rounded-full dark:hidden"
                  style={{
                    background: i % 2 === 0 ? "#00F5FF" : "#CCFF00",
                    left: `${15 + i * 14}%`,
                    top: i % 2 === 0 ? "-4px" : "auto",
                    bottom: i % 2 === 0 ? "auto" : "-4px",
                  }}
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{
                    opacity: [0, 0.8, 0],
                    scale: [0, 1, 0],
                    y: i % 2 === 0 ? [0, -10, 0] : [0, 10, 0],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                    delay: i * 0.2,
                    ease: "easeInOut",
                  }}
                />
              ))}
            </>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
