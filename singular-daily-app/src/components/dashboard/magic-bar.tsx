"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link2, Loader2 } from "lucide-react";
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
      {/* Animated glow on focus - Brass glow */}
      <AnimatePresence>
        {isFocused && (
          <motion.div
            className="absolute -inset-2 rounded-full"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            style={{
              background: "radial-gradient(circle, rgba(197, 179, 88, 0.2), transparent)",
              filter: "blur(15px)",
            }}
          />
        )}
      </AnimatePresence>

      {/* Main capsule */}
      <motion.div
        className="magic-bar relative px-6 py-4"
        animate={{
          scale: isFocused ? 1.01 : 1,
        }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
      >
        <div className="flex items-center gap-4">
          {/* Input - LEFT ALIGNED cursor, Roboto Mono */}
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder="Paste a link or add a topic..."
            className="flex-1 bg-transparent text-base text-foreground placeholder:text-muted-foreground/60 focus:outline-none text-left font-mono"
            disabled={loading}
          />

          {/* Link icon at end */}
          <motion.button
            onClick={handleSubmit}
            disabled={loading || !input.trim()}
            className="flex items-center justify-center w-9 h-9 rounded-full text-muted-foreground hover:text-brass disabled:opacity-30 transition-colors"
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Link2 className="w-4 h-4" />
            )}
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
