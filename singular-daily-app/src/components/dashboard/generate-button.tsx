"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Mic, Loader2, Sparkles, CheckCircle } from "lucide-react";
import { toast } from "sonner";

interface GenerateButtonProps {
  pendingCount: number;
}

export function GenerateButton({ pendingCount }: GenerateButtonProps) {
  const [generating, setGenerating] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleGenerate = async () => {
    if (pendingCount === 0) {
      toast.error("No content in queue. Add topics first!");
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
        toast.success(data.message || "Podcast generation started!");
        
        // Reset success state after 3 seconds
        setTimeout(() => setSuccess(false), 3000);
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
    <Card className="shadow-zen rounded-2xl border-border bg-gradient-to-br from-purple-500/5 to-pink-500/5">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
            <Mic className="w-5 h-5 text-white" />
          </div>
          <div>
            <CardTitle className="text-lg">Generate Podcast</CardTitle>
            <CardDescription>
              {pendingCount > 0
                ? `${pendingCount} items ready to process`
                : "Add topics to get started"}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Button
          onClick={handleGenerate}
          disabled={generating || pendingCount === 0}
          className="w-full h-12 rounded-xl text-base font-medium bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 transition-all"
        >
          {generating ? (
            <>
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              Generating...
            </>
          ) : success ? (
            <>
              <CheckCircle className="w-5 h-5 mr-2" />
              Queued!
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5 mr-2" />
              Generate My Podcast
            </>
          )}
        </Button>
        
        {pendingCount === 0 && (
          <p className="text-xs text-muted-foreground text-center mt-3">
            Add topics above and wait for news to be fetched
          </p>
        )}
      </CardContent>
    </Card>
  );
}
