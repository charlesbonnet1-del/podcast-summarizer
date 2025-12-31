"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  ChevronDown, Sparkles, Loader2
} from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

// ============================================
// TYPES
// ============================================

interface SignalMixerProps {
  initialWeights?: Record<string, number>;
}

// ============================================
// VERTICALS WITH TOPICS (V13 - 15 Topics)
// ============================================

const VERTICALS = [
  {
    id: "tech",
    name: "Tech",
    topics: [
      { id: "ia", label: "IA, Robotique & Hardware", description: "AGI, LLMs, robots et puces" },
      { id: "cyber", label: "Cybersécurité", description: "Menaces, zero-days et défenses" },
      { id: "deep_tech", label: "Deep Tech", description: "Quantum, fusion et matériaux" },
    ]
  },
  {
    id: "science",
    name: "Science",
    topics: [
      { id: "health", label: "Santé & Longévité", description: "Biotech, anti-âge et biohacking" },
      { id: "space", label: "Espace", description: "Économie orbitale et exploration" },
      { id: "energy", label: "Énergie", description: "Mix énergétique et stockage" },
    ]
  },
  {
    id: "economics",
    name: "Économie",
    topics: [
      { id: "crypto", label: "Crypto", description: "Protocoles et décentralisation" },
      { id: "macro", label: "Macro-économie", description: "Banques centrales et tendances" },
      { id: "deals", label: "M&A & VC", description: "Levées, acquisitions et marchés" },
    ]
  },
  {
    id: "world",
    name: "Monde",
    topics: [
      { id: "asia", label: "Asie", description: "Tech chinoise et émergents" },
      { id: "regulation", label: "Régulation", description: "Lois et compliance" },
      { id: "resources", label: "Ressources", description: "Matières et supply chains" },
    ]
  },
  {
    id: "influence",
    name: "Influence",
    topics: [
      { id: "info", label: "Guerre de l'Information", description: "Désinformation et influence ops" },
      { id: "attention", label: "Marchés de l'Attention", description: "Algorithmes et plateformes" },
      { id: "persuasion", label: "Stratégies de Persuasion", description: "Nudges et design cognitif" },
    ]
  }
];

// Flatten topics for initialization
const ALL_TOPICS = VERTICALS.flatMap(v => v.topics);

// ============================================
// HELPER FUNCTIONS
// ============================================

function getSignalLabel(weight: number) {
  if (weight >= 80) return { label: "Focus", color: "text-cyan dark:text-cyan" };      // cyan
  if (weight >= 50) return { label: "Actif", color: "text-tech-blue dark:text-cyan/80" };  // blue/cyan
  if (weight >= 20) return { label: "Passif", color: "text-muted-foreground" };     // muted
  if (weight > 0) return { label: "Faible", color: "text-muted-foreground/70" };
  return { label: "Off", color: "text-muted-foreground/50" };
}

function getSliderColor(weight: number): string {
  if (weight >= 80) return '#00F0FF';  // cyan - Focus
  if (weight >= 50) return '#007AFF';  // blue - Actif  
  if (weight >= 20) return '#4DA3FF';  // light blue - Passif
  return '#6b7280';                     // gray - Faible/Off
}

// ============================================
// SIGNAL MIXER COMPONENT
// ============================================

export default function SignalMixer({ initialWeights = {} }: SignalMixerProps) {
  const [weights, setWeights] = useState<Record<string, number>>(() => {
    const defaults: Record<string, number> = {};
    ALL_TOPICS.forEach(t => defaults[t.id] = 50);
    return { ...defaults, ...initialWeights };
  });
  const [expandedVertical, setExpandedVertical] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const router = useRouter();

  // Track changes
  useEffect(() => {
    const hasChanged = Object.keys(weights).some(
      key => weights[key] !== (initialWeights[key] ?? 50)
    );
    setHasChanges(hasChanged);
  }, [weights, initialWeights]);

  // Calculate vertical average weight
  const getVerticalWeight = (verticalId: string) => {
    const vertical = VERTICALS.find(v => v.id === verticalId);
    if (!vertical) return 50;
    const topicWeights = vertical.topics.map(t => weights[t.id] ?? 50);
    return Math.round(topicWeights.reduce((a, b) => a + b, 0) / topicWeights.length);
  };

  // Update all topics in a vertical
  const updateVerticalWeight = (verticalId: string, value: number) => {
    const vertical = VERTICALS.find(v => v.id === verticalId);
    if (!vertical) return;
    
    setWeights(prev => {
      const newWeights = { ...prev };
      vertical.topics.forEach(t => {
        newWeights[t.id] = value;
      });
      return newWeights;
    });
  };

  // Update single topic
  const updateTopicWeight = (topicId: string, value: number) => {
    setWeights(prev => ({ ...prev, [topicId]: value }));
  };

  const saveWeights = async () => {
    setSaving(true);
    try {
      const response = await fetch("/api/signal-weights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weights }),
      });
      
      if (!response.ok) throw new Error();
      toast.success("Signal Mixer sauvegardé");
      setHasChanges(false);
      router.refresh();
    } catch {
      toast.error("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  const resetToDefaults = () => {
    const defaults: Record<string, number> = {};
    ALL_TOPICS.forEach(t => defaults[t.id] = 50);
    setWeights(defaults);
  };

  return (
    <div className="space-y-4">
      {/* Reset button */}
      <div className="flex justify-end">
        <button
          onClick={resetToDefaults}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Réinitialiser
        </button>
      </div>

      {/* Verticals */}
      {VERTICALS.map((vertical) => {
        const verticalWeight = getVerticalWeight(vertical.id);
        const signal = getSignalLabel(verticalWeight);
        const isExpanded = expandedVertical === vertical.id;
        const sliderColor = getSliderColor(verticalWeight);
        
        return (
          <motion.div
            key={vertical.id}
            className="rounded-xl bg-secondary/30 border border-border/30 overflow-hidden"
            layout
          >
            {/* Vertical Header with Slider */}
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="font-display font-semibold text-base">
                    {vertical.name}
                  </span>
                  <span className={`text-xs font-mono ${signal.color}`}>
                    {verticalWeight}%
                  </span>
                </div>
                <button
                  onClick={() => setExpandedVertical(isExpanded ? null : vertical.id)}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
                >
                  {isExpanded ? "Réduire" : "Détailler"}
                  <ChevronDown className={`w-3 h-3 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                </button>
              </div>

              {/* Vertical Slider */}
              <input
                type="range"
                min="0"
                max="100"
                step="10"
                value={verticalWeight}
                onChange={(e) => updateVerticalWeight(vertical.id, parseInt(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer bg-muted
                  [&::-webkit-slider-thumb]:appearance-none
                  [&::-webkit-slider-thumb]:w-5
                  [&::-webkit-slider-thumb]:h-5
                  [&::-webkit-slider-thumb]:rounded-full
                  [&::-webkit-slider-thumb]:bg-white
                  [&::-webkit-slider-thumb]:border-2
                  [&::-webkit-slider-thumb]:border-cyan
                  [&::-webkit-slider-thumb]:shadow-md
                  [&::-webkit-slider-thumb]:cursor-pointer
                  [&::-moz-range-thumb]:w-5
                  [&::-moz-range-thumb]:h-5
                  [&::-moz-range-thumb]:rounded-full
                  [&::-moz-range-thumb]:bg-white
                  [&::-moz-range-thumb]:border-2
                  [&::-moz-range-thumb]:border-cyan
                  [&::-moz-range-thumb]:shadow-md
                  [&::-moz-range-thumb]:cursor-pointer"
                style={{
                  background: `linear-gradient(to right, 
                    ${sliderColor} 0%, 
                    ${sliderColor} ${verticalWeight}%, 
                    hsl(var(--muted)) ${verticalWeight}%, 
                    hsl(var(--muted)) 100%)`
                }}
              />
            </div>

            {/* Expanded Topics */}
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="border-t border-border/30"
                >
                  <div className="p-3 space-y-3 bg-card/50">
                    {vertical.topics.map((topic) => {
                      const topicWeight = weights[topic.id] ?? 50;
                      const topicSignal = getSignalLabel(topicWeight);
                      const topicSliderColor = getSliderColor(topicWeight);
                      
                      return (
                        <div key={topic.id} className="space-y-1">
                          <div className="flex items-center justify-between">
                            <div>
                              <span className="text-sm font-medium">{topic.label}</span>
                              <p className="text-[10px] text-muted-foreground leading-tight">
                                {topic.description}
                              </p>
                            </div>
                            <span className={`text-xs font-mono ${topicSignal.color}`}>
                              {topicWeight}%
                            </span>
                          </div>
                          
                          <input
                            type="range"
                            min="0"
                            max="100"
                            step="10"
                            value={topicWeight}
                            onChange={(e) => updateTopicWeight(topic.id, parseInt(e.target.value))}
                            className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-muted
                              [&::-webkit-slider-thumb]:appearance-none
                              [&::-webkit-slider-thumb]:w-4
                              [&::-webkit-slider-thumb]:h-4
                              [&::-webkit-slider-thumb]:rounded-full
                              [&::-webkit-slider-thumb]:bg-white
                              [&::-webkit-slider-thumb]:border-2
                              [&::-webkit-slider-thumb]:border-cyan
                              [&::-webkit-slider-thumb]:shadow-sm
                              [&::-webkit-slider-thumb]:cursor-pointer
                              [&::-moz-range-thumb]:w-4
                              [&::-moz-range-thumb]:h-4
                              [&::-moz-range-thumb]:rounded-full
                              [&::-moz-range-thumb]:bg-white
                              [&::-moz-range-thumb]:border-2
                              [&::-moz-range-thumb]:border-cyan
                              [&::-moz-range-thumb]:shadow-sm
                              [&::-moz-range-thumb]:cursor-pointer"
                            style={{
                              background: `linear-gradient(to right, 
                                ${topicSliderColor} 0%, 
                                ${topicSliderColor} ${topicWeight}%, 
                                hsl(var(--muted)) ${topicWeight}%, 
                                hsl(var(--muted)) 100%)`
                            }}
                          />
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        );
      })}

      {/* Wildcard info */}
      <div className="p-3 rounded-xl bg-cyan/5 border border-cyan/20">
        <div className="flex items-start gap-2">
          <Sparkles className="w-4 h-4 text-cyan flex-shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground">
            <span className="text-cyan font-medium">Wildcard</span> : Un sujet à 0% peut surgir pour casser la bulle
          </p>
        </div>
      </div>

      {/* Spacer for fixed button on mobile */}
      <div className="h-20 sm:h-4" />

      {/* Save button - fixed on mobile */}
      <AnimatePresence>
        {hasChanges && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed sm:sticky bottom-20 sm:bottom-4 left-0 right-0 sm:left-auto sm:right-auto px-4 sm:px-0 z-20"
          >
            <button
              onClick={saveWeights}
              disabled={saving}
              className="w-full py-3 rounded-xl bg-charcoal dark:bg-cream text-cream dark:text-charcoal font-display font-medium hover:opacity-90 transition-opacity shadow-lg disabled:opacity-50"
            >
              {saving ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Sauvegarde...
                </span>
              ) : (
                "Sauvegarder le Mix"
              )}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
