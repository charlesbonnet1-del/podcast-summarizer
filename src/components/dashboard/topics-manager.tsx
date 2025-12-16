"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Hash, Plus, X, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

interface Interest {
  id: string;
  keyword: string;
  created_at: string;
}

export function TopicsManager() {
  const [interests, setInterests] = useState<Interest[]>([]);
  const [newTopic, setNewTopic] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Fetch interests on mount
  useEffect(() => {
    fetchInterests();
  }, []);

  const fetchInterests = async () => {
    try {
      const res = await fetch("/api/interests");
      const data = await res.json();
      
      if (res.ok) {
        setInterests(data.interests || []);
      } else {
        toast.error("Failed to load topics");
      }
    } catch {
      toast.error("Failed to load topics");
    } finally {
      setLoading(false);
    }
  };

  const addTopic = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const keyword = newTopic.trim();
    if (!keyword) return;

    if (keyword.length < 2) {
      toast.error("Topic must be at least 2 characters");
      return;
    }

    setAdding(true);

    try {
      const res = await fetch("/api/interests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword }),
      });

      const data = await res.json();

      if (res.ok) {
        setInterests([data.interest, ...interests]);
        setNewTopic("");
        toast.success(`Now following "${keyword}"`);
      } else {
        toast.error(data.error || "Failed to add topic");
      }
    } catch {
      toast.error("Failed to add topic");
    } finally {
      setAdding(false);
    }
  };

  const removeTopic = async (id: string, keyword: string) => {
    setDeletingId(id);

    try {
      const res = await fetch(`/api/interests?id=${id}`, {
        method: "DELETE",
      });

      if (res.ok) {
        setInterests(interests.filter((i) => i.id !== id));
        toast.success(`Removed "${keyword}"`);
      } else {
        toast.error("Failed to remove topic");
      }
    } catch {
      toast.error("Failed to remove topic");
    } finally {
      setDeletingId(null);
    }
  };

  const suggestedTopics = [
    "Artificial Intelligence",
    "Startup",
    "Productivity",
    "Tech News",
    "Finance",
    "Science",
  ];

  const addSuggestedTopic = (topic: string) => {
    setNewTopic(topic);
  };

  return (
    <Card className="shadow-zen rounded-2xl border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-purple-500" />
          </div>
          <div>
            <CardTitle className="text-lg">My Topics</CardTitle>
            <CardDescription>
              We&apos;ll fetch daily news on these subjects
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Add topic form */}
        <form onSubmit={addTopic} className="flex gap-2">
          <div className="relative flex-1">
            <Hash className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              value={newTopic}
              onChange={(e) => setNewTopic(e.target.value)}
              placeholder="Add a topic (e.g. AI, Startup...)"
              className="pl-9 rounded-xl h-11"
              maxLength={50}
              disabled={adding}
            />
          </div>
          <Button 
            type="submit" 
            className="rounded-xl h-11 px-4"
            disabled={adding || !newTopic.trim()}
          >
            {adding ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
          </Button>
        </form>

        {/* Suggested topics (show only if user has < 3 topics) */}
        {interests.length < 3 && (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">Suggestions:</p>
            <div className="flex flex-wrap gap-2">
              {suggestedTopics
                .filter((t) => !interests.some((i) => i.keyword.toLowerCase() === t.toLowerCase()))
                .slice(0, 4)
                .map((topic) => (
                  <button
                    key={topic}
                    type="button"
                    onClick={() => addSuggestedTopic(topic)}
                    className="text-xs px-3 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 transition-colors"
                  >
                    + {topic}
                  </button>
                ))}
            </div>
          </div>
        )}

        {/* Topics list */}
        {loading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : interests.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-sm text-muted-foreground">
              No topics yet. Add topics above and we&apos;ll fetch news for you daily!
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {interests.map((interest) => (
              <Badge
                key={interest.id}
                variant="secondary"
                className="rounded-lg px-3 py-1.5 text-sm flex items-center gap-2 hover:bg-secondary/80"
              >
                <Hash className="w-3 h-3" />
                {interest.keyword}
                <button
                  onClick={() => removeTopic(interest.id, interest.keyword)}
                  disabled={deletingId === interest.id}
                  className="ml-1 hover:text-destructive transition-colors"
                >
                  {deletingId === interest.id ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <X className="w-3 h-3" />
                  )}
                </button>
              </Badge>
            ))}
          </div>
        )}

        {/* Info */}
        {interests.length > 0 && (
          <p className="text-xs text-muted-foreground pt-2">
            📰 News on these topics will be added to your queue every morning.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
