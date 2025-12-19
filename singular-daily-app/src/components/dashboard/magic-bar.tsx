"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

export function MagicBar() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
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
        // It's a URL - add to queue
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
        // It's a topic/keyword
        const supabase = createClient();
        const { data: { user } } = await supabase.auth.getUser();

        if (!user) {
          toast.error("Please sign in");
          return;
        }

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
      <Input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Add a topic or paste a link..."
        className="h-14 pl-5 pr-14 text-base rounded-2xl bg-secondary/30 border-border/50 focus-visible:ring-primary/20"
        disabled={loading}
      />
      <Button
        size="icon"
        onClick={handleSubmit}
        disabled={loading || !input.trim()}
        className="absolute right-2 top-1/2 -translate-y-1/2 h-10 w-10 rounded-xl"
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Sparkles className="w-4 h-4" />
        )}
      </Button>
    </div>
  );
}
