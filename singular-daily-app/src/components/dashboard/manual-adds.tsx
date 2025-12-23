"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
    <motion.div 
      className="mt-6"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <LinkIcon className="w-3.5 h-3.5 text-[#C5B358]" />
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Added for next Keernel
        </span>
      </div>

      {/* List */}
      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {items.map((item) => (
            <motion.div
              key={item.id}
              layout
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="group matte-card flex items-center justify-between gap-3 px-4 py-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {item.title || extractDomain(item.url)}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {extractDomain(item.url)}
                </p>
              </div>
              <motion.button
                onClick={() => handleRemove(item.id)}
                disabled={removingId === item.id}
                className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
              >
                <X className="w-4 h-4" />
              </motion.button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Hint */}
      <p className="mt-3 text-xs text-muted-foreground/60 text-center">
        These links will be included in your next podcast
      </p>
    </motion.div>
  );
}
