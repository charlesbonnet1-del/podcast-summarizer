"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Check, Globe } from "lucide-react";

interface ProfileFormProps {
  email: string;
  firstName: string;
  lastName: string;
  memberSince?: string;
  plan: string;
  includeInternational?: boolean;
}

export function ProfileForm({ 
  email, 
  firstName: initialFirstName, 
  lastName: initialLastName,
  memberSince,
  plan,
  includeInternational: initialInternational = false
}: ProfileFormProps) {
  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [includeInternational, setIncludeInternational] = useState(initialInternational);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const hasChanges = 
    firstName !== initialFirstName || 
    lastName !== initialLastName ||
    includeInternational !== initialInternational;

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
          include_international: includeInternational
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
          <Label htmlFor="firstName" className="font-display">First Name</Label>
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
          <Label htmlFor="lastName" className="font-display">Last Name</Label>
          <Input
            id="lastName"
            placeholder="Your last name"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className="h-11"
          />
        </div>
      </div>

      {/* International Sources Toggle */}
      <div className="flex items-center justify-between p-4 rounded-xl bg-secondary/50 border border-border/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-card border border-brass/20 flex items-center justify-center">
            <Globe className="w-5 h-5 text-sand" />
          </div>
          <div>
            <p className="font-display font-medium">Sources Internationales</p>
            <p className="text-sm text-muted-foreground">
              Inclure des actualités internationales
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setIncludeInternational(!includeInternational)}
          className={`relative w-12 h-6 rounded-full transition-colors ${
            includeInternational ? 'bg-charcoal dark:bg-cream' : 'bg-muted'
          }`}
        >
          <span
            className={`absolute top-1 w-4 h-4 rounded-full transition-transform ${
              includeInternational 
                ? 'left-7 bg-cream dark:bg-charcoal' 
                : 'left-1 bg-white dark:bg-gray-400'
            }`}
          />
        </button>
      </div>

      {/* Save button */}
      {hasChanges && (
        <Button 
          onClick={handleSave} 
          disabled={saving}
          className="w-full h-11 btn-generate"
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
          <span className="text-sm font-medium font-mono">{email}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Plan</span>
          <Badge variant="secondary" className="capitalize font-display">
            {plan}
          </Badge>
        </div>
        {memberSince && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Member since</span>
            <span className="text-sm font-display font-medium">
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
