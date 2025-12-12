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
  defaultDuration: number;
  voiceId: string;
}

const VOICES = [
  { id: "alloy", name: "Alloy", description: "Neutral and balanced" },
  { id: "echo", name: "Echo", description: "Warm and conversational" },
  { id: "fable", name: "Fable", description: "Expressive and dynamic" },
  { id: "onyx", name: "Onyx", description: "Deep and authoritative" },
  { id: "nova", name: "Nova", description: "Friendly and upbeat" },
  { id: "shimmer", name: "Shimmer", description: "Clear and refined" },
];

const DURATIONS = [
  { value: 5, label: "5 minutes", description: "Quick summary" },
  { value: 10, label: "10 minutes", description: "Brief digest" },
  { value: 15, label: "15 minutes", description: "Standard (recommended)" },
  { value: 20, label: "20 minutes", description: "Detailed overview" },
  { value: 30, label: "30 minutes", description: "In-depth coverage" },
];

export function SettingsForm({ defaultDuration, voiceId }: SettingsFormProps) {
  const [duration, setDuration] = useState(defaultDuration.toString());
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

    const { error } = await supabase
      .from("users")
      .update({
        default_duration: parseInt(duration),
        voice_id: voice,
      })
      .eq("id", user.id);

    if (error) {
      toast.error("Failed to save settings");
      setLoading(false);
      return;
    }

    toast.success("Settings saved!");
    setSaved(true);
    setLoading(false);
    setTimeout(() => setSaved(false), 2000);
  };

  const hasChanges = 
    parseInt(duration) !== defaultDuration || voice !== voiceId;

  return (
    <div className="space-y-6">
      {/* Duration */}
      <div className="space-y-2">
        <Label htmlFor="duration">Episode Duration</Label>
        <Select value={duration} onValueChange={setDuration}>
          <SelectTrigger id="duration" className="rounded-xl h-12">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="rounded-xl">
            {DURATIONS.map((d) => (
              <SelectItem 
                key={d.value} 
                value={d.value.toString()}
                className="rounded-lg"
              >
                <div className="flex flex-col">
                  <span>{d.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {d.description}
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Target length for your daily audio digest
        </p>
      </div>

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
          The voice used to narrate your podcast
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
