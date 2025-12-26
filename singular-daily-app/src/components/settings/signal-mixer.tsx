"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Bot, Globe, TrendingUp, FlaskConical, Film,
  Crosshair, Eye, EyeOff, Sparkles, Loader2
} from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

// ============================================
// TYPES
// ============================================

interface TopicWeight {
  id: string;
  label: string;
  weight: number;
  category: string;
}

interface SignalMixerProps {
  initialWeights?: Record<string, number>;
  userId?: string;
}

// ============================================
// TOPIC DEFINITIONS
// ============================================

const TOPICS = [
  // Tech
  { id: "ia", label: "IA", category: "Tech", icon: Bot },
  { id: "quantum", label: "Quantum", category: "Tech", icon: Bot },
  { id: "robotics", label: "Robotique", category: "Tech", icon: Bot },
  // Monde
  { id: "asia", label: "Asie", category: "Monde", icon: Globe },
  { id: "regulation", label: "Régulation", category: "Monde", icon: Globe },
  { id: "resources", label: "Ressources", category: "Monde", icon: Globe },
  // Économie
  { id: "crypto", label: "Crypto", category: "Économie", icon: TrendingUp },
  { id: "macro", label: "Macro", category: "Économie", icon: TrendingUp },
  { id: "stocks", label: "Bourse", category: "Économie", icon: TrendingUp },
  // Science
  { id: "energy", label: "Énergie", category: "Science", icon: FlaskConical },
  { id: "health", label: "Santé", category: "Science", icon: FlaskConical },
  { id: "space", label: "Espace", category: "Science", icon: FlaskConical },
  // Culture
  { id: "cinema", label: "Cinéma", category: "Culture", icon: Film },
  { id: "gaming", label: "Gaming", category: "Culture", icon: Film },
  { id: "lifestyle", label: "Lifestyle", category: "Culture", icon: Film },
];

// ============================================
// HELPER FUNCTIONS
// ============================================

function getSignalLabel(weight: number): { label: string; color: string; icon: React.ElementType } {
  if (weight >= 80) return { label: "Focus Chirurgical", color: "text-[#C5B358]", icon: Crosshair };
  if (weight >= 50) return { label: "Veille Active", color: "text-emerald-500", icon: Eye };
  if (weight >= 20) return { label: "Veille Passive", color: "text-blue-400", icon: Eye };
  if (weight > 0) return { label: "Signal Faible", color: "text-muted-foreground", icon: EyeOff };
  return { label: "Ignoré", color: "text-muted-foreground/50", icon: EyeOff };
}

function getSliderBackground(weight: number): string {
  if (weight >= 80) return "bg-gradient-to-r from-[#C5B358]/20 to-[#C5B358]";
  if (weight >= 50) return "bg-gradient-to-r from-emerald-500/20 to-emerald-500";
  if (weight >= 20) return "bg-gradient-to-r from-blue-400/20 to-blue-400";
  if (weight > 0) return "bg-gradient-to-r from-gray-400/20 to-gray-400";
  return "bg-muted";
}

// ============================================
// SIGNAL MIXER COMPONENT
// ============================================

export default function SignalMixer({ initialWeights = {}, userId }: SignalMixerProps) {
  const [weights, setWeights] = useState<Record<string, number>>(() => {
    // Initialize with defaults (50 for all) merged with any saved weights
    const defaults: Record<string, number> = {};
    TOPICS.forEach(t => defaults[t.id] = 50);
    return { ...defaults, ...initialWeights };
  });
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

  const updateWeight = (topicId: string, value: number) => {
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
      router.refresh();
    } catch {
      toast.error("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  };

  const resetToDefaults = () => {
    const defaults: Record<string, number> = {};
    TOPICS.forEach(t => defaults[t.id] = 50);
    setWeights(defaults);
  };

  // Group topics by category
  const categories = TOPICS.reduce((acc, topic) => {
    if (!acc[topic.category]) acc[topic.category] = [];
    acc[topic.category].push(topic);
    return acc;
  }, {} as Record<string, typeof TOPICS>);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#C5B358]/20 to-[#C5B358]/5 border border-[#C5B358]/20 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-[#C5B358]" />
          </div>
          <div>
            <h2 className="font-display text-lg font-semibold">Signal Mixer</h2>
            <p className="text-sm text-muted-foreground">Ajustez l'intensité de chaque signal</p>
          </div>
        </div>
        
        <button
          onClick={resetToDefaults}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Réinitialiser
        </button>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs">
        <div className="flex items-center gap-1.5">
          <Crosshair className="w-3.5 h-3.5 text-[#C5B358]" />
          <span className="text-muted-foreground">80-100: Focus Chirurgical</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Eye className="w-3.5 h-3.5 text-emerald-500" />
          <span className="text-muted-foreground">50-79: Veille Active</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Eye className="w-3.5 h-3.5 text-blue-400" />
          <span className="text-muted-foreground">20-49: Veille Passive</span>
        </div>
        <div className="flex items-center gap-1.5">
          <EyeOff className="w-3.5 h-3.5 text-muted-foreground/50" />
          <span className="text-muted-foreground">0: Ignoré (Wildcard possible)</span>
        </div>
      </div>

      {/* Categories */}
      <div className="space-y-6">
        {Object.entries(categories).map(([categoryName, topics]) => (
          <div key={categoryName} className="space-y-3">
            <h3 className="text-sm font-display font-medium text-muted-foreground uppercase tracking-wider">
              {categoryName}
            </h3>
            
            <div className="space-y-2">
              {topics.map((topic) => {
                const weight = weights[topic.id] ?? 50;
                const signal = getSignalLabel(weight);
                const Icon = topic.icon;
                const SignalIcon = signal.icon;
                
                return (
                  <motion.div
                    key={topic.id}
                    className="group p-4 rounded-xl bg-card border border-border/50 hover:border-border transition-colors"
                    layout
                  >
                    <div className="flex items-center gap-4">
                      {/* Topic info */}
                      <div className="flex items-center gap-3 min-w-[140px]">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                          weight > 0 ? "bg-secondary" : "bg-muted/50"
                        }`}>
                          <Icon className={`w-4 h-4 ${weight > 0 ? "text-foreground" : "text-muted-foreground/50"}`} />
                        </div>
                        <span className={`font-display font-medium ${
                          weight > 0 ? "" : "text-muted-foreground/50"
                        }`}>
                          {topic.label}
                        </span>
                      </div>

                      {/* Slider */}
                      <div className="flex-1 relative">
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="5"
                          value={weight}
                          onChange={(e) => updateWeight(topic.id, parseInt(e.target.value))}
                          className="w-full h-2 rounded-full appearance-none cursor-pointer bg-muted
                            [&::-webkit-slider-thumb]:appearance-none
                            [&::-webkit-slider-thumb]:w-5
                            [&::-webkit-slider-thumb]:h-5
                            [&::-webkit-slider-thumb]:rounded-full
                            [&::-webkit-slider-thumb]:bg-white
                            [&::-webkit-slider-thumb]:border-2
                            [&::-webkit-slider-thumb]:border-[#C5B358]
                            [&::-webkit-slider-thumb]:shadow-md
                            [&::-webkit-slider-thumb]:cursor-pointer
                            [&::-webkit-slider-thumb]:transition-transform
                            [&::-webkit-slider-thumb]:hover:scale-110
                            [&::-moz-range-thumb]:w-5
                            [&::-moz-range-thumb]:h-5
                            [&::-moz-range-thumb]:rounded-full
                            [&::-moz-range-thumb]:bg-white
                            [&::-moz-range-thumb]:border-2
                            [&::-moz-range-thumb]:border-[#C5B358]
                            [&::-moz-range-thumb]:shadow-md
                            [&::-moz-range-thumb]:cursor-pointer"
                          style={{
                            background: `linear-gradient(to right, 
                              ${weight >= 80 ? '#C5B358' : weight >= 50 ? '#10b981' : weight >= 20 ? '#60a5fa' : '#9ca3af'} 0%, 
                              ${weight >= 80 ? '#C5B358' : weight >= 50 ? '#10b981' : weight >= 20 ? '#60a5fa' : '#9ca3af'} ${weight}%, 
                              hsl(var(--muted)) ${weight}%, 
                              hsl(var(--muted)) 100%)`
                          }}
                        />
                      </div>

                      {/* Weight display */}
                      <div className="flex items-center gap-2 min-w-[130px] justify-end">
                        <SignalIcon className={`w-4 h-4 ${signal.color}`} />
                        <span className={`text-sm font-mono ${signal.color}`}>
                          {weight}%
                        </span>
                        <span className={`text-xs ${signal.color} hidden sm:inline`}>
                          {signal.label}
                        </span>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Wildcard explanation */}
      <div className="p-4 rounded-xl bg-[#C5B358]/5 border border-[#C5B358]/20">
        <div className="flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-[#C5B358] flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-[#C5B358]">Le Wildcard</p>
            <p className="text-sm text-muted-foreground mt-1">
              Chaque jour, un segment "surprise" issu d'un thème ignoré (0%) est injecté 
              dans votre podcast pour casser la bulle de filtres et vous exposer à l'inattendu.
            </p>
          </div>
        </div>
      </div>

      {/* Save button */}
      <AnimatePresence>
        {hasChanges && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="sticky bottom-4"
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
