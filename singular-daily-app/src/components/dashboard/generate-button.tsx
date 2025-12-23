"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Sparkles, CheckCircle, Plus } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface GenerateButtonProps {
  pendingCount: number;
  hasTopics?: boolean;
}

export function GenerateButton({ pendingCount, hasTopics = false }: GenerateButtonProps) {
  const [generating, setGenerating] = useState(false);
  const [success, setSuccess] = useState(false);
  const router = useRouter();

  const handleGenerate = async () => {
    if (pendingCount === 0) {
      toast.error("No content to process. Add topics first!");
      return;
    }

    setGenerating(true);
    setSuccess(false);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
      });

      const data = await res.json();

      if (res.ok) {
        setSuccess(true);
        toast.success("Your Keernel is brewing! ☕");
        
        setTimeout(() => {
          setSuccess(false);
          router.refresh();
        }, 3000);
      } else {
        toast.error(data.error || "Failed to start generation");
      }
    } catch {
      toast.error("Failed to connect to server");
    } finally {
      setGenerating(false);
    }
  };

  // No topics and no pending content
  if (!hasTopics && pendingCount === 0) {
    return (
      <div className="matte-card px-6 py-4 text-center">
        <div className="flex items-center justify-center gap-2 text-muted-foreground font-mono">
          <Plus className="w-4 h-4" />
          <span className="text-sm">Add topics above to get started</span>
        </div>
      </div>
    );
  }

  // Has topics but no pending content yet
  if (pendingCount === 0) {
    return (
      <div className="matte-card px-6 py-4 text-center">
        <div className="flex items-center justify-center gap-2 text-muted-foreground font-mono">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
          >
            <Sparkles className="w-4 h-4" />
          </motion.div>
          <span className="text-sm">Waiting for news to arrive...</span>
        </div>
      </div>
    );
  }

  // Ready to generate - btn-generate: bg charcoal, text brass, halo charcoal
  return (
    <motion.button
      onClick={handleGenerate}
      disabled={generating}
      className="btn-generate w-full py-4 px-6 text-base disabled:opacity-70"
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
    >
      {generating ? (
        <span className="flex items-center justify-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          Brewing your Keernel...
        </span>
      ) : success ? (
        <span className="flex items-center justify-center gap-2">
          <CheckCircle className="w-5 h-5" />
          Queued! Check back soon
        </span>
      ) : (
        <span className="flex items-center justify-center gap-2">
          <Sparkles className="w-5 h-5" />
          Generate Keernel
          <span className="ml-1 px-2 py-0.5 rounded-full bg-brass/20 text-xs">
            {pendingCount}
          </span>
        </span>
      )}
    </motion.button>
  );
}
