"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { createClient } from "@/lib/supabase/client";
import { 
  Check, 
  Lock, 
  ChevronDown, 
  Bot,           // Tech 🤖
  Globe,         // Monde 🌍
  TrendingUp,    // Économie 📈
  FlaskConical,  // Science 🔬
  Film           // Culture 🎬
} from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

/**
 * V4 Topic structure - Using Lucide icons instead of emojis
 * All icons use text-sand color class for consistency
 */
const TOPIC_CATEGORIES = [
  {
    id: "tech",
    name: "Tech",
    Icon: Bot,
    topics: [
      { id: "ia", label: "IA", description: "Suivi de la course vers l'AGI, des infrastructures de calcul aux modèles génératifs qui transforment radicalement chaque strate de la société.", keywords: ["IA", "LLM", "ChatGPT", "OpenAI", "Claude", "GPT", "AGI"] },
      { id: "quantum", label: "Quantum", description: "Immersion dans l'ingénierie subatomique pour anticiper la prochaine rupture majeure de la puissance de calcul et de la cryptographie.", keywords: ["quantique", "quantum", "qubits", "IBM Quantum"] },
      { id: "robotics", label: "Robotique", description: "Analyse du déploiement des systèmes autonomes et des humanoïdes, marquant l'intégration finale de l'intelligence artificielle dans le monde physique.", keywords: ["robotique", "robots", "Tesla Bot", "Boston Dynamics", "humanoïdes"] },
    ]
  },
  {
    id: "world",
    name: "Monde",
    Icon: Globe,
    topics: [
      { id: "asia", label: "Asie", description: "Veille stratégique sur l'épicentre de l'innovation mondiale, décryptant les dynamiques de la tech chinoise et l'essor des marchés émergents asiatiques.", keywords: ["Chine", "Japon", "Corée", "Taïwan", "Asie"] },
      { id: "regulation", label: "Régulation", description: "Analyse des enjeux de souveraineté numérique et des évolutions législatives mondiales qui redéfinissent les frontières du permis et de l'interdit.", keywords: ["régulation", "lois", "RGPD", "antitrust", "gouvernance", "souveraineté"] },
      { id: "resources", label: "Ressources", description: "Décryptage de la géopolitique des matières premières et des minéraux critiques, piliers invisibles de la transition énergétique et technologique.", keywords: ["pétrole", "gaz", "matières premières", "minerais", "lithium"] },
    ]
  },
  {
    id: "economics",
    name: "Économie",
    Icon: TrendingUp,
    topics: [
      { id: "crypto", label: "Crypto", description: "Au cœur de la décentralisation financière, analysant l'évolution des protocoles, de la blockchain et la redéfinition de la notion même de valeur.", keywords: ["Bitcoin", "Ethereum", "crypto", "blockchain", "DeFi"] },
      { id: "macro", label: "Macro", description: "Analyse des rapports de force géopolitiques et des flux de capitaux mondiaux pour anticiper les grandes ruptures économiques de demain.", keywords: ["BCE", "Fed", "inflation", "économie mondiale", "géopolitique"] },
      { id: "stocks", label: "Bourse", description: "Suivi chirurgical des marchés publics et des valorisations d'entreprises pour identifier les tendances de fond de l'économie globale.", keywords: ["CAC 40", "Wall Street", "bourse", "actions", "valorisation"] },
    ]
  },
  {
    id: "science",
    name: "Science",
    Icon: FlaskConical,
    topics: [
      { id: "energy", label: "Énergie", description: "Veille sur le mix énergétique du futur, de la renaissance nucléaire aux innovations solaires, pour comprendre les enjeux de la puissance mondiale.", keywords: ["énergie", "nucléaire", "renouvelable", "solaire", "climat"] },
      { id: "health", label: "Santé & Longévité", description: "Exploration des frontières de la biologie et de l'optimisation humaine, de la réparation cellulaire au biohacking, pour étendre la longévité active.", keywords: ["santé", "médecine", "biotech", "longévité", "biohacking", "cellulaire"] },
      { id: "space", label: "Espace", description: "Décryptage de l'économie orbitale et de l'exploration interstellaire, marquant le passage de l'humanité vers une espèce multi-planétaire.", keywords: ["NASA", "SpaceX", "espace", "Mars", "orbite"] },
    ]
  },
  {
    id: "influence",
    name: "Influence",
    Icon: Film,
    topics: [
      { id: "info", label: "Guerre de l'Info", description: "Décryptage des campagnes d'influence étatiques, de la propagande automatisée et des cyber-opérations redéfinissant la souveraineté numérique mondiale.", keywords: ["propagande", "désinformation", "cyber", "influence", "guerre informationnelle"] },
      { id: "attention", label: "Marchés de l'Attention", description: "Analyse des algorithmes de recommandation et de l'économie des plateformes pour comprendre les mécanismes de capture et de monétisation de l'attention humaine.", keywords: ["algorithme", "attention", "plateformes", "engagement", "recommandation"] },
      { id: "persuasion", label: "Stratégies de Persuasion", description: "Étude des sciences comportementales et du design cognitif pour maîtriser les leviers de décision et le leadership d'opinion à l'échelle mondiale.", keywords: ["persuasion", "comportement", "nudge", "influence", "leadership"] },
    ]
  }
];

// Export for use in other components
export { TOPIC_CATEGORIES };

const MAX_TOPICS_FREE = 4;

interface TopicPickerProps {
  initialTopics?: string[];
  plan?: string;
}

export function TopicPicker({ initialTopics = [], plan = "free" }: TopicPickerProps) {
  const [selectedTopics, setSelectedTopics] = useState<string[]>(initialTopics);
  const [expandedCategories, setExpandedCategories] = useState<string[]>(
    TOPIC_CATEGORIES.map(c => c.id)
  );
  const [saving, setSaving] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const maxTopics = plan === "pro" ? 20 : MAX_TOPICS_FREE;
  const isAtLimit = selectedTopics.length >= maxTopics;

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories(prev => 
      prev.includes(categoryId) 
        ? prev.filter(id => id !== categoryId)
        : [...prev, categoryId]
    );
  };

  const toggleTopic = async (topicId: string, topicData: { label: string; keywords: string[] }) => {
    const isSelected = selectedTopics.includes(topicId);

    if (!isSelected && isAtLimit) {
      toast.error(`Limite de ${maxTopics} thèmes atteinte pour le plan ${plan}`);
      return;
    }

    setSaving(true);

    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error("Not authenticated");

      if (isSelected) {
        const { error } = await supabase
          .from("user_interests")
          .delete()
          .eq("user_id", user.id)
          .eq("keyword", topicId);

        if (error) throw error;

        setSelectedTopics(prev => prev.filter(id => id !== topicId));
        toast.success(`"${topicData.label}" retiré`);
      } else {
        const { error } = await supabase
          .from("user_interests")
          .insert({
            user_id: user.id,
            keyword: topicId,
            display_name: topicData.label,
            search_keywords: topicData.keywords
          });

        if (error) throw error;

        setSelectedTopics(prev => [...prev, topicId]);
        toast.success(`"${topicData.label}" ajouté`);
      }

      router.refresh();
    } catch (error) {
      console.error("Failed to toggle topic:", error);
      toast.error("Échec de la mise à jour");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header with count */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-display text-lg font-medium">Vos Thèmes</h3>
          <p className="text-sm text-muted-foreground">
            Sélectionnez jusqu'à {maxTopics} thèmes pour votre podcast
          </p>
        </div>
        <div className={`px-3 py-1 rounded-full text-sm font-display font-medium ${
          isAtLimit 
            ? "bg-amber-500/10 text-amber-600 dark:text-amber-400" 
            : "bg-secondary text-foreground"
        }`}>
          {selectedTopics.length}/{maxTopics}
        </div>
      </div>

      {/* Categories */}
      <div className="space-y-3">
        {TOPIC_CATEGORIES.map((category) => {
          const isExpanded = expandedCategories.includes(category.id);
          const selectedInCategory = category.topics.filter(t => 
            selectedTopics.includes(t.id)
          ).length;
          const CategoryIcon = category.Icon;

          return (
            <div 
              key={category.id}
              className="rounded-2xl border border-border/50 overflow-hidden bg-card/50"
            >
              {/* Category Header */}
              <button
                onClick={() => toggleCategory(category.id)}
                className="w-full flex items-center justify-between p-4 hover:bg-secondary/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {/* SVG Icon with sand color */}
                  <CategoryIcon className="w-5 h-5 text-sand" />
                  <span className="font-display font-medium">{category.name}</span>
                  {selectedInCategory > 0 && (
                    <span className="px-2 py-0.5 rounded-full bg-charcoal dark:bg-cream text-cream dark:text-charcoal text-xs font-display font-medium">
                      {selectedInCategory}
                    </span>
                  )}
                </div>
                <motion.div
                  animate={{ rotate: isExpanded ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <ChevronDown className="w-5 h-5 text-muted-foreground" />
                </motion.div>
              </button>

              {/* Topics */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 space-y-2">
                      {category.topics.map((topic) => {
                        const isSelected = selectedTopics.includes(topic.id);
                        const isDisabled = !isSelected && isAtLimit;

                        return (
                          <motion.button
                            key={topic.id}
                            onClick={() => toggleTopic(topic.id, topic)}
                            disabled={saving || isDisabled}
                            className={`w-full flex items-center justify-between p-3 rounded-xl transition-all ${
                              isSelected
                                ? "bg-charcoal dark:bg-cream text-cream dark:text-charcoal"
                                : isDisabled
                                  ? "bg-secondary/30 opacity-50 cursor-not-allowed"
                                  : "bg-secondary/50 hover:bg-secondary border border-transparent"
                            }`}
                            whileHover={!isDisabled ? { scale: 1.01 } : {}}
                            whileTap={!isDisabled ? { scale: 0.99 } : {}}
                          >
                            <div className="flex-1 text-left">
                              <span className={`text-sm font-display block ${isSelected ? "font-semibold" : "font-medium"}`}>
                                {topic.label}
                              </span>
                              <span className={`text-xs mt-0.5 block leading-tight ${
                                isSelected 
                                  ? "text-cream/70 dark:text-charcoal/70" 
                                  : "text-muted-foreground"
                              }`}>
                                {topic.description}
                              </span>
                            </div>
                            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all flex-shrink-0 ml-3 ${
                              isSelected
                                ? "border-cream dark:border-charcoal bg-brass"
                                : isDisabled
                                  ? "border-muted-foreground/20"
                                  : "border-muted-foreground/40"
                            }`}>
                              {isSelected && <Check className="w-3 h-3 text-charcoal" />}
                              {isDisabled && !isSelected && <Lock className="w-2.5 h-2.5 text-muted-foreground/40" />}
                            </div>
                          </motion.button>
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      {/* Limit warning */}
      {isAtLimit && plan === "free" && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20"
        >
          <p className="text-sm text-amber-600 dark:text-amber-400 font-display">
            <Lock className="w-4 h-4 inline mr-2" />
            Limite de {maxTopics} thèmes atteinte. Passez au plan Pro pour plus de thèmes.
          </p>
        </motion.div>
      )}
    </div>
  );
}
