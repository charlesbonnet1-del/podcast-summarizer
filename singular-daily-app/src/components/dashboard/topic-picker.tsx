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
      { id: "ia", label: "IA & LLM", description: "Intelligence artificielle, ChatGPT, Claude et les dernières avancées en machine learning.", keywords: ["IA", "LLM", "ChatGPT", "OpenAI", "Claude", "GPT"] },
      { id: "quantum", label: "Quantum Computing", description: "Ordinateurs quantiques, qubits et les percées d'IBM, Google et startups.", keywords: ["quantique", "quantum", "qubits", "IBM Quantum"] },
      { id: "robotics", label: "Robotique", description: "Robots humanoïdes, automatisation industrielle et véhicules autonomes.", keywords: ["robotique", "robots", "Tesla Bot", "Boston Dynamics"] },
    ]
  },
  {
    id: "world",
    name: "Monde",
    Icon: Globe,
    topics: [
      { id: "asia", label: "Asie", description: "Actualités de Chine, Japon, Corée et tensions géopolitiques en Asie-Pacifique.", keywords: ["Chine", "Japon", "Corée", "Taïwan", "Asie"] },
      { id: "resources", label: "Ressources", description: "Marchés du pétrole, gaz, métaux rares et enjeux d'approvisionnement.", keywords: ["pétrole", "gaz", "matières premières", "minerais"] },
      { id: "regulation", label: "Régulation", description: "Nouvelles lois tech, RGPD, antitrust et décisions des régulateurs.", keywords: ["régulation", "lois", "RGPD", "antitrust", "gouvernance"] },
    ]
  },
  {
    id: "economics",
    name: "Économie",
    Icon: TrendingUp,
    topics: [
      { id: "stocks", label: "Bourse", description: "CAC 40, Wall Street, résultats d'entreprises et tendances des marchés.", keywords: ["CAC 40", "Wall Street", "bourse", "actions"] },
      { id: "crypto", label: "Crypto", description: "Bitcoin, Ethereum, DeFi et évolutions réglementaires des cryptomonnaies.", keywords: ["Bitcoin", "Ethereum", "crypto", "blockchain"] },
      { id: "macro", label: "Macro-économie", description: "Décisions de la BCE et Fed, inflation, croissance et emploi.", keywords: ["BCE", "Fed", "inflation", "économie mondiale"] },
    ]
  },
  {
    id: "science",
    name: "Science",
    Icon: FlaskConical,
    topics: [
      { id: "space", label: "Espace", description: "Missions NASA et SpaceX, exploration de Mars et satellites.", keywords: ["NASA", "SpaceX", "espace", "Mars", "fusée"] },
      { id: "health", label: "Santé", description: "Recherche médicale, biotechnologies, vaccins et santé publique.", keywords: ["santé", "médecine", "biotech", "vaccin"] },
      { id: "energy", label: "Énergie", description: "Transition énergétique, nucléaire, renouvelables et climat.", keywords: ["énergie", "nucléaire", "renouvelable", "climat"] },
    ]
  },
  {
    id: "culture",
    name: "Culture",
    Icon: Film,
    topics: [
      { id: "cinema", label: "Cinéma & Séries", description: "Sorties films, séries Netflix/Disney+ et actualités du 7ème art.", keywords: ["cinéma", "Netflix", "films", "séries"] },
      { id: "gaming", label: "Gaming", description: "Jeux vidéo, consoles, esport et industrie du gaming.", keywords: ["jeux vidéo", "PlayStation", "Nintendo", "gaming"] },
      { id: "lifestyle", label: "Lifestyle", description: "Tendances, design, mode et innovations du quotidien.", keywords: ["lifestyle", "tendances", "mode", "design"] },
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
