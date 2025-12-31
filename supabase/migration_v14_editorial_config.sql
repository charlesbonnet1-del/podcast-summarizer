-- Migration V14.5: Editorial Configuration in Database
-- All prompts and editorial intentions in Supabase, not code
-- ============================================

-- ============================================
-- 1. PROMPTS TABLE (System prompts for LLM)
-- ============================================

CREATE TABLE IF NOT EXISTS prompts (
    name TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    description TEXT,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Security: Only service_role can access (backend only)
ALTER TABLE prompts ENABLE ROW LEVEL SECURITY;

-- No public policies = no public access
-- Backend uses service_role key which bypasses RLS

COMMENT ON TABLE prompts IS 'System prompts for LLM generation. Only accessible by backend.';

-- ============================================
-- 2. ADD EDITORIAL COLUMNS TO TOPICS
-- ============================================

-- Add editorial_intention column if not exists
ALTER TABLE topics ADD COLUMN IF NOT EXISTS editorial_intention TEXT;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS transition_phrase TEXT;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS icon TEXT;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT true;
ALTER TABLE topics ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;

COMMENT ON COLUMN topics.editorial_intention IS 'Editorial angle for this topic - injected into LLM prompt';
COMMENT ON COLUMN topics.transition_phrase IS 'Audio transition phrase, e.g. "Passons à l intelligence artificielle"';

-- ============================================
-- 3. INSERT DEFAULT PROMPTS
-- ============================================

INSERT INTO prompts (name, content, description) VALUES 

('dialogue_cluster', 
'Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.
{topic_intention}
## SYNTHÈSE À TRANSFORMER EN DIALOGUE
**Sujet**: {theme}
**Accroche**: {hook}
**Thèse (fait principal)**: {thesis}
**Antithèse (nuances/contre-arguments)**: {antithesis}
**Données clés**: {key_data}
**Sources**: {sources}

## LES HÔTES
- [B] L''ANALYSTE (voix masculine) = Présente la THÈSE avec les données clés
- [A] LA SCEPTIQUE (voix féminine) = Apporte l''ANTITHÈSE et les nuances

## RÈGLES ABSOLUES
⚠️ PAS DE NOMS (pas de "Bob", "Alice", etc.)
⚠️ PAS DE TICS: "Tu vois", "Écoute", "Attends", "En fait", "C''est intéressant"
⚠️ STYLE DENSE: Chaque phrase apporte de l''information

## FORMAT
[B]
(expose la thèse avec données)

[A]
(apporte l''antithèse ou nuance)

## STRUCTURE OBLIGATOIRE
1. [B] ouvre avec l''accroche et la thèse principale + données
2. [A] challenge avec l''antithèse ou demande une précision
3. [B] répond avec des données complémentaires
4. [A] apporte une nuance finale ou perspective
5. [B] CONCLUT avec une synthèse

Minimum 6 répliques. Cite les sources naturellement.

## GÉNÈRE LE DIALOGUE ({word_count} mots):',
'Main prompt for cluster-based dialogue generation'),

('dialogue_segment',
'Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.
{topic_intention}
## LES HÔTES (Dialectique fonctionnelle, pas d''émotions simulées)
- [B] L''ANALYSTE (voix masculine) = Voix stable, factuelle. Il apporte les données brutes, les faits techniques et le potentiel futuriste.
- [A] LA SCEPTIQUE (voix féminine) = Voix incisive, inquisitrice. Elle challenge avec des objections, contre-arguments, ou questions percutantes.

## RÈGLES ABSOLUES SUR LE STYLE
⚠️ LES HÔTES NE S''APPELLENT JAMAIS PAR LEUR NOM. Pas de "Bob", "Alice", ou tout autre prénom.
⚠️ INTERDIT les tics de langage et formules creuses :
   - PAS DE: "Tu vois", "Écoute", "Attends", "En fait", "Justement"
   - PAS DE: "C''est une perspective intéressante", "Bonne question", "Effectivement", "Absolument"
   - PAS DE: phrases de transition artificielles ou compliments entre hôtes
Le dialogue doit être DIRECT et SUBSTANTIEL - chaque phrase apporte de l''information.

## STRUCTURE: [B] expose → [A] challenge ou met en perspective → [B] conclut

## FORMAT OBLIGATOIRE
Chaque réplique DOIT commencer par [A] ou [B] seul sur une ligne:

[B]
L''analyste expose les faits et données.

[A]
La sceptique challenge ou met en perspective.

## RÈGLES STRICTES
1. ALTERNER [B] et [A] - jamais deux [B] ou deux [A] de suite
2. [B] commence TOUJOURS en premier (il expose)
3. Minimum 6 répliques (3 de chaque)
4. Style DENSE et INFORMATIF - pas de remplissage
5. ⚠️ [A] LA SCEPTIQUE: Maximum 50% de ses répliques peuvent être des questions. Les autres doivent être des AFFIRMATIONS sceptiques, des contre-arguments, ou des mises en perspective.
6. ZÉRO liste, ZÉRO bullet points
7. CITE LA SOURCE dans la première réplique de [B]: {attribution_instruction}
8. INTERDIT: prénoms, didascalies, tics de langage, formules creuses
9. ⚠️ [B] TERMINE TOUJOURS LE DIALOGUE avec une synthèse factuelle ou une projection
10. La DERNIÈRE réplique est TOUJOURS [B] qui conclut - JAMAIS une question ou objection de [A]
11. ⚠️ SOURCING STRICT: Tu n''inventes AUCUNE information. Tout ce que tu écris DOIT être sourcable dans le contenu fourni.
{previous_segment_rule}

## STRUCTURE DU DIALOGUE
- Début: [B] expose les faits clés en citant la source
- Milieu: [A] challenge (affirmations sceptiques OU questions incisives), [B] répond avec des données
- Fin: [B] CONCLUT avec une synthèse factuelle ou une perspective future

## SOURCE
Titre: {title}
{source_label}
Contenu:
{content}
{previous_segment_context}

## GÉNÈRE LE DIALOGUE ({word_count} mots, style {style}) - [B] DOIT CONCLURE:',
'Prompt for single-article dialogue segments'),

('ephemeride',
'Tu es un scripteur de podcast. Génère une ÉPHÉMÉRIDE pour le {date}.

Trouve UN événement historique marquant qui s''est passé à cette date (n''importe quelle année).
L''événement doit être :
- Vérifiable et factuel
- Intéressant pour un public tech/science/économie
- Pas trop obscur mais pas non plus ultra-connu

## FORMAT DE SORTIE (JSON strict)
{{
  "year": 1969,
  "event": "Description courte de l''événement (1-2 phrases max)",
  "category": "tech|science|economics|politics|culture"
}}

Réponds UNIQUEMENT avec le JSON, rien d''autre.',
'Prompt for generating daily ephemeride')

ON CONFLICT (name) DO NOTHING;

-- ============================================
-- 4. UPDATE TOPICS WITH EDITORIAL INTENTIONS
-- ============================================

-- V1 TECH
UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (IA, Robotique, Hardware):
Qu''est-ce qui change dans ce que la machine peut faire ou comprendre aujourd''hui ?
Priorise le SAUT DE CAPACITÉ, qu''il soit technique, philosophique ou marketing.
Focus sur : nouvelles capabilities, ruptures de paradigme, implications concrètes, autonomie machine.',
    transition_phrase = 'Passons à l''intelligence artificielle.',
    icon = '🤖'
WHERE keyword = 'ia';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (CYBERSECURITY):
Quelles sont les nouvelles surfaces d''attaque et les défenses émergentes ?
Analyse les VULNÉRABILITÉS SYSTÉMIQUES et les réponses technologiques.
Focus sur : vecteurs d''attaque, zero-days, attribution, résilience infrastructure.',
    transition_phrase = 'Côté cybersécurité.',
    icon = '🔐'
WHERE keyword = 'cyber';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (QUANTUM, FUSION, MATÉRIAUX):
Où en est-on sur la courbe entre la théorie et l''impact réel ?
Retiens ce qui illustre un CHANGEMENT D''ÉCHELLE ou de PARADIGME.
Focus sur : franchissement de seuils, démonstrations expérimentales, timeline vers l''application.',
    transition_phrase = 'Direction les technologies de rupture.',
    icon = '⚛️'
WHERE keyword = 'deep_tech';

-- V2 SCIENCE
UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (HEALTH & LONGEVITY):
Quelles avancées permettent de REPOUSSER LES LIMITES BIOLOGIQUES ou d''optimiser le potentiel humain ?
Focus sur : recherche anti-âge, interventions validées, biomarqueurs, médecine de précision.',
    transition_phrase = 'En santé et longévité.',
    icon = '🧬'
WHERE keyword = 'health';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (SPACE):
Comment l''espace devient-il une EXTENSION DE NOTRE ÉCONOMIE et de notre champ d''exploration ?
Focus sur l''INFRASTRUCTURE et la LOGISTIQUE ORBITALE.
Analyse : lanceurs, constellations, économie spatiale, exploration.',
    transition_phrase = 'Cap sur l''espace.',
    icon = '🚀'
WHERE keyword = 'space';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (ENERGY):
Quelles sont les RUPTURES dans notre capacité à produire, stocker ou optimiser l''énergie ?
Focus sur l''EFFICIENCE et la SCALABILITÉ.
Analyse : nouvelles technologies, économie de l''énergie, transition énergétique.',
    transition_phrase = 'Sur le front de l''énergie.',
    icon = '⚡'
WHERE keyword = 'energy';

-- V3 ECONOMICS
UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (CRYPTO):
Comment la confiance et la valeur se déplacent-elles sur les réseaux ?
Analyse les INFRASTRUCTURES et les nouveaux MODÈLES DE PROPRIÉTÉ.
Focus sur : évolutions protocolaires, adoption institutionnelle, nouvelles primitives économiques.',
    transition_phrase = 'Dans l''univers crypto.',
    icon = '₿'
WHERE keyword = 'crypto';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (MACRO):
Quels sont les courants de fond (politiques, monétaires, intellectuels) qui déplacent les PLAQUES TECTONIQUES de l''économie mondiale ?
Focus sur : tendances structurelles, inflexions de politique, reconfigurations géoéconomiques.',
    transition_phrase = 'Regard sur la macro-économie.',
    icon = '🌍'
WHERE keyword = 'macro';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (DEALS - M&A, VC, IPO, MARCHÉS):
Quels MOUVEMENTS DE CAPITAL signalent les stratégies de long terme des acteurs ?
Analyse les LOGIQUES D''ACQUISITION, les signaux du marché VC, et les FORCES STRUCTURELLES qui modifient la valeur des entreprises.
Focus sur : levées de fonds, acquisitions stratégiques, IPO, consolidations sectorielles, valorisations, rotations de marché.',
    transition_phrase = 'Côté deals et marchés.',
    icon = '💼'
WHERE keyword = 'deals';

-- V4 WORLD
UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (ASIA):
Quels SIGNAUX (tech, politiques, sociaux) émanant d''Asie redéfinissent l''ÉQUILIBRE MONDIAL ?
Focus sur : innovations asiatiques, dynamiques géopolitiques, tendances culturelles et économiques.',
    transition_phrase = 'Regard vers l''Asie.',
    icon = '🌏'
WHERE keyword = 'asia';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (REGULATION):
Comment les RÈGLES DU JEU évoluent-elles ?
Analyse la norme comme une CONTRAINTE ou comme un LEVIER STRATÉGIQUE.
Focus sur : nouvelles législations, enforcement, arbitrages réglementaires.',
    transition_phrase = 'Sur le front réglementaire.',
    icon = '⚖️'
WHERE keyword = 'regulation';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (RESOURCES):
Quelles sont les TENSIONS ou les INNOVATIONS sur les flux de matières premières qui soutiennent le monde moderne ?
Focus sur : supply chains, métaux critiques, eau, agriculture, géopolitique des ressources.',
    transition_phrase = 'Parlons ressources.',
    icon = '🪨'
WHERE keyword = 'resources';

-- V5 INFLUENCE
UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (GUERRE DE L''INFORMATION):
Comment l''information est-elle utilisée comme une ARME ou un OUTIL DE PUISSANCE ?
Analyse les MÉTHODES DE DIFFUSION et de CONTRÔLE.
Focus sur : désinformation, influence operations, contrôle narratif, fact-checking.',
    transition_phrase = 'Dans la guerre de l''information.',
    icon = '📡'
WHERE keyword = 'info';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (MARCHÉS DE L''ATTENTION):
Comment la CAPTATION DE L''ATTENTION évolue-t-elle avec les plateformes ?
Focus sur les CHANGEMENTS DE MODÈLES MENTAUX des audiences.
Analyse : algorithmes, formats, comportements utilisateurs, économie de l''attention.',
    transition_phrase = 'Sur les marchés de l''attention.',
    icon = '👁️'
WHERE keyword = 'attention';

UPDATE topics SET 
    editorial_intention = '⚡ ANGLE ÉDITORIAL (STRATÉGIES DE PERSUASION):
Quelles sont les logiques (psychologiques, historiques, marketing) qui permettent de FORGER UNE OPINION ou d''ENTRAÎNER UNE ADHÉSION ?
Focus sur : techniques rhétoriques, nudges, design persuasif, propagande.',
    transition_phrase = 'Explorons la persuasion.',
    icon = '🎯'
WHERE keyword = 'persuasion';

-- ============================================
-- 5. TRIGGER FOR UPDATED_AT
-- ============================================

CREATE OR REPLACE FUNCTION update_prompts_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_prompts_timestamp ON prompts;
CREATE TRIGGER trigger_update_prompts_timestamp
    BEFORE UPDATE ON prompts
    FOR EACH ROW
    EXECUTE FUNCTION update_prompts_timestamp();

-- ============================================
-- 6. GRANT ACCESS TO SERVICE ROLE
-- ============================================

GRANT ALL ON prompts TO service_role;
GRANT SELECT ON prompts TO authenticated;  -- Read-only for frontend if needed

-- ============================================
-- VERIFICATION
-- ============================================

SELECT 'Prompts created:' as status, count(*) as count FROM prompts;
SELECT 'Topics with intentions:' as status, count(*) as count FROM topics WHERE editorial_intention IS NOT NULL;
