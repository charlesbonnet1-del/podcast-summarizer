"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Check, Globe, Bot, Landmark, TrendingUp, FlaskConical, Clapperboard } from "lucide-react";

// The 5 Alpha Verticals
const VERTICALS = [
  { id: "ai_tech", name: "IA & Tech", icon: Bot, description: "LLM, Hardware, Robotique, Startups" },
  { id: "politics", name: "Politique & Monde", icon: Landmark, description: "France, USA, Géopolitique" },
  { id: "finance", name: "Finance & Marchés", icon: TrendingUp, description: "Bourse, Crypto, Économie" },
  { id: "science", name: "Science & Santé", icon: FlaskConical, description: "Espace, Biotech, Climat" },
  { id: "culture", name: "Culture & Divertissement", icon: Clapperboard, description: "Cinéma, Gaming, Streaming" },
];

interface ProfileFormProps {
  email: string;
  firstName: string;
  lastName: string;
  memberSince?: string;
  plan: string;
  includeInternational?: boolean;
  selectedVerticals?: Record<string, boolean>;
}

export function ProfileForm({ 
  email, 
  firstName: initialFirstName, 
  lastName: initialLastName,
  memberSince,
  plan,
  includeInternational: initialInternational = false,
  selectedVerticals: initialVerticals
}: ProfileFormProps) {
  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [includeInternational, setIncludeInternational] = useState(initialInternational);
  const [selectedVerticals, setSelectedVerticals] = useState<Record<string, boolean>>(
    initialVerticals || {
      ai_tech: true,
      politics: true,
      finance: true,
      science: true,
      culture: true
    }
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const hasChanges = 
    firstName !== initialFirstName || 
    lastName !== initialLastName ||
    includeInternational !== initialInternational ||
    JSON.stringify(selectedVerticals) !== JSON.stringify(initialVerticals);

  const toggleVertical = (id: string) => {
    setSelectedVerticals(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);

    try {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();

      if (!user) return;

      const { error } = await supabase
        .from("users")
        .update({
          first_name: firstName.trim() || null,
          last_name: lastName.trim() || null,
          include_international: includeInternational,
          selected_verticals: selectedVerticals
        })
        .eq("id", user.id);

      if (error) throw error;

      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (error) {
      console.error("Failed to save profile:", error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Name fields */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="firstName">First Name</Label>
          <Input
            id="firstName"
            placeholder="Your first name"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            className="h-11"
          />
          <p className="text-xs text-muted-foreground">
            Used for your personalized podcast greeting
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="lastName">Last Name</Label>
          <Input
            id="lastName"
            placeholder="Your last name"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className="h-11"
          />
        </div>
      </div>

      {/* Verticals Selection */}
      <div className="space-y-3">
        <Label>News Verticals</Label>
        <p className="text-xs text-muted-foreground -mt-1">
          Select the topics you want in your daily podcast
        </p>
        <div className="grid gap-2">
          {VERTICALS.map((vertical) => {
            const Icon = vertical.icon;
            const isSelected = selectedVerticals[vertical.id];
            return (
              <button
                key={vertical.id}
                type="button"
                onClick={() => toggleVertical(vertical.id)}
                className={`flex items-center gap-3 p-3 rounded-xl border transition-all text-left ${
                  isSelected 
                    ? 'border-[#00F5FF]/50 bg-[#00F5FF]/5 dark:bg-[#00F5FF]/10' 
                    : 'border-border bg-secondary/30 opacity-60'
                }`}
              >
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                  isSelected ? 'bg-[#00F5FF]/20 text-[#00F5FF]' : 'bg-muted text-muted-foreground'
                }`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${isSelected ? '' : 'text-muted-foreground'}`}>
                    {vertical.name}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {vertical.description}
                  </p>
                </div>
                <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                  isSelected ? 'border-[#00F5FF] bg-[#00F5FF]' : 'border-muted-foreground/30'
                }`}>
                  {isSelected && <Check className="w-3 h-3 text-white" />}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* International Sources Toggle */}
      <div className="flex items-center justify-between p-4 rounded-xl bg-secondary/50 border border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
            <Globe className="w-5 h-5 text-blue-500" />
          </div>
          <div>
            <p className="font-medium">International Sources</p>
            <p className="text-sm text-muted-foreground">
              Include news from US, UK, Germany, Spain, Italy
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setIncludeInternational(!includeInternational)}
          className={`relative w-12 h-6 rounded-full transition-colors ${
            includeInternational ? 'bg-[#00F5FF]' : 'bg-muted'
          }`}
        >
          <span
            className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
              includeInternational ? 'left-7' : 'left-1'
            }`}
          />
        </button>
      </div>

      {includeInternational && (
        <div className="flex flex-wrap gap-2 px-1">
          {["🇫🇷 France", "🇺🇸 USA", "🇬🇧 UK", "🇩🇪 Germany", "🇪🇸 Spain", "🇮🇹 Italy"].map((country) => (
            <Badge key={country} variant="secondary" className="text-xs">
              {country}
            </Badge>
          ))}
        </div>
      )}

      {/* Save button */}
      {hasChanges && (
        <Button 
          onClick={handleSave} 
          disabled={saving}
          className="w-full h-11 bg-[#00F5FF] hover:bg-[#00D4E0] text-black"
        >
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Saving...
            </>
          ) : saved ? (
            <>
              <Check className="w-4 h-4 mr-2" />
              Saved!
            </>
          ) : (
            "Save Changes"
          )}
        </Button>
      )}

      {/* Read-only info */}
      <div className="pt-4 border-t space-y-3">
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Email</span>
          <span className="text-sm font-medium">{email}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Plan</span>
          <Badge variant="secondary" className="capitalize">
            {plan}
          </Badge>
        </div>
        {memberSince && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Member since</span>
            <span className="text-sm font-medium">
              {new Date(memberSince).toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
                year: "numeric"
              })}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
