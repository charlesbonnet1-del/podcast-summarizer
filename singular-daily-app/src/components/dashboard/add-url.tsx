"use client";

import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Link2, Plus, Loader2, Youtube, FileText, Podcast } from "lucide-react";
import { toast } from "sonner";

interface AddUrlProps {
  onUrlAdded?: () => void;
}

export function AddUrl({ onUrlAdded }: AddUrlProps) {
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const trimmedUrl = url.trim();
    if (!trimmedUrl) return;

    // Basic URL validation
    if (!trimmedUrl.startsWith("http://") && !trimmedUrl.startsWith("https://")) {
      toast.error("Please enter a valid URL starting with http:// or https://");
      return;
    }

    setAdding(true);

    try {
      const res = await fetch("/api/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmedUrl }),
      });

      const data = await res.json();

      if (res.ok) {
        const icon = data.source_type === "youtube" ? "🎬" : 
                     data.source_type === "podcast" ? "🎙️" : "📰";
        toast.success(`${icon} Added to your queue!`);
        setUrl("");
        onUrlAdded?.();
      } else {
        toast.error(data.error || "Failed to add URL");
      }
    } catch {
      toast.error("Failed to connect to server");
    } finally {
      setAdding(false);
    }
  };

  const getPlaceholder = () => {
    const examples = [
      "Paste a YouTube link...",
      "Paste an article URL...",
      "Paste a podcast link...",
    ];
    return examples[Math.floor(Date.now() / 5000) % examples.length];
  };

  return (
    <Card className="shadow-zen rounded-2xl border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
            <Link2 className="w-5 h-5 text-blue-500" />
          </div>
          <div>
            <CardTitle className="text-lg">Add Content</CardTitle>
            <CardDescription>
              Paste any URL to add to your podcast
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={getPlaceholder()}
              className="rounded-xl h-11 pr-10"
              disabled={adding}
              type="url"
            />
            {url && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                {url.includes("youtube") || url.includes("youtu.be") ? (
                  <Youtube className="w-4 h-4 text-red-500" />
                ) : url.includes("spotify") ? (
                  <Podcast className="w-4 h-4 text-green-500" />
                ) : (
                  <FileText className="w-4 h-4 text-blue-500" />
                )}
              </div>
            )}
          </div>
          <Button 
            type="submit" 
            className="rounded-xl h-11 px-4"
            disabled={adding || !url.trim()}
          >
            {adding ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
          </Button>
        </form>
        
        <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Youtube className="w-3 h-3 text-red-500" /> YouTube
          </span>
          <span className="flex items-center gap-1">
            <FileText className="w-3 h-3 text-blue-500" /> Articles
          </span>
          <span className="flex items-center gap-1">
            <Podcast className="w-3 h-3 text-green-500" /> Podcasts
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
