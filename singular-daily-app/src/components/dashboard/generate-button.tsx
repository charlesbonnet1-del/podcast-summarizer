"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Loader2, Sparkles, CheckCircle } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface GenerateButtonProps {
  pendingCount: number;
}

export function GenerateButton({ pendingCount }: GenerateButtonProps) {
  const [generating, setGenerating] = useState(false);
  const [success, setSuccess] = useState(false);
  const router = useRouter();

  const handleGenerate = async () => {
    if (pendingCount === 0) {
      toast.error("No content to process");
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

  return (
    <Button
      onClick={handleGenerate}
      disabled={generating || pendingCount === 0}
      variant="outline"
      className="w-full h-12 rounded-2xl text-sm font-medium border-dashed border-2 hover:border-solid hover:bg-secondary/50 transition-all"
    >
      {generating ? (
        <>
          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          Brewing your Keernel...
        </>
      ) : success ? (
        <>
          <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
          Queued! Check back soon
        </>
      ) : (
        <>
          <Sparkles className="w-4 h-4 mr-2" />
          Generate Keernel
          <span className="ml-2 text-xs text-muted-foreground">
            ({pendingCount} {pendingCount === 1 ? "item" : "items"})
          </span>
        </>
      )}
    </Button>
  );
}
