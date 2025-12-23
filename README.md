# 🔧 Fix Podcast Dialogue - V3.1

## Problème identifié
Le podcast était généré uniquement avec la voix de Breeze (nova) sans Vale (onyx) car :
1. Le parsing des tags `[VOICE_B]` ne fonctionnait pas correctement
2. Les anciens segments étaient en cache
3. Le LLM générait parfois des formats de tags non reconnus

## Fichiers à remplacer

### 1. `python-worker/generator.py`
Améliorations :
- **Normalisation robuste** des tags : gère `[VOICE A]`, `[voice_a]`, `Breeze:`, etc.
- **Meilleurs logs** pour debugger le parsing
- **Validation stricte** : regénère si pas assez de tags des deux voix
- **Fallback** : si le parsing échoue, génère en voix unique au lieu de crasher

### 2. `python-worker/stitcher.py` (déjà fourni précédemment)
- Appelle `generate_dialogue_audio()` directement
- Génère des prompts qui forcent l'alternance des voix

## Instructions de déploiement

### Étape 1 : Remplacer les fichiers
```bash
# Dans ton repo local
cp generator.py python-worker/generator.py
cp stitcher.py python-worker/stitcher.py

# Commit et push
git add .
git commit -m "Fix: dialogue dual voice Breeze & Vale"
git push
```

### Étape 2 : VIDER LE CACHE (IMPORTANT!)
Exécute ce SQL dans Supabase :

```sql
-- Vider le cache des segments pour forcer la régénération
DELETE FROM processed_segments 
WHERE date = CURRENT_DATE 
   OR voice_format IS NULL 
   OR voice_format != 'dialogue_duo';

-- Vider le cache de l'éphéméride du jour
DELETE FROM daily_ephemeride 
WHERE date = CURRENT_DATE;

-- Optionnel : voir les segments en cache
SELECT date, segment_type, voice_format, title 
FROM processed_segments 
ORDER BY date DESC 
LIMIT 20;
```

### Étape 3 : Vérifier les variables d'environnement
Dans Vercel, assure-toi d'avoir :
- `OPENAI_API_KEY` - pour TTS (nova et onyx)
- `GROQ_API_KEY` - pour générer les scripts

### Étape 4 : Tester
1. Génère un nouveau podcast
2. Écoute pour vérifier l'alternance des voix
3. Regarde les logs pour voir :
   - `voice_a_count` et `voice_b_count` dans les logs de génération
   - `voice_a_segments` et `voice_b_segments` dans les logs de parsing

## Voix utilisées

| Hôte | Tag | Voix OpenAI | Personnalité |
|------|-----|-------------|--------------|
| **Breeze** | `[VOICE_A]` | `nova` | Expert pédagogue, factuel |
| **Vale** | `[VOICE_B]` | `onyx` | Challenger pragmatique, questions |

## Logs à surveiller

### ✅ Bon fonctionnement
```
INFO: Script generated voice_a_count=4 voice_b_count=3
INFO: Dialogue parsed total_segments=7 voice_a_segments=4 voice_b_segments=3
INFO: Generating segment 1/7 voice=nova voice_id=A
INFO: Generating segment 2/7 voice=onyx voice_id=B
```

### ❌ Problème
```
WARNING: Script missing sufficient voice tags voice_a=5 voice_b=0
ERROR: NO VOICE_B SEGMENTS FOUND
```

## Troubleshooting

### Si toujours pas de Vale après le fix :
1. Vérifie que le cache est bien vidé (SQL ci-dessus)
2. Regarde les logs Vercel pour voir le script brut généré
3. Vérifie que le nouveau code est bien déployé (hash du commit dans Vercel)
