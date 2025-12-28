"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Check } from "lucide-react";

interface ProfileFormProps {
  email: string;
  firstName: string;
  lastName: string;
  memberSince?: string;
  plan: string;
}

export function ProfileForm({ 
  email, 
  firstName: initialFirstName, 
  lastName: initialLastName,
  memberSince,
  plan
}: ProfileFormProps) {
  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const hasChanges = 
    firstName !== initialFirstName || 
    lastName !== initialLastName;

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
          last_name: lastName.trim() || null
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
          <Label htmlFor="firstName" className="font-display">Prénom</Label>
          <Input
            id="firstName"
            placeholder="Votre prénom"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            className="h-11"
          />
          <p className="text-xs text-muted-foreground">
            Utilisé pour le titre de votre podcast
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="lastName" className="font-display">Nom</Label>
          <Input
            id="lastName"
            placeholder="Votre nom"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className="h-11"
          />
        </div>
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
              Sauvegarde...
            </>
          ) : saved ? (
            <>
              <Check className="w-4 h-4 mr-2" />
              Sauvegardé !
            </>
          ) : (
            "Sauvegarder"
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
            <span className="text-sm text-muted-foreground">Membre depuis</span>
            <span className="text-sm font-display font-medium">
              {new Date(memberSince).toLocaleDateString("fr-FR", {
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
