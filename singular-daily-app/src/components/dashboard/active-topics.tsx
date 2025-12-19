"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
    <motion.div 
      className="flex flex-wrap gap-2"
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <AnimatePresence mode="popLayout">
        {topics.map((topic) => (
          <motion.span
            key={topic.id}
            layout
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="tag-pill group inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-all"
          >
            <span className="text-[#00F5FF] dark:text-[#00F5FF]/70">#</span>
            <span>{topic.keyword}</span>
            <motion.button
              onClick={() => handleRemove(topic)}
              disabled={removingId === topic.id}
              className="opacity-0 group-hover:opacity-100 ml-0.5 -mr-1 p-0.5 rounded-full hover:bg-black/5 dark:hover:bg-white/10 transition-all"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <X className="w-3 h-3" />
            </motion.button>
          </motion.span>
        ))}
      </AnimatePresence>
    </motion.div>
  );
}
