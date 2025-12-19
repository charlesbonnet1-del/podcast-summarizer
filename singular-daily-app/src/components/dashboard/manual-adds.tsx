"use client";

import { useState } from "react";
import { X, Link as LinkIcon } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface ManualItem {
  id: string;
  url: string;
  title: string | null;
}

interface ManualAddsProps {
  items: ManualItem[];
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace("www.", "");
  } catch {
    return url;
  }
}

export function ManualAdds({ items }: ManualAddsProps) {
  const [removingId, setRemovingId] = useState<string | null>(null);
  const router = useRouter();

  // Hidden if no manual items
  if (!items || items.length === 0) {
    return null;
  }

  const handleRemove = async (id: string) => {
    setRemovingId(id);

    try {
      const response = await fetch(`/api/queue?id=${id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to remove");
      }

      toast.success("Link removed");
      router.refresh();
    } catch (error) {
      toast.error("Failed to remove link");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="mt-6 animate-in fade-in slide-in-from-top-2 duration-300">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <LinkIcon className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Added for next Keernel
        </span>
      </div>

      {/* List */}
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="group flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-secondary/30 border border-border/30"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">
                {item.title || extractDomain(item.url)}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {extractDomain(item.url)}
              </p>
            </div>
            <button
              onClick={() => handleRemove(item.id)}
              disabled={removingId === item.id}
              className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>

      {/* Subtle hint */}
      <p className="mt-3 text-xs text-muted-foreground/60 text-center">
        These links will be included in your next podcast
      </p>
    </div>
  );
}
