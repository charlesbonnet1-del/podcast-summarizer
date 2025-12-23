"use client";

import { Users } from "lucide-react";

/**
 * Voice Duo Info Component
 * Displays information about the fixed Breeze & Vale duo
 * No user selection - voices are fixed for dialogue format
 */
export function SettingsForm() {
  return (
    <div className="space-y-6">
      {/* Duo Info */}
      <div className="rounded-2xl border border-border bg-card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-primary/10">
            <Users className="w-5 h-5 text-primary" />
          </div>
          <h3 className="font-semibold">Format Dialogue</h3>
        </div>
        
        <p className="text-sm text-muted-foreground mb-6">
          Votre podcast est présenté par un duo d'experts qui débattent et analysent l'actualité ensemble.
        </p>
        
        <div className="grid gap-4">
          {/* Breeze */}
          <div className="flex items-start gap-4 p-4 rounded-xl bg-muted/50">
            <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center font-serif font-bold text-primary">
              B
            </div>
            <div>
              <div className="font-medium">Breeze</div>
              <div className="text-sm text-muted-foreground">
                L'expert pédagogue — Pose le cadre, expose les faits et les chiffres
              </div>
            </div>
          </div>
          
          {/* Vale */}
          <div className="flex items-start gap-4 p-4 rounded-xl bg-muted/50">
            <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center font-serif font-bold">
              V
            </div>
            <div>
              <div className="font-medium">Vale</div>
              <div className="text-sm text-muted-foreground">
                Le challenger pragmatique — Questions directes, risques et implications concrètes
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {/* Style Info */}
      <div className="text-xs text-muted-foreground space-y-1">
        <p>• Ton factuel et analytique, sans superlatifs</p>
        <p>• Accessible aux non-experts, termes techniques expliqués</p>
        <p>• Dialogue naturel avec questions et réponses</p>
      </div>
    </div>
  );
}
