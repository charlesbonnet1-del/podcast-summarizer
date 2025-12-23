"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { createClient } from "@/lib/supabase/client";
import { Zap, BookOpen, Check } from "lucide-react";
import { toast } from "sonner";

interface FormatToggleProps {
  initialFormat?: string;
  onFormatChange?: (format: string) => void;
}

export function FormatToggle({ initialFormat = "digest", onFormatChange }: FormatToggleProps) {
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

      toast.success(`Format ${newFormat === "flash" ? "Flash ⚡" : "Digest 📚"} sélectionné`);
    } catch (error) {
      console.error("Failed to save format:", error);
      toast.error("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-foreground">Format du podcast</h3>
      <p className="text-sm text-muted-foreground">
        Choisissez la durée de votre briefing quotidien
      </p>
      
      <div className="grid grid-cols-2 gap-4">
        {/* Flash Option */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => handleFormatChange("flash")}
          disabled={saving}
          className={`relative p-6 rounded-2xl border-2 transition-all duration-300 text-left ${
            format === "flash"
              ? "border-[#00F5FF] bg-[#00F5FF]/10 shadow-lg shadow-[#00F5FF]/20"
              : "border-border hover:border-muted-foreground/50 bg-card"
          }`}
        >
          {format === "flash" && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="absolute top-3 right-3"
            >
              <Check className="w-5 h-5 text-[#00F5FF]" />
            </motion.div>
          )}
          
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-xl ${
              format === "flash" ? "bg-[#00F5FF]/20" : "bg-muted"
            }`}>
              <Zap className={`w-6 h-6 ${
                format === "flash" ? "text-[#00F5FF]" : "text-muted-foreground"
              }`} />
            </div>
            <div>
              <div className="font-semibold text-lg">Flash</div>
              <div className="text-2xl font-bold text-[#00F5FF]">~4 min</div>
            </div>
          </div>
          
          <p className="text-sm text-muted-foreground">
            Headlines essentielles pour les matins pressés
          </p>
          
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="px-2 py-1 rounded-full bg-muted text-xs">4 sujets</span>
            <span className="px-2 py-1 rounded-full bg-muted text-xs">100 mots/sujet</span>
          </div>
        </motion.button>

        {/* Digest Option */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => handleFormatChange("digest")}
          disabled={saving}
          className={`relative p-6 rounded-2xl border-2 transition-all duration-300 text-left ${
            format === "digest"
              ? "border-[#00F5FF] bg-[#00F5FF]/10 shadow-lg shadow-[#00F5FF]/20"
              : "border-border hover:border-muted-foreground/50 bg-card"
          }`}
        >
          {format === "digest" && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="absolute top-3 right-3"
            >
              <Check className="w-5 h-5 text-[#00F5FF]" />
            </motion.div>
          )}
          
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-xl ${
              format === "digest" ? "bg-[#00F5FF]/20" : "bg-muted"
            }`}>
              <BookOpen className={`w-6 h-6 ${
                format === "digest" ? "text-[#00F5FF]" : "text-muted-foreground"
              }`} />
            </div>
            <div>
              <div className="font-semibold text-lg">Digest</div>
              <div className="text-2xl font-bold text-[#00F5FF]">~15 min</div>
            </div>
          </div>
          
          <p className="text-sm text-muted-foreground">
            Analyse approfondie pour tout comprendre
          </p>
          
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="px-2 py-1 rounded-full bg-muted text-xs">8 sujets</span>
            <span className="px-2 py-1 rounded-full bg-muted text-xs">200 mots/sujet</span>
          </div>
        </motion.button>
      </div>
    </div>
  );
}
