"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
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
        
        // Refresh to clear manual adds
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

  // No topics and no pending content - show "Add topics" state
  if (!hasTopics && pendingCount === 0) {
    return (
      <Button
        disabled
        variant="outline"
        className="w-full h-14 rounded-2xl text-sm font-medium border-dashed border-2 opacity-50"
      >
        <Plus className="w-4 h-4 mr-2" />
        Add topics above to get started
      </Button>
    );
  }

  // Has topics but no pending content yet (waiting for fetch)
  if (pendingCount === 0) {
    return (
      <Button
        disabled
        variant="outline"
        className="w-full h-14 rounded-2xl text-sm font-medium border-dashed border-2 opacity-60"
      >
        <Sparkles className="w-4 h-4 mr-2" />
        Waiting for news to arrive...
      </Button>
    );
  }

  // Ready to generate
  return (
    <Button
      onClick={handleGenerate}
      disabled={generating}
      className="w-full h-14 rounded-2xl text-base font-medium bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-600 hover:to-purple-700 transition-all shadow-lg shadow-purple-500/20"
    >
      {generating ? (
        <>
          <Loader2 className="w-5 h-5 mr-2 animate-spin" />
          Brewing your Keernel...
        </>
      ) : success ? (
        <>
          <CheckCircle className="w-5 h-5 mr-2" />
          Queued! Check back soon
        </>
      ) : (
        <>
          <Sparkles className="w-5 h-5 mr-2" />
          Generate Keernel
          <span className="ml-2 px-2 py-0.5 rounded-full bg-white/20 text-xs">
            {pendingCount}
          </span>
        </>
      )}
    </Button>
  );
}
