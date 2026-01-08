"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

// ============================================
// TYPES
// ============================================

interface TopicSelectorProps {
  initialTopics?: string[];
  minTopics?: number;
  onComplete?: () => void;
  isOnboarding?: boolean;
}

interface Topic {
  id: string;
  label: string;
  description: string;
}

interface Vertical {
  id: string;
  name: string;
  emoji: string;
  topics: Topic[];
}

// ============================================
// VERTICALS WITH TOPICS (V19 - 15 User-Selectable Topics)
// ============================================

const VERTICALS: Vertical[] = [
  {
    id: "tech",
    name: "Tech",
    emoji: "🤖",
    topics: [
      { id: "ia", label: "IA & Robotique", description: "AGI, LLMs, robots et puces" },
      { id: "cyber", label: "Cybersécurité", description: "Menaces, zero-days et défenses" },
      { id: "deep_tech", label: "Deep Tech", description: "Quantum, fusion et matériaux" },
    ]
  },
  {
    id: "science",
    name: "Science",
    emoji: "🔬",
    topics: [
      { id: "health", label: "Santé & Longévité", description: "Biotech, anti-âge et médecine" },
      { id: "space", label: "Espace", description: "Économie orbitale et exploration" },
      { id: "energy", label: "Énergie", description: "Mix énergétique et stockage" },
    ]
  },
  {
    id: "economics",
    name: "Économie",
    emoji: "📈",
    topics: [
      { id: "crypto", label: "Crypto", description: "Protocoles et décentralisation" },
      { id: "macro", label: "Macro-économie", description: "Banques centrales et tendances" },
      { id: "deals", label: "M&A & VC", description: "Levées et acquisitions" },
    ]
  },
  {
    id: "world",
    name: "Monde",
    emoji: "🌍",
    topics: [
      { id: "asia", label: "Asie", description: "Tech chinoise et émergents" },
      { id: "regulation", label: "Régulation", description: "Lois et compliance" },
      { id: "resources", label: "Ressources", description: "Matières et supply chains" },
    ]
  },
  {
    id: "influence",
    name: "Influence",
    emoji: "🎯",
    topics: [
      { id: "info", label: "Guerre de l'Info", description: "Désinformation et influence" },
      { id: "attention", label: "Marchés de l'Attention", description: "Algorithmes et plateformes" },
      { id: "persuasion", label: "Stratégies de Persuasion", description: "Nudges et design cognitif" },
    ]
  }
  // Note: "general" topic is internal only (for authority source enrichment)
];

// ============================================
// TOPIC SELECTOR COMPONENT
// ============================================

export default function TopicSelector({
  initialTopics = [],
  minTopics = 5,
  onComplete,
  isOnboarding = false
}: TopicSelectorProps) {
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(
    new Set(initialTopics)
  );
  const [saving, setSaving] = useState(false);
  const router = useRouter();

  const toggleTopic = (topicId: string) => {
    setSelectedTopics(prev => {
      const next = new Set(prev);
      if (next.has(topicId)) {
        next.delete(topicId);
      } else {
        next.add(topicId);
      }
      return next;
    });
  };

  const selectAll = (verticalId: string) => {
    const vertical = VERTICALS.find(v => v.id === verticalId);
    if (!vertical) return;

    setSelectedTopics(prev => {
      const next = new Set(prev);
      vertical.topics.forEach(t => next.add(t.id));
      return next;
    });
  };

  const isValid = selectedTopics.size >= minTopics;
  const remaining = minTopics - selectedTopics.size;

  const saveTopics = async () => {
    if (!isValid) {
      toast.error(`Sélectionnez au moins ${minTopics} sujets`);
      return;
    }

    setSaving(true);
    try {
      const response = await fetch("/api/selected-topics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topics: Array.from(selectedTopics) }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "Erreur");
      }

      toast.success("Préférences sauvegardées !");

      if (onComplete) {
        onComplete();
      } else if (isOnboarding) {
        router.push("/dashboard");
      } else {
        router.refresh();
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Progress indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-cyan" />
          <span className="text-sm font-medium">
            {selectedTopics.size} / {minTopics} minimum
          </span>
        </div>
        {remaining > 0 && (
          <span className="text-xs text-muted-foreground">
            Encore {remaining} à choisir
          </span>
        )}
        {isValid && (
          <span className="text-xs text-green-500 flex items-center gap-1">
            <Check className="w-3 h-3" /> Prêt
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-gradient-to-r from-cyan to-tech-blue"
          initial={{ width: 0 }}
          animate={{
            width: `${Math.min(100, (selectedTopics.size / minTopics) * 100)}%`
          }}
          transition={{ duration: 0.3 }}
        />
      </div>

      {/* Verticals */}
      <div className="space-y-4">
        {VERTICALS.map((vertical) => {
          const selectedCount = vertical.topics.filter(t =>
            selectedTopics.has(t.id)
          ).length;

          return (
            <div
              key={vertical.id}
              className="rounded-xl bg-secondary/30 border border-border/30 overflow-hidden"
            >
              {/* Vertical Header */}
              <div className="p-3 flex items-center justify-between border-b border-border/20">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{vertical.emoji}</span>
                  <span className="font-display font-semibold">
                    {vertical.name}
                  </span>
                  {selectedCount > 0 && (
                    <span className="text-xs bg-cyan/20 text-cyan px-2 py-0.5 rounded-full">
                      {selectedCount}
                    </span>
                  )}
                </div>
                {vertical.topics.length > 1 && selectedCount < vertical.topics.length && (
                  <button
                    onClick={() => selectAll(vertical.id)}
                    className="text-xs text-muted-foreground hover:text-cyan transition-colors"
                  >
                    Tout sélectionner
                  </button>
                )}
              </div>

              {/* Topics Grid */}
              <div className="p-3 grid gap-2">
                {vertical.topics.map((topic) => {
                  const isSelected = selectedTopics.has(topic.id);

                  return (
                    <motion.button
                      key={topic.id}
                      onClick={() => toggleTopic(topic.id)}
                      className={cn(
                        "w-full p-3 rounded-lg text-left transition-all",
                        "border-2",
                        isSelected
                          ? "border-cyan bg-cyan/10"
                          : "border-transparent bg-card/50 hover:bg-card/80"
                      )}
                      whileTap={{ scale: 0.98 }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-medium text-sm">
                            {topic.label}
                          </span>
                          <p className="text-[11px] text-muted-foreground mt-0.5">
                            {topic.description}
                          </p>
                        </div>
                        <AnimatePresence>
                          {isSelected && (
                            <motion.div
                              initial={{ scale: 0 }}
                              animate={{ scale: 1 }}
                              exit={{ scale: 0 }}
                              className="w-6 h-6 rounded-full bg-cyan flex items-center justify-center"
                            >
                              <Check className="w-4 h-4 text-charcoal" />
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </motion.button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Info box */}
      <div className="p-3 rounded-xl bg-cyan/5 border border-cyan/20">
        <div className="flex items-start gap-2">
          <Sparkles className="w-4 h-4 text-cyan flex-shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground">
            <span className="text-cyan font-medium">Top 3</span> : Chaque jour, votre podcast
            contient les 3 meilleurs sujets parmi vos choix, classés par pertinence.
          </p>
        </div>
      </div>

      {/* Spacer for fixed button */}
      <div className="h-24" />

      {/* Save button - fixed at bottom */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-background via-background to-transparent">
        <div className="max-w-lg mx-auto">
          <button
            onClick={saveTopics}
            disabled={!isValid || saving}
            className={cn(
              "w-full py-4 rounded-xl font-display font-medium text-lg transition-all",
              "shadow-lg",
              isValid
                ? "bg-charcoal dark:bg-cream text-cream dark:text-charcoal hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed"
            )}
          >
            {saving ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 className="w-5 h-5 animate-spin" />
                Sauvegarde...
              </span>
            ) : isOnboarding ? (
              isValid ? "Commencer" : `Sélectionnez ${remaining} sujet${remaining > 1 ? 's' : ''} de plus`
            ) : (
              isValid ? "Sauvegarder" : `Sélectionnez ${remaining} sujet${remaining > 1 ? 's' : ''} de plus`
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
