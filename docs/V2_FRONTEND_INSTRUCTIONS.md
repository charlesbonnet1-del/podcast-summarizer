# KEERNEL V2 - Instructions Frontend

## 1. Suppression des boutons 20/30 minutes

Remplacer le sélecteur de durée par un toggle Flash/Digest.

### Fichier: `settings-form.tsx`

Remplacer:
```tsx
// ANCIEN CODE
<Select value={duration} onValueChange={setDuration}>
  <SelectTrigger>
    <SelectValue placeholder="Durée" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="5">5 minutes</SelectItem>
    <SelectItem value="10">10 minutes</SelectItem>
    <SelectItem value="20">20 minutes</SelectItem>
    <SelectItem value="30">30 minutes</SelectItem>
  </SelectContent>
</Select>
```

Par:
```tsx
// NOUVEAU CODE V2
<div className="flex gap-4">
  <button
    onClick={() => setFormat("flash")}
    className={`flex-1 p-4 rounded-xl border-2 transition-all ${
      format === "flash" 
        ? "border-[#00F5FF] bg-[#00F5FF]/10" 
        : "border-border hover:border-muted-foreground/50"
    }`}
  >
    <div className="font-medium">⚡ Flash</div>
    <div className="text-sm text-muted-foreground">~4 minutes</div>
    <div className="text-xs text-muted-foreground mt-1">Headlines essentielles</div>
  </button>
  
  <button
    onClick={() => setFormat("digest")}
    className={`flex-1 p-4 rounded-xl border-2 transition-all ${
      format === "digest" 
        ? "border-[#00F5FF] bg-[#00F5FF]/10" 
        : "border-border hover:border-muted-foreground/50"
    }`}
  >
    <div className="font-medium">📚 Digest</div>
    <div className="text-sm text-muted-foreground">~15 minutes</div>
    <div className="text-xs text-muted-foreground mt-1">Analyse approfondie</div>
  </button>
</div>
```

### Fichier: `generate-button.tsx`

Mettre à jour l'appel API pour envoyer le format:
```tsx
// AVANT
const response = await fetch(`${workerUrl}/generate`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ user_id: userId })
});

// APRÈS
const response = await fetch(`${workerUrl}/generate`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ 
    user_id: userId,
    format: userFormat  // "flash" ou "digest"
  })
});
```

## 2. Mise à jour de la colonne en base

Le frontend doit lire/écrire `preferred_format` au lieu de `default_duration`:

```tsx
// Lecture
const { data: user } = await supabase
  .from("users")
  .select("preferred_format")
  .eq("id", userId)
  .single();

const format = user?.preferred_format || "digest";

// Écriture
await supabase
  .from("users")
  .update({ preferred_format: newFormat })
  .eq("id", userId);
```

## 3. Tracking last_listened_at

Quand l'utilisateur joue un épisode, mettre à jour `last_listened_at`:

### Fichier: `audio-player.tsx` ou `player-pod.tsx`

```tsx
const handlePlay = async () => {
  // ... existing play logic
  
  // Track listening for Phantom User Guardrail
  try {
    await supabase
      .from("users")
      .update({ last_listened_at: new Date().toISOString() })
      .eq("id", userId);
  } catch (e) {
    console.warn("Failed to track listen:", e);
  }
};
```

## 4. Affichage du badge format sur les épisodes

Dans la liste des épisodes, afficher si c'est un Flash ou Digest:

```tsx
// Dans EpisodesList ou ShowNotes
<Badge variant={episode.audio_duration < 300 ? "default" : "secondary"}>
  {episode.audio_duration < 300 ? "⚡ Flash" : "📚 Digest"}
</Badge>
```

## 5. Migration des préférences existantes

Les utilisateurs avec `default_duration` seront migrés automatiquement:
- duration ≤ 5 → flash
- duration > 5 → digest

## 6. Récapitulatif des changements

| Avant (V1) | Après (V2) |
|------------|------------|
| `default_duration` (int) | `preferred_format` (string) |
| 5/10/20/30 minutes | flash (4min) / digest (15min) |
| Génération unique | Segments mutualisés (cache) |
| Tous les users | Phantom User Guardrail |

## 7. Types TypeScript à mettre à jour

```typescript
// types/database.ts
interface User {
  // ...existing fields
  preferred_format: "flash" | "digest";
  last_listened_at: string | null;
}
```
