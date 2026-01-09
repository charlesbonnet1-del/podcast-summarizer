"use client";

import { Zap } from "lucide-react";

/**
 * V19: Format selection removed - single 5-minute format only.
 * This component now just displays the fixed format info.
 */
export function FormatToggle() {
  return (
    <div className="p-6 rounded-2xl border-2 border-[#C5B358] bg-[#C5B358]/10">
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 rounded-xl bg-[#C5B358]/20">
          <Zap className="w-6 h-6 text-[#C5B358]" />
        </div>
        <div>
          <div className="font-semibold text-lg">Express</div>
          <div className="text-2xl font-bold text-[#C5B358]">~5 min</div>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        L'essentiel de l'actualité tech, chaque matin
      </p>

      <div className="mt-4">
        <span className="px-3 py-1.5 rounded-full bg-muted text-xs font-medium">5 sujets • Synthèse intelligente</span>
      </div>
    </div>
  );
}
