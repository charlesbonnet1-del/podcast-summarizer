"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface Topic {
  id: string;
  keyword: string;
}

interface ActiveTopicsProps {
  topics: Topic[];
}

export function ActiveTopics({ topics }: ActiveTopicsProps) {
  const [removingId, setRemovingId] = useState<string | null>(null);
  const router = useRouter();

  if (!topics || topics.length === 0) {
    return null;
  }

  const handleRemove = async (topic: Topic) => {
    setRemovingId(topic.id);

    try {
      const response = await fetch(`/api/interests?keyword=${encodeURIComponent(topic.keyword)}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to remove topic");
      }

      toast.success(`"${topic.keyword}" removed`);
      router.refresh();
    } catch (error) {
      toast.error("Failed to remove topic");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {topics.map((topic) => (
        <span
          key={topic.id}
          className="group inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-secondary/50 text-muted-foreground hover:bg-secondary transition-colors"
        >
          <span className="opacity-50">#</span>
          {topic.keyword}
          <button
            onClick={() => handleRemove(topic)}
            disabled={removingId === topic.id}
            className="opacity-0 group-hover:opacity-100 hover:text-foreground transition-opacity ml-0.5 -mr-1"
          >
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
    </div>
  );
}
