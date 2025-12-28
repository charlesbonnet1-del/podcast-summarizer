"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { createClient } from "@/lib/supabase/client";
import { 
  Check, 
  Lock, 
  ChevronDown, 
  Bot,           // Tech 🤖
  Globe,         // World 🌍
  TrendingUp,    // Economics 📈
  FlaskConical,  // Science 🔬
  Radio          // Influence 📡
} from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

/**
 * V13 Topic structure - 15 topics across 5 verticals
 * Matching backend VALID_TOPICS in stitcher_v2.py
 */
const TOPIC_CATEGORIES = [
  {
    id: "tech",
    name: "Tech",
    Icon: Bot,
    topics: [
      { id: "ia", label: "IA, Robotique & Hardware", description: "Intelligence artificielle, LLMs, robots, puces et avancées matérielles.", keywords: ["IA", "LLM", "ChatGPT", "OpenAI", "Claude", "GPT", "robotique", "NVIDIA", "puces"] },
      { id: "cyber", label: "Cybersécurité", description: "Menaces, vulnérabilités, défenses et incidents de sécurité informatique.", keywords: ["cybersécurité", "hacking", "ransomware", "zero-day", "breach", "sécurité"] },
      { id: "deep_tech", label: "Deep Tech", description: "Quantum, fusion nucléaire, nouveaux matériaux et technologies de rupture.", keywords: ["quantique", "quantum", "fusion", "matériaux", "deep tech", "breakthrough"] },
    ]
  },
  {
    id: "science",
    name: "Science",
    Icon: FlaskConical,
    topics: [
      { id: "health", label: "Santé & Longévité", description: "Recherche médicale, biotechnologies, anti-âge et optimisation humaine.", keywords: ["santé", "médecine", "biotech", "longévité", "anti-âge", "CRISPR"] },
      { id: "space", label: "Espace", description: "Missions spatiales, satellites, exploration et économie orbitale.", keywords: ["NASA", "SpaceX", "espace", "Mars", "satellite", "fusée", "orbite"] },
      { id: "energy", label: "Énergie", description: "Transition énergétique, nucléaire, renouvelables et stockage.", keywords: ["énergie", "nucléaire", "renouvelable", "batterie", "solaire", "hydrogène"] },
    ]
  },
  {
    id: "economics",
    name: "Économie",
    Icon: TrendingUp,
    topics: [
      { id: "crypto", label: "Crypto", description: "Bitcoin, Ethereum, DeFi, protocoles et adoption institutionnelle.", keywords: ["Bitcoin", "Ethereum", "crypto", "blockchain", "DeFi", "NFT"] },
      { id: "macro", label: "Macro-économie", description: "Politiques monétaires, banques centrales, inflation et tendances mondiales.", keywords: ["BCE", "Fed", "inflation", "taux", "économie mondiale", "récession"] },
      { id: "stocks", label: "Marchés", description: "Actions, valorisations, rotations sectorielles et signaux de long terme.", keywords: ["bourse", "actions", "Wall Street", "CAC 40", "earnings", "IPO"] },
      { id: "deals", label: "M&A & VC", description: "Fusions-acquisitions, levées de fonds, VC et mouvements de capital stratégiques.", keywords: ["M&A", "acquisition", "levée de fonds", "VC", "funding", "série A", "IPO"] },
    ]
  },
  {
    id: "world",
    name: "Monde",
    Icon: Globe,
    topics: [
      { id: "asia", label: "Asie", description: "Signaux tech, politiques et économiques de Chine, Japon, Corée et Asie-Pacifique.", keywords: ["Chine", "Japon", "Corée", "Taïwan", "Asie", "ASEAN"] },
      { id: "regulation", label: "Régulation", description: "Nouvelles lois, antitrust, normes et arbitrages réglementaires.", keywords: ["régulation", "lois", "RGPD", "antitrust", "compliance", "UE"] },
      { id: "resources", label: "Ressources", description: "Matières premières, métaux critiques, supply chains et géopolitique des ressources.", keywords: ["pétrole", "lithium", "terres rares", "minerais", "supply chain"] },
    ]
  },
  {
    id: "influence",
    name: "Influence",
    Icon: Radio,
    topics: [
      { id: "info", label: "Guerre de l'Information", description: "Désinformation, influence ops, contrôle narratif et fact-checking.", keywords: ["désinformation", "fake news", "propagande", "influence", "manipulation"] },
      { id: "attention", label: "Marchés de l'Attention", description: "Plateformes, algorithmes, captation d'attention et modèles mentaux.", keywords: ["attention", "algorithme", "réseaux sociaux", "TikTok", "engagement"] },
      { id: "persuasion", label: "Stratégies de Persuasion", description: "Rhétorique, nudges, design persuasif et techniques d'adhésion.", keywords: ["persuasion", "nudge", "marketing", "influence", "psychologie"] },
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
