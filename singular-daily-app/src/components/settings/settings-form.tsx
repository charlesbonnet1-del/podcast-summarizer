"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, Check } from "lucide-react";
import { toast } from "sonner";

interface SettingsFormProps {
  voiceId: string;
}

const VOICES = [
  { id: "alloy", name: "Denise (Femme)", description: "Voix neutre et équilibrée" },
  { id: "echo", name: "Henri (Homme)", description: "Voix chaude et conversationnelle" },
  { id: "nova", name: "Nova (Femme)", description: "Voix amicale et dynamique" },
  { id: "onyx", name: "Onyx (Homme)", description: "Voix profonde et autoritaire" },
];

export function SettingsForm({ voiceId }: SettingsFormProps) {
  const [voice, setVoice] = useState(voiceId);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setLoading(true);
    setSaved(false);

    const supabase = createClient();
    const { data: { user } } = await supabase.auth.getUser();

    if (!user) {
      toast.error("Please sign in again");
      setLoading(false);
      return;
    }

    // Get current settings JSONB
    const { data: profile } = await supabase
      .from("users")
      .select("settings")
      .eq("id", user.id)
      .single();

    const currentSettings = profile?.settings || {};

    // Update voice_id in settings
    const { error } = await supabase
      .from("users")
      .update({
        settings: {
          ...currentSettings,
          voice_id: voice,
        }
      })
      .eq("id", user.id);

    if (error) {
      toast.error("Failed to save settings");
      setLoading(false);
      return;
    }

    toast.success("Voice preference saved!");
    setSaved(true);
    setLoading(false);
    setTimeout(() => setSaved(false), 2000);
  };

  const hasChanges = voice !== voiceId;

  return (
    <div className="space-y-6">
      {/* Voice */}
      <div className="space-y-2">
        <Label htmlFor="voice">AI Voice</Label>
        <Select value={voice} onValueChange={setVoice}>
          <SelectTrigger id="voice" className="rounded-xl h-12">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="rounded-xl">
            {VOICES.map((v) => (
              <SelectItem 
                key={v.id} 
                value={v.id}
                className="rounded-lg"
              >
                <div className="flex flex-col">
                  <span>{v.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {v.description}
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          La voix qui narrera votre podcast
        </p>
      </div>

      {/* Save Button */}
      <Button 
        onClick={handleSave}
        disabled={loading || !hasChanges}
        className="rounded-xl h-12 w-full sm:w-auto"
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
        ) : saved ? (
          <Check className="w-4 h-4 mr-2 text-green-500" />
        ) : null}
        {saved ? "Saved!" : "Save Changes"}
      </Button>
    </div>
  );
}
