"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { createClient } from "@/lib/supabase/client";
import { Zap, Compass, Check } from "lucide-react";
import { toast } from "sonner";

interface FormatToggleProps {
  initialFormat?: string;
  onFormatChange?: (format: string) => void;
}

export function FormatToggle({ initialFormat = "deepdive", onFormatChange }: FormatToggleProps) {
  const [format, setFormat] = useState<string>(initialFormat);
  const [saving, setSaving] = useState(false);
  const supabase = createClient();

  useEffect(() => {
    // Load user's preferred format
    const loadFormat = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      const { data } = await supabase
        .from("users")
        .select("preferred_format")
        .eq("id", user.id)
        .single();

      if (data?.preferred_format) {
        setFormat(data.preferred_format);
      }
    };

    loadFormat();
  }, [supabase]);

  const handleFormatChange = async (newFormat: string) => {
    setFormat(newFormat);
    onFormatChange?.(newFormat);
    setSaving(true);

    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error("Not authenticated");

      const { error } = await supabase
        .from("users")
        .update({ preferred_format: newFormat })
        .eq("id", user.id);

      if (error) throw error;

      toast.success(`Format ${newFormat === "flash" ? "Express ⚡" : "Deep Dive 🧭"} sélectionné`);
    } catch (error) {
      console.error("Failed to save format:", error);
      toast.error("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* Express Option (formerly Flash) */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => handleFormatChange("flash")}
          disabled={saving}
          className={`relative p-6 rounded-2xl border-2 transition-all duration-300 text-left ${
            format === "flash"
              ? "border-[#C5B358] bg-[#C5B358]/10 shadow-lg shadow-[#C5B358]/20"
              : "border-border hover:border-muted-foreground/50 bg-card"
          }`}
        >
          {format === "flash" && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="absolute top-3 right-3"
            >
              <Check className="w-5 h-5 text-[#C5B358]" />
            </motion.div>
          )}
          
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-xl ${
              format === "flash" ? "bg-[#C5B358]/20" : "bg-muted"
            }`}>
              <Zap className={`w-6 h-6 ${
                format === "flash" ? "text-[#C5B358]" : "text-muted-foreground"
              }`} />
            </div>
            <div>
              <div className="font-semibold text-lg">Express</div>
              <div className="text-2xl font-bold text-[#C5B358]">~4 min</div>
            </div>
          </div>
          
          <p className="text-sm text-muted-foreground">
            L'essentiel, sans compromis
          </p>
          
          <div className="mt-4">
            <span className="px-3 py-1.5 rounded-full bg-muted text-xs font-medium">Synthèse chirurgicale</span>
          </div>
        </motion.button>

        {/* Deep Dive Option */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => handleFormatChange("deepdive")}
          disabled={saving}
          className={`relative p-6 rounded-2xl border-2 transition-all duration-300 text-left ${
            format === "deepdive" || format === "digest"
              ? "border-[#C5B358] bg-[#C5B358]/10 shadow-lg shadow-[#C5B358]/20"
              : "border-border hover:border-muted-foreground/50 bg-card"
          }`}
        >
          {(format === "deepdive" || format === "digest") && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="absolute top-3 right-3"
            >
              <Check className="w-5 h-5 text-[#C5B358]" />
            </motion.div>
          )}
          
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-xl ${
              format === "deepdive" || format === "digest" ? "bg-[#C5B358]/20" : "bg-muted"
            }`}>
              <Compass className={`w-6 h-6 ${
                format === "deepdive" || format === "digest" ? "text-[#C5B358]" : "text-muted-foreground"
              }`} />
            </div>
            <div>
              <div className="font-semibold text-lg">Deep Dive</div>
              <div className="text-2xl font-bold text-[#C5B358]">~15 min</div>
            </div>
          </div>
          
          <p className="text-sm text-muted-foreground">
            Contexte, analyse et perspectives
          </p>
          
          <div className="mt-4">
            <span className="px-3 py-1.5 rounded-full bg-muted text-xs font-medium">Exploration complète</span>
          </div>
        </motion.button>
      </div>
    </div>
  );
}
