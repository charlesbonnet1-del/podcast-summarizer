"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";

// ============================================
// TYPES
// ============================================

interface SignalRadarProps {
  weights: Record<string, number>;
  size?: number;
  showLabels?: boolean;
  className?: string;
}

interface TopicData {
  id: string;
  label: string;
  shortLabel: string;
}

// ============================================
// TOPIC DEFINITIONS (V13 - 15 Topics)
// ============================================

const ALL_TOPICS: TopicData[] = [
  // V1 TECH
  { id: "ia", label: "IA, Robotique & Hardware", shortLabel: "IA" },
  { id: "cyber", label: "Cybersécurité", shortLabel: "Cyber" },
  { id: "deep_tech", label: "Deep Tech", shortLabel: "Deep" },
  // V2 SCIENCE
  { id: "health", label: "Santé & Longévité", shortLabel: "Santé" },
  { id: "space", label: "Espace", shortLabel: "Space" },
  { id: "energy", label: "Énergie", shortLabel: "Energy" },
  // V3 ECONOMICS
  { id: "crypto", label: "Crypto", shortLabel: "Crypto" },
  { id: "macro", label: "Macro-économie", shortLabel: "Macro" },
  { id: "deals", label: "M&A & VC", shortLabel: "Deals" },
  // V4 WORLD
  { id: "asia", label: "Asie", shortLabel: "Asia" },
  { id: "regulation", label: "Régulation", shortLabel: "Régul" },
  { id: "resources", label: "Ressources", shortLabel: "Ress" },
  // V5 INFLUENCE
  { id: "info", label: "Guerre de l'Information", shortLabel: "Info" },
  { id: "attention", label: "Marchés de l'Attention", shortLabel: "Attn" },
  { id: "persuasion", label: "Persuasion", shortLabel: "Persu" },
];

// ============================================
// RADAR CHART COMPONENT
// ============================================

export default function SignalRadar({ 
  weights, 
  size = 200, 
  showLabels = true,
  className = "" 
}: SignalRadarProps) {
  // Get top 5 topics by weight
  const topTopics = useMemo(() => {
    return ALL_TOPICS
      .map(t => ({ ...t, weight: weights[t.id] ?? 50 }))
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 5);
  }, [weights]);

  const centerX = size / 2;
  const centerY = size / 2;
  const maxRadius = (size / 2) - 30; // Leave space for labels
  
  // Calculate points for pentagon
  const getPoint = (index: number, value: number) => {
    const angle = (Math.PI * 2 * index) / 5 - Math.PI / 2; // Start from top
    const radius = (value / 100) * maxRadius;
    return {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  };

  // Generate polygon points for the data shape
  const dataPoints = topTopics.map((topic, i) => getPoint(i, topic.weight));
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  // Generate grid rings (20%, 40%, 60%, 80%, 100%)
  const rings = [20, 40, 60, 80, 100];

  // Label positions (slightly outside the max radius)
  const labelRadius = maxRadius + 20;
  const labelPositions = topTopics.map((_, i) => {
    const angle = (Math.PI * 2 * i) / 5 - Math.PI / 2;
    return {
      x: centerX + labelRadius * Math.cos(angle),
      y: centerY + labelRadius * Math.sin(angle),
    };
  });

  return (
    <div className={`relative ${className}`}>
      <svg width={size} height={size} className="overflow-visible">
        {/* Grid rings */}
        {rings.map((ring) => {
          const points = Array.from({ length: 5 }, (_, i) => {
            const p = getPoint(i, ring);
            return `${p.x},${p.y}`;
          }).join(' ');
          
          return (
            <polygon
              key={ring}
              points={points}
              fill="none"
              stroke="currentColor"
              strokeOpacity={0.1}
              strokeWidth={1}
            />
          );
        })}

        {/* Axis lines */}
        {topTopics.map((_, i) => {
          const endPoint = getPoint(i, 100);
          return (
            <line
              key={i}
              x1={centerX}
              y1={centerY}
              x2={endPoint.x}
              y2={endPoint.y}
              stroke="currentColor"
              strokeOpacity={0.1}
              strokeWidth={1}
            />
          );
        })}

        {/* Gradient definitions */}
        <defs>
          <linearGradient id="cyanGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00F0FF" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#007AFF" stopOpacity="0.1" />
          </linearGradient>
        </defs>

        {/* Data shape */}
        <motion.path
          d={dataPath}
          fill="url(#cyanGradient)"
          stroke="currentColor"
          strokeWidth={2}
          className="stroke-tech-blue dark:stroke-cyan"
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          style={{ transformOrigin: `${centerX}px ${centerY}px` }}
        />

        {/* Data points */}
        {dataPoints.map((point, i) => (
          <motion.circle
            key={i}
            cx={point.x}
            cy={point.y}
            r={4}
            className="fill-tech-blue dark:fill-cyan"
            stroke="white"
            strokeWidth={2}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1 * i, duration: 0.3 }}
          />
        ))}

        {/* Center dot */}
        <circle
          cx={centerX}
          cy={centerY}
          r={3}
          fill="currentColor"
          fillOpacity={0.2}
        />
      </svg>

      {/* Labels */}
      {showLabels && (
        <div className="absolute inset-0 pointer-events-none">
          {topTopics.map((topic, i) => {
            const pos = labelPositions[i];
            const isTop = i === 0;
            const isLeft = i === 3 || i === 4;
            const isRight = i === 1 || i === 2;
            
            return (
              <motion.div
                key={topic.id}
                className="absolute transform -translate-x-1/2 -translate-y-1/2"
                style={{ 
                  left: pos.x, 
                  top: pos.y,
                  textAlign: isLeft ? 'right' : isRight ? 'left' : 'center',
                  transform: `translate(${isLeft ? '-80%' : isRight ? '-20%' : '-50%'}, ${isTop ? '-80%' : '-50%'})`
                }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 + i * 0.1 }}
              >
                <div className="flex flex-col items-center">
                  <span className="text-[10px] font-display font-medium text-foreground">
                    {topic.shortLabel}
                  </span>
                  <span className="text-[9px] text-tech-blue dark:text-cyan font-mono">
                    {topic.weight}%
                  </span>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================
// COMPACT VERSION FOR DASHBOARD
// ============================================

export function SignalRadarCompact({ 
  weights, 
  onClick 
}: { 
  weights: Record<string, number>;
  onClick?: () => void;
}) {
  return (
    <motion.button
      onClick={onClick}
      className="relative group"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.98 }}
    >
      <SignalRadar 
        weights={weights} 
        size={160} 
        showLabels={true}
      />
      
      {/* Hover overlay */}
      <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
        <div className="px-3 py-1.5 rounded-full bg-charcoal/80 dark:bg-cream/80 backdrop-blur-sm">
          <span className="text-xs font-display text-cream dark:text-charcoal">
            Modifier
          </span>
        </div>
      </div>
    </motion.button>
  );
}
