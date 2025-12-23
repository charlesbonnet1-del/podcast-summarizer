# 🎙️ Podcast V5 - BULLETPROOF DIALOGUE

## Le problème
Le LLM ne génère pas toujours les tags [VOICE_A]/[VOICE_B] correctement.
Résultat: tout est lu avec une seule voix.

## La solution V5

### 1. Tags simplifiés
Au lieu de `[VOICE_A]` et `[VOICE_B]`, on utilise `[A]` et `[B]`.
Le LLM suit mieux ce format court.

### 2. Parsing ultra-robuste
Le code reconnaît TOUS ces formats:
- `[A]` / `[B]`
- `[VOICE_A]` / `[VOICE_B]`
- `Breeze:` / `Vale:`
- `Speaker A:` / `Speaker B:`
- Et plein d'autres...

### 3. Fallback automatique
Si AUCUN tag n'est trouvé → on split par paragraphes et on alterne.
Résultat: il y aura TOUJOURS un dialogue.

### 4. Logs explicites
Chaque étape affiche des logs avec ✅ ou ❌ pour debugger facilement.

## Déploiement

### 1. Remplace les fichiers sur ton worker (Fly.io/Render)
```
python-worker/stitcher.py
python-worker/generator.py
```

### 2. Vide le cache dans Supabase
```sql
DELETE FROM cached_intros;
DELETE FROM processed_segments;
DELETE FROM daily_ephemeride;
```

### 3. Redémarre ton worker
```bash
# Sur Fly.io
fly deploy

# Sur Render
# Push to GitHub, auto-deploy
```

### 4. Teste
Génère un podcast et regarde les logs.
Tu devrais voir:
```
✅ Groq client initialized
✅ OpenAI client initialized
📝 Generating script with Groq
📄 Script generated has_A=True has_B=True
✅ Valid dialogue script with 3 Vale segments
🎤 Segment 1/6: nova (A)
🎤 Segment 2/6: onyx (B)
🎤 Segment 3/6: nova (A)
...
```

## Vérification du dialogue

Dans les logs, cherche:
- `Voice A: X, Voice B: Y` → les deux doivent être > 0
- `🎤 Segment X: onyx (B)` → tu dois voir "onyx" pour Vale

Si tu vois seulement `nova (A)` → le problème persiste.
