"""
Keernel Stitcher V13 - Cartesia TTS with Analyst & Skeptic

VOICE SYSTEM:
- Primary: Cartesia Sonic 3.0
  - [B] L'Analyste (Pierre) = Lead, exposes facts (voix masculine)
  - [A] La Sceptique (Helpful French Lady) = Challenger (voix féminine)
- Fallback: OpenAI TTS (nova/onyx)

V13 CHANGES:
- Inverted roles: [B] leads, [A] challenges
- No names in dialogue (just [A] and [B] markers)
- Skeptic limited to 50% questions max (rest are affirmations)
- Inventory-first architecture
"""
import os
import hashlib
import tempfile
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List
from urllib.parse import urlparse
import re

import structlog
from dotenv import load_dotenv

from db import supabase
from extractor import extract_content

load_dotenv()
log = structlog.get_logger()

# ============================================
# VOICE CONFIGURATION - CARTESIA
# ============================================

# Cartesia Voice IDs (Sonic 3.0)
# V14: French FRANCE accent voices (not Canadian)
#
# To find voice IDs, go to https://play.cartesia.ai/ and browse French voices
# Look for voices with "France" or "Parisian" in description
#
# [A] La Sceptique = Female French voice (France accent) - challenges, questions
# [B] L'Analyste = Male French voice (France accent) - leads and exposes facts
#
# DEFAULT VOICE IDs (update these in .env with your preferred voices):
# - CARTESIA_VOICE_ALICE: French female voice
# - CARTESIA_VOICE_BOB: French male voice
#
# Recommended French (France) voices from Cartesia library:
# - "French Narrator Lady" (female, France accent)
# - "French Narrator Man" (male, France accent)
# - Look for voices tagged with language "fr" and France/Parisian in description
#
CARTESIA_VOICE_ALICE = os.getenv("CARTESIA_VOICE_ALICE", "a3520a8f-226a-428d-9fcd-b0a4711a6829")  # [A] Skeptic - UPDATE THIS
CARTESIA_VOICE_BOB = os.getenv("CARTESIA_VOICE_BOB", "ab7c61f5-3daa-47dd-a23b-4ac0aac5f5c3")      # [B] Analyst - UPDATE THIS

# Fallback OpenAI voices (only used if Cartesia fails)
OPENAI_VOICE_ALICE = "nova"    # Female - [A] Skeptic
OPENAI_VOICE_BOB = "onyx"      # Male - [B] Analyst

# Model
CARTESIA_MODEL = "sonic-3"

# V14: Speed setting for Cartesia API
# Range: -1.0 (slowest) to 1.0 (fastest), 0.0 = normal
# We use 0.15 for slightly faster delivery (then apply 1.1x in post-processing)
CARTESIA_SPEED = 0.15  # Slightly faster than normal

# ============================================
# TTS CLIENTS
# ============================================

# Cartesia client
cartesia_client = None
try:
    from cartesia import Cartesia
    if os.getenv("CARTESIA_API_KEY"):
        cartesia_client = Cartesia(api_key=os.getenv("CARTESIA_API_KEY"))
        log.info("✅ Cartesia client initialized")
except ImportError:
    log.warning("⚠️ Cartesia SDK not installed, will use fallback")
except Exception as e:
    log.warning(f"⚠️ Cartesia init failed: {e}")

# OpenAI fallback client
openai_client = None
try:
    from openai import OpenAI
    if os.getenv("OPENAI_API_KEY"):
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        log.info("✅ OpenAI fallback client initialized")
except:
    pass

# Groq for script generation
groq_client = None
try:
    from groq import Groq
    if os.getenv("GROQ_API_KEY"):
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        log.info("✅ Groq client initialized")
except:
    pass

# Perplexity for content enrichment (Digest mode only)
perplexity_client = None
try:
    from openai import OpenAI as PerplexityClient
    if os.getenv("PERPLEXITY_API_KEY"):
        perplexity_client = PerplexityClient(
            api_key=os.getenv("PERPLEXITY_API_KEY"),
            base_url="https://api.perplexity.ai"
        )
        log.info("✅ Perplexity client initialized (for Digest enrichment)")
except:
    pass

# ============================================
# CONFIGURATION
# ============================================

WORDS_PER_MINUTE = 150
# V17: Segments are only served on day of creation, then never re-served
SEGMENT_CACHE_DAYS = 1  # Segments only eligible on creation day
# V17: Content queue sources stay eligible for 3 days for clustering
CONTENT_QUEUE_DAYS = 3
REPORT_RETENTION_DAYS = 365

# Format configurations - OPTIMIZED FOR DENSITY
# V17: Added segment duration constraints (no article limits)
FORMAT_CONFIG = {
    "flash": {
        "duration_minutes": 4,
        "total_words": 1000,           # Target ~4-5 min with segments
        "max_segments": 4,             # V17: 3-4 segments
        "min_segments": 3,
        # V17: Segment duration control (replaces article limits)
        "segment_target_seconds": 45,  # Target ~45s per segment
        "segment_max_seconds": 60,     # Hard max 60s (can stretch for major events)
        "segment_target_words": 110,   # ~45s at 150 WPM
        "segment_max_words": 150,      # ~60s at 150 WPM
        "style": "ultra-concis et percutant"
    },
    "digest": {
        "duration_minutes": 15,
        "total_words": 2800,
        "max_segments": 8,             # V17: 6-8 segments
        "min_segments": 6,
        # V17: Segment duration control (replaces article limits)
        "segment_target_seconds": 90,  # Target ~90s per segment
        "segment_max_seconds": 120,    # Hard max 120s (can stretch for major events)
        "segment_target_words": 225,   # ~90s at 150 WPM
        "segment_max_words": 300,      # ~120s at 150 WPM
        "style": "approfondi et analytique"
    }
}


def get_podcast_config(format_type: str = "flash") -> dict:
    """Get configuration for podcast format."""
    config = FORMAT_CONFIG.get(format_type, FORMAT_CONFIG["flash"]).copy()
    config["target_minutes"] = config.get("duration_minutes", 4)
    return config

# ============================================
# TRANSITIONS BETWEEN SEGMENTS (Cached)
# ============================================

# Map topic/vertical to transition phrases
# These will be cached as audio files
TRANSITION_PHRASES = {
    # V1 TECH
    "ia": "Passons à l'intelligence artificielle.",
    "cyber": "Côté cybersécurité.",
    "deep_tech": "Direction les technologies de rupture.",
    
    # V2 SCIENCE
    "health": "Parlons santé et longévité.",
    "space": "Direction l'espace.",
    "energy": "Côté énergie.",
    
    # V3 ECONOMICS
    "crypto": "Direction les cryptomonnaies.",
    "macro": "Côté macroéconomie.",
    "deals": "Les deals du moment.",
    
    # V4 WORLD
    "asia": "Cap sur l'Asie.",
    "regulation": "Côté régulation.",
    "resources": "Parlons ressources.",
    
    # V5 INFLUENCE
    "info": "Parlons guerre de l'information.",
    "attention": "Côté économie de l'attention.",
    "persuasion": "Les stratégies de persuasion.",
    
    # Generic fallbacks
    "general": "Passons au sujet suivant.",
    "default": "Continuons.",
}

# ============================================
# TOPIC EDITORIAL INTENTIONS (16 TOPICS)
# ============================================
# V1 TECH: ia, cyber, deep_tech
# V2 SCIENCE: health, space, energy
# V3 ECONOMICS: crypto, macro, deals
# V4 WORLD: asia, regulation, resources
# V5 INFLUENCE: info, attention, persuasion

TOPIC_INTENTIONS = {
    # V1 TECH
    "ia": """⚡ ANGLE ÉDITORIAL (IA, Robotique, Hardware):
Qu'est-ce qui change dans ce que la machine peut faire ou comprendre aujourd'hui ?
Priorise le SAUT DE CAPACITÉ, qu'il soit technique, philosophique ou marketing.
Focus sur : nouvelles capabilities, ruptures de paradigme, implications concrètes, autonomie machine.""",

    "cyber": """⚡ ANGLE ÉDITORIAL (CYBERSECURITY):
Quelles sont les nouvelles surfaces d'attaque et les défenses émergentes ?
Analyse les VULNÉRABILITÉS SYSTÉMIQUES et les réponses technologiques.
Focus sur : vecteurs d'attaque, zero-days, attribution, résilience infrastructure.""",

    "deep_tech": """⚡ ANGLE ÉDITORIAL (QUANTUM, FUSION, MATÉRIAUX):
Où en est-on sur la courbe entre la théorie et l'impact réel ?
Retiens ce qui illustre un CHANGEMENT D'ÉCHELLE ou de PARADIGME.
Focus sur : franchissement de seuils, démonstrations expérimentales, timeline vers l'application.""",

    # V2 SCIENCE
    "health": """⚡ ANGLE ÉDITORIAL (HEALTH & LONGEVITY):
Quelles avancées permettent de REPOUSSER LES LIMITES BIOLOGIQUES ou d'optimiser le potentiel humain ?
Focus sur : recherche anti-âge, interventions validées, biomarqueurs, médecine de précision.""",

    "space": """⚡ ANGLE ÉDITORIAL (SPACE):
Comment l'espace devient-il une EXTENSION DE NOTRE ÉCONOMIE et de notre champ d'exploration ?
Focus sur l'INFRASTRUCTURE et la LOGISTIQUE ORBITALE.
Analyse : lanceurs, constellations, économie spatiale, exploration.""",

    "energy": """⚡ ANGLE ÉDITORIAL (ENERGY):
Quelles sont les RUPTURES dans notre capacité à produire, stocker ou optimiser l'énergie ?
Focus sur l'EFFICIENCE et la SCALABILITÉ.
Analyse : nouvelles technologies, économie de l'énergie, transition énergétique.""",

    # V3 ECONOMICS
    "crypto": """⚡ ANGLE ÉDITORIAL (CRYPTO):
Comment la confiance et la valeur se déplacent-elles sur les réseaux ?
Analyse les INFRASTRUCTURES et les nouveaux MODÈLES DE PROPRIÉTÉ.
Focus sur : évolutions protocolaires, adoption institutionnelle, nouvelles primitives économiques.""",

    "macro": """⚡ ANGLE ÉDITORIAL (MACRO):
Quels sont les courants de fond (politiques, monétaires, intellectuels) qui déplacent les PLAQUES TECTONIQUES de l'économie mondiale ?
Focus sur : tendances structurelles, inflexions de politique, reconfigurations géoéconomiques.""",

    "deals": """⚡ ANGLE ÉDITORIAL (DEALS - M&A, VC, IPO, MARCHÉS):
Quels MOUVEMENTS DE CAPITAL signalent les stratégies de long terme des acteurs ?
Analyse les LOGIQUES D'ACQUISITION, les signaux du marché VC, et les FORCES STRUCTURELLES qui modifient la valeur des entreprises.
Focus sur : levées de fonds, acquisitions stratégiques, IPO, consolidations sectorielles, valorisations, rotations de marché.""",

    # V4 WORLD
    "asia": """⚡ ANGLE ÉDITORIAL (ASIA):
Quels SIGNAUX (tech, politiques, sociaux) émanant d'Asie redéfinissent l'ÉQUILIBRE MONDIAL ?
Focus sur : innovations asiatiques, dynamiques géopolitiques, tendances culturelles et économiques.""",

    "regulation": """⚡ ANGLE ÉDITORIAL (REGULATION):
Comment les RÈGLES DU JEU évoluent-elles ?
Analyse la norme comme une CONTRAINTE ou comme un LEVIER STRATÉGIQUE.
Focus sur : nouvelles législations, enforcement, arbitrages réglementaires.""",

    "resources": """⚡ ANGLE ÉDITORIAL (RESOURCES):
Quelles sont les TENSIONS ou les INNOVATIONS sur les flux de matières premières qui soutiennent le monde moderne ?
Focus sur : supply chains, métaux critiques, eau, agriculture, géopolitique des ressources.""",

    # V5 INFLUENCE
    "info": """⚡ ANGLE ÉDITORIAL (GUERRE DE L'INFORMATION):
Comment l'information est-elle utilisée comme une ARME ou un OUTIL DE PUISSANCE ?
Analyse les MÉTHODES DE DIFFUSION et de CONTRÔLE.
Focus sur : désinformation, influence operations, contrôle narratif, fact-checking.""",

    "attention": """⚡ ANGLE ÉDITORIAL (MARCHÉS DE L'ATTENTION):
Comment la CAPTATION DE L'ATTENTION évolue-t-elle avec les plateformes ?
Focus sur les CHANGEMENTS DE MODÈLES MENTAUX des audiences.
Analyse : algorithmes, formats, comportements utilisateurs, économie de l'attention.""",

    "persuasion": """⚡ ANGLE ÉDITORIAL (STRATÉGIES DE PERSUASION):
Quelles sont les logiques (psychologiques, historiques, marketing) qui permettent de FORGER UNE OPINION ou d'ENTRAÎNER UNE ADHÉSION ?
Focus sur : techniques rhétoriques, nudges, design persuasif, propagande.""",
}

# Valid topic slugs for validation
VALID_TOPICS = list(TOPIC_INTENTIONS.keys())

def get_topic_intention(topic_slug: str) -> str:
    """Get the editorial intention for a specific topic from database."""
    if not topic_slug:
        return ""
    
    # Try database first
    try:
        result = supabase.table("topics") \
            .select("editorial_intention") \
            .eq("keyword", topic_slug.lower()) \
            .single() \
            .execute()
        
        if result.data and result.data.get("editorial_intention"):
            intention = result.data["editorial_intention"]
            log.debug(f"📝 Using DB editorial intention for {topic_slug}")
            return f"\n{intention}\n"
    except Exception as e:
        log.debug(f"DB lookup failed for topic {topic_slug}: {e}")
    
    # Fallback to hardcoded (for backwards compatibility)
    intention = TOPIC_INTENTIONS.get(topic_slug.lower(), "")
    if intention:
        return f"\n{intention}\n"
    return ""


def get_transition_text(topic: str, vertical: str = None) -> str:
    """Get the transition phrase for a topic from database or fallback."""
    # Try database first
    if topic:
        try:
            result = supabase.table("topics") \
                .select("transition_phrase") \
                .eq("keyword", topic.lower()) \
                .single() \
                .execute()
            
            if result.data and result.data.get("transition_phrase"):
                log.debug(f"📝 Using DB transition for {topic}")
                return result.data["transition_phrase"]
        except Exception:
            pass
    
    # Fallback to hardcoded
    if topic and topic.lower() in TRANSITION_PHRASES:
        return TRANSITION_PHRASES[topic.lower()]
    
    if vertical and vertical.lower() in TRANSITION_PHRASES:
        return TRANSITION_PHRASES[vertical.lower()]
    
    return TRANSITION_PHRASES["default"]


def get_or_create_transition(topic: str, vertical: str = None) -> Optional[dict]:
    """
    Get or create a cached transition audio for a topic.
    Transitions are short (~2-3 seconds) and cached indefinitely.
    """
    transition_text = get_transition_text(topic, vertical)
    
    # Create cache key from text (normalized)
    import hashlib
    cache_key = hashlib.md5(transition_text.encode()).hexdigest()[:12]
    
    # Check cache
    try:
        cached = supabase.table("cached_transitions") \
            .select("audio_url, audio_duration, text") \
            .eq("cache_key", cache_key) \
            .single() \
            .execute()
        
        if cached.data and cached.data.get("audio_url"):
            log.debug(f"✅ Using cached transition: {transition_text}")
            return {
                "audio_url": cached.data["audio_url"],
                "duration": cached.data["audio_duration"],
                "text": cached.data["text"]
            }
    except:
        pass
    
    # Generate new transition
    log.info(f"🎵 Creating transition: {transition_text}")
    
    timestamp = datetime.now().strftime("%H%M%S%f")
    temp_path = os.path.join(tempfile.gettempdir(), f"transition_{cache_key}_{timestamp}.mp3")
    
    # Use Alice's voice for transitions
    if not generate_tts(transition_text, "alice", temp_path):
        log.warning(f"⚠️ Failed to generate transition audio")
        return None
    
    duration = get_audio_duration(temp_path)
    
    # Upload
    remote_path = f"transitions/{cache_key}.mp3"
    audio_url = upload_segment(temp_path, remote_path)
    
    if audio_url:
        # Cache it
        try:
            supabase.table("cached_transitions").upsert({
                "cache_key": cache_key,
                "text": transition_text,
                "topic": topic,
                "audio_url": audio_url,
                "audio_duration": duration
            }).execute()
            log.info(f"✅ Transition cached: {transition_text} ({duration}s)")
        except Exception as e:
            log.warning(f"⚠️ Failed to cache transition: {e}")
    
    # Clean up temp file
    try:
        os.remove(temp_path)
    except:
        pass
    
    return {
        "audio_url": audio_url,
        "duration": duration,
        "text": transition_text
    }

# ============================================
# DIALOGUE PROMPT - ALICE & BOB
# ============================================

# V14: Optimized prompt for pre-synthesized clusters (with thesis/antithesis)
DIALOGUE_CLUSTER_PROMPT = """Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.
{topic_intention}
## SYNTHÈSE À TRANSFORMER EN DIALOGUE
**Sujet**: {theme}
**Accroche**: {hook}
**Thèse (fait principal)**: {thesis}
**Antithèse (nuances/contre-arguments)**: {antithesis}
**Données clés**: {key_data}
**Sources**: {sources}

## LES HÔTES
- [B] L'ANALYSTE (voix masculine) = Présente la THÈSE avec les données clés
- [A] LA SCEPTIQUE (voix féminine) = Apporte l'ANTITHÈSE et les nuances

## RÈGLES ABSOLUES
⚠️ PAS DE NOMS (pas de "Bob", "Alice", etc.)
⚠️ PAS DE TICS: "Tu vois", "Écoute", "Attends", "En fait", "C'est intéressant"
⚠️ STYLE DENSE: Chaque phrase apporte de l'information

## FORMAT
[B]
(expose la thèse avec données)

[A]
(apporte l'antithèse ou nuance)

## STRUCTURE OBLIGATOIRE
1. [B] ouvre avec l'accroche et la thèse principale + données
2. [A] challenge avec l'antithèse ou demande une précision
3. [B] répond avec des données complémentaires
4. [A] apporte une nuance finale ou perspective
5. [B] CONCLUT avec une synthèse

Minimum 6 répliques. Cite les sources naturellement.

## GÉNÈRE LE DIALOGUE ({word_count} mots):"""


def get_prompt_from_db(prompt_name: str, default: str) -> str:
    """
    Fetch prompt from database if available, otherwise use default.
    
    Create a table 'prompts' in Supabase:
    CREATE TABLE prompts (
        name TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT NOW()
    );
    
    INSERT INTO prompts (name, content) VALUES ('dialogue_cluster', '...');
    INSERT INTO prompts (name, content) VALUES ('dialogue_segment', '...');
    """
    try:
        result = supabase.table("prompts").select("content").eq("name", prompt_name).single().execute()
        if result.data and result.data.get("content"):
            log.info(f"📝 Using custom prompt from DB: {prompt_name}")
            return result.data["content"]
    except Exception as e:
        # Table doesn't exist or no custom prompt - use default
        pass
    return default


# ============================================
# DEPRECATED PROMPTS - REMOVED IN V14.5
# ============================================
# DIALOGUE_SEGMENT_PROMPT - Removed: Use dialogue_cluster instead (all content goes through Perplexity synthesis)
# 
# Only DIALOGUE_CLUSTER_PROMPT remains for dialogue generation

# Fallback for code that still references removed prompts
DIALOGUE_SEGMENT_PROMPT = DIALOGUE_CLUSTER_PROMPT  # Redirect to cluster prompt

# Multi-source prompt - kept because it uses different variables than cluster
DIALOGUE_MULTI_SOURCE_PROMPT = """Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.
{topic_intention}

## SOURCES ({source_count} articles sur ce sujet)
{sources_content}

## LES HÔTES
- [B] L'ANALYSTE (voix masculine) = Synthétise les informations des différentes sources
- [A] LA SCEPTIQUE (voix féminine) = Challenge et met en perspective

## RÈGLES ABSOLUES
⚠️ PAS DE NOMS (pas de "Bob", "Alice", etc.)
⚠️ PAS DE TICS: "Tu vois", "Écoute", "Attends", "En fait", "C'est intéressant"
⚠️ STYLE DENSE: Chaque phrase apporte de l'information
⚠️ CITE LES SOURCES: "Selon [source]...", "D'après [source]..."

## FORMAT
[B]
(synthétise les sources avec données)

[A]
(challenge ou met en perspective)

## STRUCTURE OBLIGATOIRE
1. [B] ouvre en synthétisant les faits clés des sources
2. [A] challenge ou demande une précision
3. [B] répond avec des données complémentaires
4. [A] apporte une nuance finale
5. [B] CONCLUT avec une synthèse

Minimum 6 répliques. {previous_segment_rule}
{previous_segment_context}

## GÉNÈRE LE DIALOGUE ({word_count} mots, style {style}):"""

# Rule to add when there's a previous segment (still used)
PREVIOUS_SEGMENT_RULE = """⚠️ NON-RÉPÉTITION: Un segment récent sur ce sujet existe. NE RÉPÈTE PAS les informations déjà couvertes. Apporte des NOUVELLES informations ou un nouvel angle."""

# Context block for previous segment (still used)
PREVIOUS_SEGMENT_CONTEXT = """

## SEGMENT PRÉCÉDENT SUR CE SUJET (ne pas répéter)
Titre précédent: {prev_title}
Ce qui a été couvert:
{prev_script}

⚠️ NE RÉPÈTE PAS ces informations. Apporte du NOUVEAU."""

# ============================================
# DIGEST EXTRACTION PROMPT
# ============================================

DIGEST_EXTRACTION_PROMPT = """Analyse cet article et extrais les métadonnées suivantes en JSON.

## ARTICLE
Titre: {title}
Source: {source_name}
URL: {url}
Contenu:
{content}

## FORMAT DE RÉPONSE (JSON uniquement, pas de texte avant/après)
{{
  "author": "Nom de l'auteur si mentionné, sinon null",
  "published_date": "YYYY-MM-DD si mentionné, sinon null",
  "summary": "Résumé factuel en 2-3 phrases (max 150 mots)",
  "key_insights": ["Insight 1", "Insight 2", "Insight 3"],
  "historical_context": "Événement historique lié ou contexte important si pertinent, sinon null"
}}

## RÈGLES
- key_insights: 2-4 points clés, phrases courtes et percutantes
- summary: factuel, informatif, pas de jugement
- historical_context: uniquement si vraiment pertinent (anniversaire, précédent historique, etc.)
- Réponds UNIQUEMENT avec le JSON, rien d'autre

JSON:"""


def extract_article_digest(
    title: str,
    content: str,
    source_name: str,
    url: str
) -> Optional[dict]:
    """Extract structured digest from article using Groq/Llama."""
    
    if not groq_client:
        log.warning("❌ Groq client not available for digest extraction")
        return None
    
    try:
        prompt = DIGEST_EXTRACTION_PROMPT.format(
            title=title,
            source_name=source_name,
            url=url,
            content=content[:4000]  # Limit content size
        )
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Lower temp for more consistent extraction
            max_tokens=500
        )
        
        json_text = response.choices[0].message.content.strip()
        
        # Clean up response - remove markdown code blocks if present
        if json_text.startswith("```"):
            json_text = json_text.split("```")[1]
            if json_text.startswith("json"):
                json_text = json_text[4:]
        json_text = json_text.strip()
        
        import json
        digest = json.loads(json_text)
        
        log.info(f"✅ Digest extracted: {len(digest.get('key_insights', []))} insights")
        return digest
        
    except Exception as e:
        log.error(f"❌ Digest extraction failed: {e}")
        return None


def save_episode_digest(
    episode_id: str,
    source_url: str,
    title: str,
    digest: dict
) -> bool:
    """Save extracted digest to episode_digests table."""
    
    try:
        data = {
            "episode_id": episode_id,
            "source_url": source_url,
            "title": title,
            "author": digest.get("author"),
            "published_date": digest.get("published_date"),
            "summary": digest.get("summary"),
            "key_insights": digest.get("key_insights", []),
            "historical_context": digest.get("historical_context")
        }
        
        result = supabase.table("episode_digests").insert(data).execute()
        
        if result.data:
            log.info(f"✅ Digest saved for: {title[:40]}...")
            return True
        return False
        
    except Exception as e:
        log.error(f"❌ Failed to save digest: {e}")
        return False


# ============================================
# TTS GENERATION - CARTESIA PRIMARY
# ============================================

def generate_tts_cartesia(text: str, voice_id: str, output_path: str) -> bool:
    """
    Generate TTS using Cartesia Sonic
    
    V14 FIX: 
    - Speed: Only post-processing 1.1x (not API speed + post)
    - Emotion: ["positivity:high", "curiosity:high"] for engaged tone
    - No API speed parameter (was causing double speedup)
    """
    if not cartesia_client:
        return False
    
    try:
        log.info(f"🎤 Cartesia TTS: {len(text)} chars, voice={voice_id[:8]}...")
        
        # V14 FIX: No speed in API - only apply 1.1x in post-processing
        audio_bytes = b""
        for chunk in cartesia_client.tts.bytes(
            model_id=CARTESIA_MODEL,
            transcript=text,
            voice={
                "mode": "id", 
                "id": voice_id,
                # V14: Emotion controls only (no speed here - applied in post)
                "__experimental_controls": {
                    "emotion": ["positivity:high", "curiosity:high"]  # Engaged, enthusiastic
                }
            },
            language="fr",
            output_format={
                "container": "mp3",
                "bit_rate": 192000,
                "sample_rate": 44100
            }
        ):
            audio_bytes += chunk
        
        # Save to file
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        
        # V14.5: No speed increase - natural pace
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(output_path)
            # V14.5: Remove speedup, only increase volume
            louder_audio = audio + 3.5
            louder_audio.export(output_path, format="mp3", bitrate="192k")
            log.info(f"✅ Cartesia audio processed: speed=1.0x (natural), volume=+3.5dB")
        except Exception as e:
            log.warning(f"⚠️ Post-processing skipped: {e}")
        
        log.info(f"✅ Cartesia audio saved: {len(audio_bytes)} bytes")
        return True
        
    except Exception as e:
        log.error(f"❌ Cartesia TTS failed: {e}")
        # V14: Try with simpler params if advanced features fail
        try:
            log.info("🔄 Retrying Cartesia TTS with basic params...")
            audio_bytes = b""
            for chunk in cartesia_client.tts.bytes(
                model_id=CARTESIA_MODEL,
                transcript=text,
                voice={"mode": "id", "id": voice_id},
                language="fr",
                output_format={"container": "mp3", "bit_rate": 192000, "sample_rate": 44100}
            ):
                audio_bytes += chunk
            
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            
            # V14.5: No speedup in fallback either
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_mp3(output_path)
                louder_audio = audio + 3.5  # Only volume, no speed
                louder_audio.export(output_path, format="mp3", bitrate="192k")
            except:
                pass
            
            log.info(f"✅ Cartesia TTS (basic mode) saved: {len(audio_bytes)} bytes")
            return True
        except Exception as e2:
            log.error(f"❌ Cartesia TTS basic mode also failed: {e2}")
            return False


def generate_tts_openai(text: str, voice: str, output_path: str) -> bool:
    """Fallback: Generate TTS using OpenAI"""
    if not openai_client:
        return False
    
    try:
        log.info(f"🎤 OpenAI TTS (fallback): {len(text)} chars, voice={voice}")
        
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
            speed=1.0
        )
        response.stream_to_file(output_path)
        return True
        
    except Exception as e:
        log.error(f"❌ OpenAI TTS failed: {e}")
        return False


def generate_tts(text: str, voice_type: str, output_path: str) -> bool:
    """
    Generate TTS with Cartesia (primary) or OpenAI (fallback).
    
    V13: Applies phonetic sanitization before TTS to ensure proper pronunciation.
    
    voice_type: "alice" or "bob"
    """
    # V13: Sanitize text for proper pronunciation
    from phonetic_sanitizer import sanitize_for_tts
    sanitized_text = sanitize_for_tts(text)
    
    if sanitized_text != text:
        log.debug("🔤 Text sanitized for TTS", 
                  original_len=len(text), 
                  sanitized_len=len(sanitized_text))
    
    # Map voice type to voice IDs
    if voice_type == "alice":
        cartesia_voice = CARTESIA_VOICE_ALICE
        openai_voice = OPENAI_VOICE_ALICE
    else:  # bob
        cartesia_voice = CARTESIA_VOICE_BOB
        openai_voice = OPENAI_VOICE_BOB
    
    # Try Cartesia first (with sanitized text)
    if cartesia_client and generate_tts_cartesia(sanitized_text, cartesia_voice, output_path):
        return True
    
    # Fallback to OpenAI (with sanitized text)
    log.warning(f"⚠️ Falling back to OpenAI TTS")
    return generate_tts_openai(sanitized_text, openai_voice, output_path)


def get_audio_duration(path: str) -> int:
    """Get audio duration in seconds."""
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_mp3(path)) // 1000
    except:
        return 0


# ============================================
# DIALOGUE PARSING - ALICE [A] / BOB [B]
# ============================================

def clean_stage_directions(text: str) -> str:
    """Remove stage directions like 'Alice répond', 'Bob questionne', etc."""
    patterns_to_remove = [
        r'^Alice\s+(répond|explique|continue|ajoute|conclut|questionne|demande|s\'exclame|lance|commente)\s*[:\.\,]?\s*',
        r'^Bob\s+(répond|explique|continue|ajoute|conclut|questionne|demande|s\'exclame|lance|commente)\s*[:\.\,]?\s*',
        r'^\(Alice[^)]*\)\s*',
        r'^\(Bob[^)]*\)\s*',
        r'^\*Alice[^*]*\*\s*',
        r'^\*Bob[^*]*\*\s*',
        r'^Alice\s*:\s*',
        r'^Bob\s*:\s*',
    ]
    
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\(il\s+[^)]+\)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\(elle\s+[^)]+\)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\(en\s+[^)]+\)', '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()


def parse_dialogue_to_segments(script: str) -> list[dict]:
    """Parse dialogue script into voice segments with GUARANTEED alternation."""
    if not script:
        return []
    
    # Normalize tags
    normalized = script
    replacements = [
        (r'\[VOICE_A\]', '\n[A]\n'),
        (r'\[VOICE_B\]', '\n[B]\n'),
        (r'Alice\s*:', '\n[A]\n'),
        (r'Bob\s*:', '\n[B]\n'),
        (r'\*\*Alice\*\*', '\n[A]\n'),
        (r'\*\*Bob\*\*', '\n[B]\n'),
        (r'Breeze\s*:', '\n[A]\n'),  # Legacy support
        (r'Vale\s*:', '\n[B]\n'),    # Legacy support
    ]
    
    for pattern, repl in replacements:
        normalized = re.sub(pattern, repl, normalized, flags=re.IGNORECASE)
    
    # Parse [A] and [B] tags
    segments = []
    pattern = r'\[([AB])\]'
    parts = re.split(pattern, normalized)
    
    i = 1
    while i < len(parts) - 1:
        voice = parts[i].upper()
        text = parts[i + 1].strip()
        text = re.sub(r'^\s*\n+', '', text).strip()
        
        # Clean stage directions
        text = clean_stage_directions(text)
        
        if voice in ('A', 'B') and text and len(text) > 10:
            segments.append({'voice': voice, 'text': text})
        i += 2
    
    # FALLBACK: Split by paragraphs
    if not segments:
        log.warning("⚠️ No voice tags found, using paragraph fallback")
        paragraphs = [p.strip() for p in script.split('\n\n') if p.strip() and len(p.strip()) > 20]
        if not paragraphs:
            paragraphs = [p.strip() for p in script.split('\n') if p.strip() and len(p.strip()) > 20]
        
        for i, para in enumerate(paragraphs[:10]):
            cleaned = clean_stage_directions(para)
            if cleaned and len(cleaned) > 10:
                segments.append({'voice': 'A' if i % 2 == 0 else 'B', 'text': cleaned})
    
    # FORCE alternation - Alice always starts
    for i in range(len(segments)):
        segments[i]['voice'] = 'A' if i % 2 == 0 else 'B'
    
    return segments


def generate_dialogue_audio(script: str, output_path: str) -> str | None:
    """Generate dialogue audio with Alice [A] and Bob [B] voices."""
    
    segments = parse_dialogue_to_segments(script)
    
    if not segments:
        log.error("❌ No segments!")
        return None
    
    alice_count = sum(1 for s in segments if s['voice'] == 'A')
    bob_count = sum(1 for s in segments if s['voice'] == 'B')
    log.info(f"🎙️ Generating dialogue: {len(segments)} segments, Alice={alice_count}, Bob={bob_count}")
    
    audio_files = []
    
    for i, seg in enumerate(segments):
        voice_type = "alice" if seg['voice'] == 'A' else "bob"
        seg_path = output_path.replace('.mp3', f'_seg{i:03d}.mp3')
        
        log.info(f"🎤 Segment {i+1}/{len(segments)}: {voice_type.upper()}")
        
        if generate_tts(seg['text'], voice_type, seg_path):
            audio_files.append(seg_path)
    
    if not audio_files:
        return None
    
    # Combine with pauses
    try:
        from pydub import AudioSegment
        
        combined = AudioSegment.empty()
        pause = AudioSegment.silent(duration=300)  # 300ms between turns
        
        for i, path in enumerate(audio_files):
            combined += AudioSegment.from_mp3(path)
            if i < len(audio_files) - 1:
                combined += pause
        
        combined.export(output_path, format='mp3', bitrate='192k')
        
        # Cleanup
        for f in audio_files:
            try:
                os.remove(f)
            except:
                pass
        
        return output_path
        
    except Exception as e:
        log.error(f"❌ Combine failed: {e}")
        return None


# ============================================
# PERPLEXITY ENRICHMENT (DIGEST MODE ONLY)
# ============================================

ENRICHMENT_PROMPT = """À partir de cet article, fournis un contexte enrichi pour un podcast tech/actualité approfondi.

ARTICLE:
Titre: {title}
Source: {source}
Contenu: {content}

FOURNIS EN 250 MOTS MAX:
1. Contexte historique ou évolution récente du sujet
2. Comparaison avec la concurrence ou autres acteurs
3. Réactions du marché, analystes ou experts
4. Enjeux et implications concrètes
5. Ce que ça change pour le public/consommateurs

Sois factuel, concis et cite tes sources entre crochets [source]."""


def enrich_content_with_perplexity(
    title: str,
    content: str,
    source_name: str
) -> Optional[str]:
    """
    Enrich article content using Perplexity's web search.
    Only used for Digest format (15 min) to add depth.
    Returns enriched context or None if unavailable.
    """
    if not perplexity_client:
        log.debug("Perplexity not available, skipping enrichment")
        return None
    
    try:
        prompt = ENRICHMENT_PROMPT.format(
            title=title,
            source=source_name,
            content=content[:2000]  # Limit input size
        )
        
        response = perplexity_client.chat.completions.create(
            model="sonar",  # Perplexity model with web search
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        
        enriched = response.choices[0].message.content.strip()
        log.info(f"✅ Perplexity enrichment: +{len(enriched.split())} words context")
        return enriched
        
    except Exception as e:
        log.warning(f"⚠️ Perplexity enrichment failed: {e}")
        return None


def inject_premium_sources_to_deals(user_id: str) -> int:
    """
    V14 Premium Module: Inject articles from high-score sources (>90) into deals category.
    
    Sources with GSheet score > 90 are considered premium and their content
    is automatically classified into the deals topic for priority processing.
    
    Returns number of articles injected.
    """
    if not supabase:
        return 0
    
    try:
        # Get premium sources (score > 90)
        from source_scoring import STATUS_ACTIVE
        
        premium_sources = supabase.table("source_performance") \
            .select("source_domain, gsheet_score, dynamic_score") \
            .gte("gsheet_score", 90) \
            .eq("status", STATUS_ACTIVE) \
            .execute()
        
        if not premium_sources.data:
            log.debug("No premium sources found")
            return 0
        
        premium_domains = [s["source_domain"] for s in premium_sources.data]
        log.info(f"🌟 Found {len(premium_domains)} premium sources (score > 90)")
        
        # Get pending articles from premium sources not yet in deals
        articles = supabase.table("content_queue") \
            .select("id, title, source_name, keyword") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .in_("source_name", premium_domains) \
            .neq("keyword", "deals") \
            .limit(10) \
            .execute()
        
        if not articles.data:
            return 0
        
        # Inject into deals with deal_type classification
        injected = 0
        for article in articles.data:
            try:
                # Classify deal type based on title
                deal_type = classify_deal_type(article.get("title", ""))
                
                supabase.table("content_queue").update({
                    "keyword": "deals",
                    "deal_type": deal_type or "MARKET",
                    "priority": "high",
                    "premium_source": True
                }).eq("id", article["id"]).execute()
                
                injected += 1
                log.debug(f"🌟 Premium inject: {article['title'][:50]}... → deals/{deal_type}")
                
            except Exception as e:
                log.warning(f"⚠️ Failed to inject premium article: {e}")
        
        if injected > 0:
            log.info(f"🌟 Injected {injected} premium source articles into deals")
        
        return injected
        
    except ImportError:
        log.debug("source_scoring not available")
        return 0
    except Exception as e:
        log.warning(f"⚠️ Premium injection failed: {e}")
        return 0


def classify_deal_type(title: str) -> Optional[str]:
    """
    Classify deal type based on title keywords.
    
    Returns: MA, FUNDRAISING, IPO, PARTNERSHIP, MARKET, or None
    """
    if not title:
        return None
    
    title_lower = title.lower()
    
    # M&A keywords
    if any(kw in title_lower for kw in ["acquisition", "rachat", "fusion", "merger", "m&a", "achète", "rachète"]):
        return "MA"
    
    # Fundraising keywords
    if any(kw in title_lower for kw in ["levée", "fundrais", "série a", "série b", "série c", "seed", "investissement", "vc", "venture"]):
        return "FUNDRAISING"
    
    # IPO keywords
    if any(kw in title_lower for kw in ["ipo", "introduction en bourse", "entrée en bourse", "cotation"]):
        return "IPO"
    
    # Partnership keywords
    if any(kw in title_lower for kw in ["partenariat", "partnership", "alliance", "collaboration", "accord"]):
        return "PARTNERSHIP"
    
    # Market keywords
    if any(kw in title_lower for kw in ["bourse", "action", "cac", "dow", "nasdaq", "valorisation", "cours"]):
        return "MARKET"
    
    return None


# ============================================
# SCRIPT GENERATION
# ============================================

def generate_cluster_dialogue_script(
    cluster_item: dict,
    word_count: int = 200,
    max_word_count: int = None,
    style: str = "dynamique",
    topic_slug: str = None,
    user_id: str = None
) -> Optional[str]:
    """
    V14: Generate DIALOGUE script from a pre-synthesized cluster.
    Uses the thesis/antithesis structure for better dialogue.
    
    V17: Added max_word_count for flexible duration control.
    """
    # V17: Default max to target + 30% if not specified
    if max_word_count is None:
        max_word_count = int(word_count * 1.3)
    
    if not groq_client:
        log.error("Groq client not available")
        return None
    
    # Check if this is a cluster item
    if not cluster_item.get("_from_cluster"):
        # Fall back to regular generation
        return generate_dialogue_segment_script(
            title=cluster_item.get("title", ""),
            content=cluster_item.get("content", ""),
            source_name=cluster_item.get("source_name", ""),
            word_count=word_count,
            max_word_count=max_word_count,
            style=style,
            topic_slug=topic_slug,
            user_id=user_id
        )
    
    try:
        # Extract cluster synthesis
        theme = cluster_item.get("title", cluster_item.get("theme", "Sujet"))
        hook = cluster_item.get("hook", "")
        thesis = cluster_item.get("thesis", cluster_item.get("content", ""))
        antithesis = cluster_item.get("antithesis", "")
        key_data = cluster_item.get("key_data", [])
        sources = cluster_item.get("source_name", "Multiple sources")
        
        # Format key data as string
        key_data_str = ", ".join(key_data) if key_data else "Non disponible"
        
        # Get editorial intention for this topic
        topic_intention = get_topic_intention(topic_slug) if topic_slug else ""
        
        # Get prompt (from DB if available, otherwise default)
        prompt_template = get_prompt_from_db("dialogue_cluster", DIALOGUE_CLUSTER_PROMPT)
        
        prompt = prompt_template.format(
            word_count=word_count,
            style=style,
            theme=theme,
            hook=hook if hook else theme,
            thesis=thesis,
            antithesis=antithesis if antithesis else "À explorer dans le dialogue",
            key_data=key_data_str,
            sources=sources,
            topic_intention=topic_intention
        )
        
        log.info(f"🎯 Generating cluster dialogue: {theme[:50]}...")
        
        for attempt in range(3):
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=word_count * 3
            )
            
            script = response.choices[0].message.content.strip()
            
            # Validate dialogue format
            has_tags = '[A]' in script or '[B]' in script
            if has_tags:
                script = ensure_bob_conclusion(script)
                log.info(f"✅ Cluster dialogue generated ({len(script)} chars)")
                return script
            
            log.warning(f"⚠️ Cluster dialogue attempt {attempt+1} missing tags, retrying...")
        
        log.error("❌ Failed to generate valid cluster dialogue after 3 attempts")
        return None
        
    except Exception as e:
        log.error(f"❌ Cluster dialogue generation failed: {e}")
        return None


def generate_dialogue_segment_script(
    title: str,
    content: str,
    source_name: str,
    word_count: int = 200,
    max_word_count: int = None,
    style: str = "dynamique",
    use_enrichment: bool = False,
    topic_slug: str = None,
    user_id: str = None,
    source_type: str = None,
    metadata: dict = None
) -> Optional[str]:
    """
    Generate DIALOGUE script for a segment.
    
    V17: Added max_word_count for flexible duration control.
    Target word_count for normal segments, can expand to max_word_count for major events.
    
    Args:
        word_count: Target word count (~target duration)
        max_word_count: Maximum word count (can stretch for important content)
        use_enrichment: If True, uses Perplexity to add context (for Digest mode)
        topic_slug: Topic identifier to fetch previous segment
        user_id: User ID for context (optional)
        source_type: Type of source ("youtube_video", "article", etc.)
        metadata: Additional metadata (attribution_prefix for YouTube)
    """
    # V17: Default max to target + 30% if not specified
    if max_word_count is None:
        max_word_count = int(word_count * 1.3)
    
    if not groq_client:
        log.error("Groq client not available")
        return None
    
    try:
        # Enrich content with Perplexity for Digest mode
        enriched_context = None
        if use_enrichment:
            enriched_context = enrich_content_with_perplexity(title, content, source_name)
        
        # Build content for prompt
        if enriched_context:
            full_content = f"""ARTICLE PRINCIPAL:
{content[:3000]}

CONTEXTE ENRICHI (sources additionnelles):
{enriched_context}"""
        else:
            full_content = content[:4000]
        
        # V12: Get previous segment for this topic to avoid repetition
        previous_segment = None
        previous_segment_rule = ""
        previous_segment_context = ""
        
        if topic_slug:
            previous_segment = get_previous_segment_for_topic(topic_slug, user_id)
            
            if previous_segment and previous_segment.get("script_text"):
                previous_segment_rule = PREVIOUS_SEGMENT_RULE
                previous_segment_context = PREVIOUS_SEGMENT_CONTEXT.format(
                    prev_title=previous_segment.get("title", "Segment précédent"),
                    prev_script=previous_segment.get("script_text", "")[:1500]  # Limit size
                )
                log.info(f"📚 Including previous segment context for topic '{topic_slug}'")
        
        # V12: Get editorial intention for this topic
        topic_intention = get_topic_intention(topic_slug) if topic_slug else ""
        if topic_intention:
            log.info(f"🎯 Applying editorial angle for topic '{topic_slug}'")
        
        # V14: LEGAL - YouTube Attribution
        # If source is YouTube, use specific attribution format
        if source_type == "youtube_video" and metadata:
            attribution_prefix = metadata.get("attribution_prefix", f"{source_name} explique dans sa vidéo que")
            attribution_instruction = f'"{attribution_prefix}..."'
            source_label = f"Vidéo YouTube: {source_name}"
            log.info(f"🎬 YouTube attribution: {attribution_prefix}")
        else:
            attribution_instruction = f'"Selon {source_name}..."'
            source_label = f"Source: {source_name}"
        
        # Get prompt from DB or use default
        prompt_template = get_prompt_from_db("dialogue_segment", DIALOGUE_SEGMENT_PROMPT)
        
        prompt = prompt_template.format(
            word_count=word_count,
            style=style,
            title=title,
            attribution_instruction=attribution_instruction,
            source_label=source_label,
            content=full_content,
            previous_segment_rule=previous_segment_rule,
            previous_segment_context=previous_segment_context,
            topic_intention=topic_intention
        )
        
        for attempt in range(3):
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=word_count * 3
            )
            
            script = response.choices[0].message.content.strip()
            
            # Validate dialogue format
            has_tags = '[A]' in script or '[B]' in script
            if has_tags:
                # Ensure dialogue ends with Alice [A]
                script = ensure_bob_conclusion(script)
                log.info(f"✅ Dialogue script generated: {len(script.split())} words" + 
                        (" (enriched)" if enriched_context else ""))
                return script
            
            prompt += "\n\nATTENTION: Tu DOIS utiliser [A] et [B] pour chaque réplique!"
        
        return script
        
    except Exception as e:
        log.error(f"Failed to generate script: {e}")
        return None


def ensure_bob_conclusion(script: str) -> str:
    """Ensure the dialogue ends with Bob [B], not Alice [A].
    
    In the new format: Bob (Analyste) exposes and concludes, Alice (Sceptique) challenges.
    """
    lines = script.strip().split('\n')
    
    # Find the last speaker tag
    last_a_idx = -1
    last_b_idx = -1
    
    for i, line in enumerate(lines):
        if line.strip() == '[A]':
            last_a_idx = i
        elif line.strip() == '[B]':
            last_b_idx = i
    
    # If Alice speaks last, we need to fix it (Bob should conclude)
    if last_a_idx > last_b_idx:
        log.warning("⚠️ Dialogue ended with Alice, adding Bob conclusion")
        
        # Append Bob's conclusion
        conclusion_phrases = [
            "Voilà pour les faits. On surveillera les prochains développements.",
            "Ce sont les données clés à retenir sur ce sujet.",
            "Les chiffres parlent d'eux-mêmes. Affaire à suivre.",
            "Voilà l'état des lieux. On verra comment ça évolue.",
            "C'est ce que disent les sources. Le reste, c'est de la spéculation."
        ]
        import random
        conclusion = random.choice(conclusion_phrases)
        
        script = script.rstrip() + f"\n\n[B]\n{conclusion}"
        log.info("✅ Added Bob conclusion to dialogue")
    
    return script


# ============================================
# SEGMENT CACHING
# ============================================

def get_previous_segment_for_topic(topic_slug: str, user_id: str = None, days_back: int = 7) -> Optional[dict]:
    """
    Get the most recent segment generated for the same topic.
    Used to avoid repetition and build on previous coverage.
    
    Returns:
        dict with 'script_text', 'title', 'source_title', 'created_at' or None
    """
    try:
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        
        query = supabase.table("audio_segments") \
            .select("script_text, source_title, topic_slug, created_at") \
            .eq("topic_slug", topic_slug) \
            .gte("created_at", cutoff_date) \
            .order("created_at", desc=True) \
            .limit(1)
        
        # Optionally filter by user_id if provided
        if user_id:
            query = query.eq("user_id", user_id)
        
        result = query.execute()
        
        if result.data and len(result.data) > 0:
            segment = result.data[0]
            log.info(f"📚 Found previous segment for topic '{topic_slug}': {segment.get('source_title', '')[:40]}...")
            return {
                "script_text": segment.get("script_text", ""),
                "title": segment.get("source_title", ""),
                "created_at": segment.get("created_at", "")
            }
        
        return None
        
    except Exception as e:
        log.warning(f"⚠️ Could not fetch previous segment for topic: {e}")
        return None


def get_content_hash(url: str, content: str) -> str:
    """Generate unique hash for content."""
    data = f"{url}:{content[:1000]}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def get_cached_segment(content_hash: str, target_date: date, edition: str) -> Optional[dict]:
    """Check if segment exists in cache."""
    try:
        result = supabase.table("audio_segments") \
            .select("id, audio_url, audio_duration, script_text") \
            .eq("content_hash", content_hash) \
            .eq("date", target_date.isoformat()) \
            .eq("edition", edition) \
            .single() \
            .execute()
        
        if result.data:
            supabase.table("audio_segments") \
                .update({"use_count": result.data.get("use_count", 1) + 1}) \
                .eq("id", result.data["id"]) \
                .execute()
            
            log.info("📦 Cache hit", hash=content_hash[:8])
            return result.data
    except:
        pass
    
    return None


def cache_segment(content_hash: str, topic_slug: str, target_date: date, edition: str,
                  source_url: str, source_title: str, script_text: str,
                  audio_url: str, audio_duration: int) -> bool:
    """Save segment to cache."""
    try:
        domain = urlparse(source_url).netloc.replace("www.", "") if source_url else ""
        
        supabase.table("audio_segments").insert({
            "content_hash": content_hash,
            "topic_slug": topic_slug,
            "date": target_date.isoformat(),
            "edition": edition,
            "source_url": source_url,
            "source_title": source_title,
            "source_domain": domain,
            "script_text": script_text,
            "audio_url": audio_url,
            "audio_duration": audio_duration,
            "use_count": 1
        }).execute()
        return True
    except Exception as e:
        log.warning(f"Failed to cache: {e}")
        return False


def upload_segment(local_path: str, remote_path: str) -> Optional[str]:
    """Upload segment to Supabase storage."""
    try:
        with open(local_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            remote_path, audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        return supabase.storage.from_("audio").get_public_url(remote_path)
    except Exception as e:
        log.warning(f"Upload failed: {e}")
        return None


# ============================================
# SEGMENT CREATION
# ============================================

def get_or_create_segment(
    url: str,
    title: str,
    topic_slug: str,
    target_date: date,
    edition: str,
    format_config: dict,
    use_enrichment: bool = False,
    user_id: str = None,
    source_name: str = None
) -> Optional[dict]:
    """
    Create or retrieve a DIALOGUE segment for an article.
    
    Args:
        use_enrichment: If True, uses Perplexity for deeper context (Digest mode)
        user_id: User ID for previous segment lookup (V12)
        source_name: Media display name from GSheet (V13) - e.g., "Le Monde", "TechCrunch"
    """
    
    log.info(f"📰 Processing: {title[:50]}..." + (" [enriched]" if use_enrichment else ""))
    
    # 1. Extract content
    extraction = extract_content(url)
    if not extraction:
        log.warning(f"❌ Extraction failed: {url[:50]}")
        return None
    
    source_type, extracted_title, content = extraction
    
    if not content or len(content) < 100:
        log.warning(f"❌ Content too short: {len(content) if content else 0} chars")
        return None
    
    if not title and extracted_title:
        title = extracted_title
    
    # V13: Use source_name from GSheet if provided, otherwise fallback to URL parsing
    if not source_name:
        source_name = urlparse(url).netloc.replace("www.", "")
        log.debug(f"⚠️ No source_name provided, using URL: {source_name}")
    else:
        log.info(f"📰 Source: {source_name}")
    
    # 2. Extract digest metadata (for episode_digests)
    digest = extract_article_digest(
        title=title,
        content=content,
        source_name=source_name,
        url=url
    )
    
    # 3. Check cache (only if not enriched - enriched content should be fresh)
    content_hash = get_content_hash(url, content)
    if not use_enrichment:
        cached = get_cached_segment(content_hash, target_date, edition)
        if cached:
            return {
                "audio_url": cached["audio_url"],
                "duration": cached["audio_duration"],
                "script": cached["script_text"],
                "title": title,
                "url": url,
                "source_name": source_name,
                "cached": True,
                "digest": digest  # Include digest even for cached segments
            }
    
    # 4. Generate DIALOGUE script (with Perplexity enrichment for Digest)
    # V12: Pass topic_slug to check for previous segment
    # V17: Use segment duration constraints instead of words_per_article
    target_words = format_config.get("segment_target_words", 150)
    max_words = format_config.get("segment_max_words", 200)
    
    script = generate_dialogue_segment_script(
        title=title,
        content=content,
        source_name=source_name,
        word_count=target_words,
        max_word_count=max_words,
        style=format_config["style"],
        use_enrichment=use_enrichment,
        topic_slug=topic_slug,
        user_id=user_id
    )
    
    if not script:
        return None
    
    # 4. Generate DIALOGUE audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"segment_{content_hash[:8]}_{timestamp}.mp3")
    
    audio_path = generate_dialogue_audio(script, temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    # 5. Upload
    remote_path = f"segments/{target_date.isoformat()}/{edition}/{content_hash[:16]}.mp3"
    audio_url = upload_segment(audio_path, remote_path)
    
    if not audio_url:
        audio_url = audio_path
    
    # 6. Cache
    cache_segment(
        content_hash=content_hash,
        topic_slug=topic_slug,
        target_date=target_date,
        edition=edition,
        source_url=url,
        source_title=title,
        script_text=script,
        audio_url=audio_url,
        audio_duration=duration
    )
    
    log.info(f"✅ Segment created: {title[:40]}, {duration}s")
    
    return {
        "audio_url": audio_url,
        "audio_path": audio_path,
        "duration": duration,
        "script": script,
        "title": title,
        "url": url,
        "source_name": source_name,
        "cached": False,
        "digest": digest  # Include extracted digest
    }


def get_or_create_multi_source_segment(
    articles: list[dict],
    cluster_theme: str,
    target_date: date,
    edition: str,
    format_config: dict,
    user_id: str = None
) -> Optional[dict]:
    """Create an enriched segment from multiple articles on the same topic."""
    
    log.info(f"🔥 Creating multi-source segment: {cluster_theme[:50]}... ({len(articles)} sources)")
    
    # Get topic from first article for previous segment lookup
    topic_slug = articles[0].get("keyword", "general") if articles else "general"
    
    # 1. Extract content from all articles
    extracted_articles = []
    all_digests = []
    
    for article in articles:
        extraction = extract_content(article["url"])
        if extraction:
            source_type, extracted_title, content = extraction
            
            # V13: Use source_name from GSheet if available, otherwise fallback to URL
            source_name = article.get("source_name")
            if not source_name:
                source_name = urlparse(article["url"]).netloc.replace("www.", "")
            
            extracted_articles.append({
                "title": article.get("title") or extracted_title,
                "content": content[:3000],  # Limit per article for multi-source
                "source_name": source_name,
                "url": article["url"]
            })
            
            # Extract digest for each article
            digest = extract_article_digest(
                title=article.get("title") or extracted_title,
                content=content,
                source_name=source_name,
                url=article["url"]
            )
            if digest:
                all_digests.append({
                    "title": article.get("title") or extracted_title,
                    "url": article["url"],
                    "digest": digest
                })
    
    if not extracted_articles:
        log.warning("❌ No content extracted from multi-source cluster")
        return None
    
    # 2. Build multi-source content for prompt
    sources_content = ""
    for i, art in enumerate(extracted_articles, 1):
        sources_content += f"\n--- SOURCE {i}: {art['source_name']} ---\n"
        sources_content += f"Titre: {art['title']}\n"
        sources_content += f"Contenu:\n{art['content']}\n"
    
    # V12: Get previous segment for this topic to avoid repetition
    previous_segment = get_previous_segment_for_topic(topic_slug, user_id)
    previous_segment_rule = ""
    previous_segment_context = ""
    
    if previous_segment and previous_segment.get("script_text"):
        previous_segment_rule = PREVIOUS_SEGMENT_RULE
        previous_segment_context = PREVIOUS_SEGMENT_CONTEXT.format(
            prev_title=previous_segment.get("title", "Segment précédent"),
            prev_script=previous_segment.get("script_text", "")[:1500]
        )
        log.info(f"📚 Including previous segment context for multi-source topic '{topic_slug}'")
    
    # V12: Get editorial intention for this topic
    topic_intention = get_topic_intention(topic_slug)
    if topic_intention:
        log.info(f"🎯 Applying editorial angle for multi-source topic '{topic_slug}'")
    
    # 3. Generate dialogue with multi-source prompt
    # More words for richer multi-source content
    word_count = int(format_config["words_per_article"] * 1.5)
    
    prompt = DIALOGUE_MULTI_SOURCE_PROMPT.format(
        word_count=word_count,
        source_count=len(extracted_articles),
        sources_content=sources_content,
        style=format_config["style"],
        previous_segment_rule=previous_segment_rule,
        previous_segment_context=previous_segment_context,
        topic_intention=topic_intention
    )
    
    script = None
    if groq_client:
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Tu es un scripteur de podcast expert. Tu croises les sources pour créer un dialogue riche et informatif."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=word_count * 4
            )
            script = response.choices[0].message.content
            log.info(f"✅ Multi-source script generated: {len(script)} chars")
        except Exception as e:
            log.error(f"❌ Multi-source script generation failed: {e}")
    
    if not script:
        return None
    
    # 4. Generate audio
    content_hash = hashlib.md5(f"{cluster_theme}_{len(articles)}".encode()).hexdigest()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"multi_{content_hash[:8]}_{timestamp}.mp3")
    
    audio_path = generate_dialogue_audio(script, temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    # 5. Upload
    remote_path = f"segments/{target_date.isoformat()}/{edition}/multi_{content_hash[:16]}.mp3"
    audio_url = upload_segment(audio_path, remote_path)
    
    if not audio_url:
        audio_url = audio_path
    
    # V12: Cache this multi-source segment for future non-repetition
    cache_segment(
        content_hash=content_hash,
        topic_slug=topic_slug,
        target_date=target_date,
        edition=edition,
        source_url=articles[0]["url"],
        source_title=cluster_theme,
        script_text=script,
        audio_url=audio_url,
        audio_duration=duration
    )
    
    log.info(f"✅ Multi-source segment created: {cluster_theme[:40]}, {duration}s, {len(articles)} sources")
    
    return {
        "audio_url": audio_url,
        "audio_path": audio_path,
        "duration": duration,
        "script": script,
        "title": cluster_theme,
        "sources": extracted_articles,
        "cached": False,
        "digests": all_digests  # All digests from cluster
    }


# ============================================
# INTRO WITH MUSIC MIXING
# ============================================

INTRO_MUSIC_PATH = os.path.join(os.path.dirname(__file__), "intro_music.mp3")

def create_intro_block(voice_intro_audio, ephemeride_audio, first_dialogue_audio, intro_music_path: str) -> tuple:
    """
    Create the intro block: music plays to its full length underneath everything.
    
    V14.5 TIMELINE - Music plays to the END:
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ 0s        2s        ~4s              ~12s                    ~20s           │
    │ │         │         │                │                       │              │
    │ ▼         ▼         ▼                ▼                       ▼              │
    │ ═══════════════════════════════════════════════════════════════════════     │
    │ │ SOLO   │   MUSIC DUCKED (-15dB) underneath all voice      │FADEOUT│       │
    │ ═══════════════════════════════════════════════════════════════════════     │
    │           ██████████                                                        │
    │           │VOICE    │                                                       │
    │                     ██████████████████                                      │
    │                     │   EPHEMERIDE   │                                      │
    │                                      ████████████████████████████...        │
    │                                      │    FIRST DIALOGUE        │           │
    └─────────────────────────────────────────────────────────────────────────────┘
    
    - 0s: Music starts (full volume)
    - 2s: Voice intro starts, music ducks to -15dB
    - Voice ends → Ephemeride starts IMMEDIATELY
    - Ephemeride ends → Dialogue starts IMMEDIATELY  
    - Music continues underneath until it naturally ends, then fades out
    
    Returns:
        (combined_audio, total_duration_seconds)
    """
    from pydub import AudioSegment
    
    VOICE_START = 2000          # Voice intro starts at 2s
    DUCK_DB = -15               # Music volume when voice is playing
    FADE_OUT_DURATION = 2000    # 2s fade out at end of music
    DUCK_TRANSITION = 300       # 300ms to duck smoothly
    
    # Calculate durations
    voice_intro_duration = len(voice_intro_audio) if voice_intro_audio else 0
    ephemeride_duration = len(ephemeride_audio) if ephemeride_audio else 0
    dialogue_duration = len(first_dialogue_audio) if first_dialogue_audio else 0
    
    # Total voice content
    total_voice_content = voice_intro_duration + ephemeride_duration + dialogue_duration
    voice_end_time = VOICE_START + total_voice_content
    
    log.info(f"🎵 Content: intro={voice_intro_duration//1000}s, ephemeride={ephemeride_duration//1000}s, dialogue={dialogue_duration//1000}s")
    
    # Load music
    if not os.path.exists(intro_music_path):
        log.warning(f"⚠️ Intro music not found at {intro_music_path}")
        # Fallback: just concatenate voice elements with silence at start
        combined = AudioSegment.silent(duration=VOICE_START)
        if voice_intro_audio:
            combined += voice_intro_audio
        if ephemeride_audio:
            combined += ephemeride_audio
        if first_dialogue_audio:
            combined += first_dialogue_audio
        return combined, len(combined) // 1000
    
    music = AudioSegment.from_mp3(intro_music_path)
    music_length = len(music)
    log.info(f"🎵 Music file length: {music_length/1000:.1f}s")
    
    # The block length is the MAX of: music length OR voice content end
    # Music plays to its natural end (with fade), voice may extend beyond
    total_block_length = max(music_length, voice_end_time)
    
    # === BUILD DUCKED MUSIC TRACK ===
    
    # Part 1: Full volume (0 - 2s)
    music_solo = music[:VOICE_START]
    
    # Part 2: Duck transition (2s - 2.3s) - smooth volume reduction
    duck_section = music[VOICE_START:VOICE_START + DUCK_TRANSITION]
    ducked_transition = AudioSegment.empty()
    slice_ms = 50
    for i in range(0, min(DUCK_TRANSITION, len(duck_section)), slice_ms):
        slice_audio = duck_section[i:i + slice_ms]
        if len(slice_audio) > 0:
            progress = i / DUCK_TRANSITION
            db_change = DUCK_DB * progress
            ducked_transition += slice_audio + db_change
    
    # Part 3: Ducked section (rest of music, minus fade out)
    ducked_start = VOICE_START + DUCK_TRANSITION
    ducked_end = music_length - FADE_OUT_DURATION
    if ducked_end > ducked_start:
        music_ducked = music[ducked_start:ducked_end] + DUCK_DB
    else:
        music_ducked = AudioSegment.empty()
    
    # Part 4: Fade out (still ducked, then fade to silence)
    if ducked_end < music_length:
        music_fadeout = (music[ducked_end:music_length] + DUCK_DB).fade_out(FADE_OUT_DURATION)
    else:
        music_fadeout = AudioSegment.empty()
    
    # Combine music track
    processed_music = music_solo + ducked_transition + music_ducked + music_fadeout
    log.info(f"🎵 Processed music: {len(processed_music)//1000}s")
    
    # === BUILD VOICE TRACK ===
    
    # 2s silence, then voice intro, then ephemeride, then dialogue (back-to-back, no gaps)
    voice_track = AudioSegment.silent(duration=VOICE_START)
    
    if voice_intro_audio:
        voice_track += voice_intro_audio
    
    if ephemeride_audio:
        voice_track += ephemeride_audio
    
    if first_dialogue_audio:
        voice_track += first_dialogue_audio
    
    log.info(f"🎤 Voice track: {len(voice_track)//1000}s")
    
    # === MIX ===
    # Pad the shorter track to match the longer one
    if len(voice_track) < len(processed_music):
        voice_track += AudioSegment.silent(duration=len(processed_music) - len(voice_track))
    elif len(processed_music) < len(voice_track):
        processed_music += AudioSegment.silent(duration=len(voice_track) - len(processed_music))
    
    combined = processed_music.overlay(voice_track)
    
    # Gentle fade in at start
    combined = combined.fade_in(200)
    
    total_duration = len(combined) // 1000
    log.info(f"✅ Intro block ready: {total_duration}s (music underneath until it ends)")
    
    return combined, total_duration


def mix_intro_with_music(voice_audio, intro_music_path: str, ephemeride_audio=None) -> tuple:
    """
    Legacy wrapper - uses create_intro_block.
    """
    return create_intro_block(
        voice_intro_audio=voice_audio,
        ephemeride_audio=ephemeride_audio,
        first_dialogue_audio=None,
        intro_music_path=intro_music_path
    )


# ============================================
# AMBIENT TRACKS (Background music for podcast)
# ============================================

AMBIENT_BUCKET = "ambient-tracks"
AMBIENT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "ambient_cache")

def list_ambient_tracks() -> list[str]:
    """
    List all ambient tracks available in Supabase Storage.
    Returns list of file names.
    """
    try:
        files = supabase.storage.from_(AMBIENT_BUCKET).list()
        # Filter for mp3 files only
        tracks = [f["name"] for f in files if f["name"].endswith(".mp3")]
        log.info(f"🎵 Found {len(tracks)} ambient tracks in storage")
        return tracks
    except Exception as e:
        log.warning(f"⚠️ Could not list ambient tracks: {e}")
        return []


def get_random_ambient_track() -> Optional[str]:
    """
    Download a random ambient track and return local path.
    Caches downloaded tracks to avoid re-downloading.
    """
    import random
    
    # Ensure cache directory exists
    os.makedirs(AMBIENT_CACHE_DIR, exist_ok=True)
    
    # List available tracks
    tracks = list_ambient_tracks()
    if not tracks:
        log.warning("⚠️ No ambient tracks available")
        return None
    
    # Pick random track
    selected = random.choice(tracks)
    log.info(f"🎲 Selected ambient track: {selected}")
    
    # Check cache
    safe_name = selected.replace(" ", "_").replace("(", "").replace(")", "")
    cache_path = os.path.join(AMBIENT_CACHE_DIR, safe_name)
    
    if os.path.exists(cache_path):
        log.info(f"✅ Using cached ambient track: {cache_path}")
        return cache_path
    
    # Download from Supabase
    try:
        data = supabase.storage.from_(AMBIENT_BUCKET).download(selected)
        with open(cache_path, 'wb') as f:
            f.write(data)
        log.info(f"✅ Downloaded ambient track: {selected} -> {cache_path}")
        return cache_path
    except Exception as e:
        log.error(f"❌ Failed to download ambient track {selected}: {e}")
        return None


def mix_ambient_under_dialogue(dialogue_segments: list, intro_block_duration: int):
    """
    Mix a random ambient track underneath the dialogue segments.
    
    Args:
        dialogue_segments: List of dialogue audio segments (AudioSegment objects)
        intro_block_duration: Duration of intro block in seconds (ambient starts 2s after)
    
    Returns:
        Combined audio with ambient underneath, or None if no ambient available
    
    Timeline:
    ┌────────────────────────────────────────────────────────────────────────────┐
    │ [INTRO BLOCK]  │ 2s │        [DIALOGUE SEGMENTS]                          │
    │                │gap │                                                      │
    │                │    │ ═══════════════════════════════════════════════════  │
    │                │    │ │  AMBIENT TRACK (very low volume, -25dB)    │FADE│  │
    │                │    │ ═══════════════════════════════════════════════════  │
    │                │    │ ████████████████████████████████████████████████████ │
    │                │    │ │              DIALOGUE                            │ │
    └────────────────────────────────────────────────────────────────────────────┘
    """
    from pydub import AudioSegment
    
    AMBIENT_VOLUME_DB = -25  # Very quiet background
    AMBIENT_FADE_OUT = 3000  # 3s fade out at end
    GAP_AFTER_INTRO = 2000   # 2s gap after intro block
    
    # Get random ambient track
    ambient_path = get_random_ambient_track()
    if not ambient_path:
        return None
    
    try:
        ambient = AudioSegment.from_mp3(ambient_path)
        log.info(f"🎵 Ambient track duration: {len(ambient)//1000}s")
    except Exception as e:
        log.error(f"❌ Failed to load ambient track: {e}")
        return None
    
    # Concatenate all dialogue segments
    dialogue_combined = AudioSegment.empty()
    for seg in dialogue_segments:
        if isinstance(seg, AudioSegment):
            dialogue_combined += seg
        elif isinstance(seg, dict) and seg.get("audio"):
            dialogue_combined += seg["audio"]
    
    if len(dialogue_combined) == 0:
        log.warning("⚠️ No dialogue to mix with ambient")
        return None
    
    dialogue_duration = len(dialogue_combined)
    log.info(f"🎤 Dialogue duration: {dialogue_duration//1000}s")
    
    # Process ambient: lower volume + fade out
    ambient_processed = ambient + AMBIENT_VOLUME_DB
    
    # If ambient is longer than dialogue, trim and fade
    if len(ambient_processed) > dialogue_duration:
        ambient_processed = ambient_processed[:dialogue_duration]
    
    # Add fade out at the end
    if len(ambient_processed) > AMBIENT_FADE_OUT:
        ambient_processed = ambient_processed.fade_out(AMBIENT_FADE_OUT)
    
    # Pad ambient if shorter than dialogue
    if len(ambient_processed) < dialogue_duration:
        # Ambient ends naturally, rest is dialogue only
        ambient_processed += AudioSegment.silent(duration=dialogue_duration - len(ambient_processed))
    
    # Mix ambient under dialogue
    mixed = ambient_processed.overlay(dialogue_combined)
    
    log.info(f"✅ Mixed ambient under dialogue: {len(mixed)//1000}s")
    
    return mixed


def get_or_create_intro(first_name: str, ephemeride_audio=None) -> Optional[dict]:
    """
    Get or create personalized intro WITH background music.
    
    V14: If ephemeride_audio is provided, crossfades into it for seamless transition.
    Only caches the base intro (without ephemeride) for reuse.
    """
    from pydub import AudioSegment
    
    display_name = first_name.strip().title() if first_name else "Ami"
    
    # V14: If we have ephemeride, we need to generate fresh (with crossfade)
    # So we skip cache lookup but can still use cached voice
    cache_key = f"intro_{display_name.lower()}"
    
    # Check cache for the base intro voice (without music/ephemeride)
    cached_voice_url = None
    if not ephemeride_audio:
        try:
            cached = supabase.table("cached_intros") \
                .select("audio_url, audio_duration") \
                .eq("name_key", cache_key) \
                .single() \
                .execute()
            
            if cached.data and cached.data.get("audio_url"):
                log.info(f"✅ Using cached intro for {display_name}")
                return {
                    "audio_url": cached.data["audio_url"],
                    "duration": cached.data["audio_duration"],
                    "audio_duration": cached.data["audio_duration"]
                }
        except:
            pass
    
    # Generate new intro voice
    intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    
    log.info(f"🎤 Creating intro for {display_name}" + (" (with ephemeride crossfade)" if ephemeride_audio else ""))
    
    timestamp = datetime.now().strftime("%H%M%S")
    voice_path = os.path.join(tempfile.gettempdir(), f"intro_voice_{timestamp}.mp3")
    
    # Use Alice's voice for intro
    if not generate_tts(intro_text, "alice", voice_path):
        log.error("❌ Failed to generate intro voice")
        return None
    
    voice_audio = AudioSegment.from_mp3(voice_path)
    voice_duration = len(voice_audio) // 1000
    log.info(f"🎤 Voice generated: {voice_duration}s")
    
    if os.path.exists(INTRO_MUSIC_PATH):
        log.info(f"🎵 Mixing with intro music")
        mixed_audio, total_duration = mix_intro_with_music(voice_audio, INTRO_MUSIC_PATH, ephemeride_audio)
        
        final_path = os.path.join(tempfile.gettempdir(), f"intro_mixed_{timestamp}.mp3")
        mixed_audio.export(final_path, format="mp3", bitrate="192k")
        
        try:
            os.remove(voice_path)
        except:
            pass
        
        # Only cache if no ephemeride (base intro only)
        audio_url = None
        if not ephemeride_audio:
            remote_path = f"intros/{cache_key}.mp3"
            audio_url = upload_segment(final_path, remote_path)
            
            if audio_url:
                try:
                    supabase.table("cached_intros").upsert({
                        "name_key": cache_key,
                        "audio_url": audio_url,
                        "audio_duration": total_duration
                    }).execute()
                    log.info(f"✅ Intro cached for {display_name}")
                except Exception as e:
                    log.warning(f"⚠️ Failed to cache intro: {e}")
        
        log.info(f"✅ Intro {'with ephemeride crossfade' if ephemeride_audio else 'with music'}: {total_duration}s")
        
        return {
            "local_path": final_path,
            "audio_url": audio_url,
            "duration": total_duration,
            "audio_duration": total_duration,
            "includes_ephemeride": ephemeride_audio is not None
        }
    else:
        log.warning(f"⚠️ No intro music, using voice only")
        return {
            "local_path": voice_path,
            "duration": voice_duration,
            "audio_duration": voice_duration,
            "includes_ephemeride": False
        }


def get_or_create_ephemeride() -> Optional[dict]:
    """Generate daily ephemeride segment (NOT cached - changes daily).
    V13: Short and punchy - 5-10 seconds max, fun facts only.
    """
    from sourcing import get_best_ephemeride_fact
    
    # Get today's date in French
    today = datetime.now()
    months_fr = ["janvier", "février", "mars", "avril", "mai", "juin", 
                 "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    date_str = f"{today.day} {months_fr[today.month - 1]}"
    
    # Get ephemeride fact from Wikipedia
    ephemeride = get_best_ephemeride_fact()
    
    if ephemeride:
        year = ephemeride.get("year", "")
        fact_text = ephemeride.get("text", "")
        
        # V13: Keep it SHORT - max 80 chars for the fact (~5-8 seconds spoken)
        # Truncate at sentence boundary if possible
        if len(fact_text) > 80:
            # Try to cut at a sentence boundary
            sentences = fact_text.split('. ')
            if sentences and len(sentences[0]) <= 80:
                fact_text = sentences[0]
            else:
                # Hard truncate
                fact_text = fact_text[:77] + "..."
        
        # V13: Shorter format - no "Nous sommes le", just the fun fact
        ephemeride_text = f"Le {date_str}, en {year}, {fact_text}"
        log.info(f"📅 Ephemeride: {year} - {fact_text[:50]}...")
    else:
        # V13: Skip ephemeride entirely if no fun fact
        log.warning("⚠️ No ephemeride fact available - skipping")
        return None
    
    timestamp = datetime.now().strftime("%H%M%S")
    ephemeride_path = os.path.join(tempfile.gettempdir(), f"ephemeride_{timestamp}.mp3")
    
    # Use Alice's voice (female - la sceptique)
    if not generate_tts(ephemeride_text, "alice", ephemeride_path):
        log.error("❌ Failed to generate ephemeride")
        return None
    
    duration = get_audio_duration(ephemeride_path)
    
    # V13: If too long (>12s), skip it
    if duration > 12:
        log.warning(f"⚠️ Ephemeride too long ({duration}s > 12s) - skipping")
        return None
    
    log.info(f"✅ Ephemeride generated: {duration}s")
    
    return {
        "local_path": ephemeride_path,
        "duration": duration,
        "audio_duration": duration
    }


def get_or_create_outro() -> Optional[dict]:
    """Get or create outro."""
    try:
        result = supabase.table("cached_outros") \
            .select("audio_url, audio_duration") \
            .eq("outro_type", "standard") \
            .single() \
            .execute()
        
        if result.data:
            return result.data
    except:
        pass
    
    outro_text = "C'était votre Keernel du jour. À demain pour de nouvelles découvertes!"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"outro_{timestamp}.mp3")
    
    # Use Alice's voice for outro
    if not generate_tts(outro_text, "alice", temp_path):
        return None
    
    duration = get_audio_duration(temp_path)
    
    remote_path = "outros/standard.mp3"
    audio_url = upload_segment(temp_path, remote_path)
    
    if audio_url:
        try:
            supabase.table("cached_outros").upsert({
                "outro_type": "standard",
                "audio_url": audio_url,
                "audio_duration": duration
            }).execute()
        except:
            pass
    
    return {"audio_url": audio_url, "audio_duration": duration}


# ============================================
# CONTENT SELECTION - SMART CLUSTERING
# ============================================

CLUSTERING_PROMPT = """Analyse ces titres d'articles et regroupe UNIQUEMENT ceux qui parlent du MÊME ÉVÉNEMENT SPÉCIFIQUE.

TITRES:
{titles}

RÉPONDS EN JSON UNIQUEMENT (pas de texte avant/après):
{{
  "clusters": [
    {{
      "theme": "Description courte du sujet commun",
      "article_indices": [0, 3, 5],
      "priority": "high/medium/low"
    }}
  ]
}}

RÈGLES STRICTES:
- REGROUPER UNIQUEMENT si les articles parlent du MÊME ÉVÉNEMENT (ex: même annonce, même actualité)
- NE PAS regrouper des articles juste parce qu'ils parlent du même domaine général (ex: "IA" n'est pas un regroupement valide)
- Un article peut être dans UN SEUL cluster
- Les articles seuls (pas de doublon) = cluster avec 1 seul indice
- priority "high" = 3+ articles sur le MÊME événement spécifique
- priority "medium" = 2 articles sur le MÊME événement spécifique  
- priority "low" = article seul (LA MAJORITÉ devrait être "low")
- Les indices commencent à 0
- EN CAS DE DOUTE, NE PAS REGROUPER

JSON:"""


def cluster_articles_by_theme(items: list[dict]) -> list[dict]:
    """
    Use LLM to cluster articles by theme/topic.
    Returns list of clusters with articles grouped by similar subjects.
    """
    if not items:
        return []
    
    if len(items) <= 3:
        # Too few articles to cluster meaningfully
        return [{"theme": item.get("title", ""), "articles": [item], "priority": "low"} for item in items]
    
    if not groq_client:
        log.warning("❌ Groq client not available for clustering, using fallback")
        return [{"theme": item.get("title", ""), "articles": [item], "priority": "low"} for item in items]
    
    try:
        # Prepare titles for clustering
        titles = "\n".join([f"{i}. {item.get('title', 'Sans titre')}" for i, item in enumerate(items)])
        
        prompt = CLUSTERING_PROMPT.format(titles=titles)
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000
        )
        
        json_text = response.choices[0].message.content.strip()
        
        # Clean up response
        if json_text.startswith("```"):
            json_text = json_text.split("```")[1]
            if json_text.startswith("json"):
                json_text = json_text[4:]
        json_text = json_text.strip()
        
        import json
        result = json.loads(json_text)
        
        clusters = []
        used_indices = set()
        
        for cluster_data in result.get("clusters", []):
            indices = cluster_data.get("article_indices", [])
            valid_indices = [i for i in indices if i < len(items) and i not in used_indices]
            
            if valid_indices:
                cluster = {
                    "theme": cluster_data.get("theme", ""),
                    "articles": [items[i] for i in valid_indices],
                    "priority": cluster_data.get("priority", "low"),
                    "source_count": len(valid_indices)
                }
                clusters.append(cluster)
                used_indices.update(valid_indices)
        
        # Add any unclustered articles
        for i, item in enumerate(items):
            if i not in used_indices:
                clusters.append({
                    "theme": item.get("title", ""),
                    "articles": [item],
                    "priority": "low",
                    "source_count": 1
                })
        
        log.info(f"🎯 Clustering complete: {len(clusters)} clusters from {len(items)} articles")
        
        # Log multi-source clusters
        multi_source = [c for c in clusters if c["source_count"] > 1]
        if multi_source:
            log.info(f"🔥 Multi-source topics: {len(multi_source)}")
            for c in multi_source:
                log.info(f"   - {c['theme']}: {c['source_count']} sources ({c['priority']})")
        
        return clusters
        
    except Exception as e:
        log.error(f"❌ Clustering failed: {e}, using fallback")
        return [{"theme": item.get("title", ""), "articles": [item], "priority": "low", "source_count": 1} for item in items]


# ============================================
# INVENTORY-FIRST SELECTION (14+1 Algorithm)
# ============================================

def get_user_topic_weights(user_id: str) -> dict:
    """Get user's topic weights from database or return defaults."""
    try:
        result = supabase.table("users") \
            .select("topic_weights") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if result.data and result.data.get("topic_weights"):
            return result.data["topic_weights"]
    except:
        pass
    
    # Default weights (all topics equal at 50%)
    return {topic: 50 for topic in VALID_TOPICS}


def get_user_history_hashes(user_id: str, days_back: int = 30) -> set:
    """Get content hashes of segments already served to this user."""
    try:
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        
        result = supabase.table("user_history") \
            .select("content_hash") \
            .eq("user_id", user_id) \
            .gte("served_at", cutoff_date) \
            .execute()
        
        if result.data:
            return {row["content_hash"] for row in result.data if row.get("content_hash")}
    except Exception as e:
        log.warning(f"⚠️ Could not fetch user history: {e}")
    
    return set()


def record_user_history(user_id: str, segments: list, episode_id: str = None):
    """Record segments served to user for future deduplication."""
    try:
        records = []
        for seg in segments:
            if seg.get("content_hash"):
                records.append({
                    "user_id": user_id,
                    "content_hash": seg["content_hash"],
                    "topic_slug": seg.get("keyword", seg.get("topic_slug", "general")),
                    "episode_id": episode_id
                })
        
        if records:
            supabase.table("user_history").upsert(
                records,
                on_conflict="user_id,content_hash"
            ).execute()
            log.info(f"📝 Recorded {len(records)} segments in user history")
    except Exception as e:
        log.warning(f"⚠️ Failed to record user history: {e}")


def calculate_final_score(item: dict, user_weights: dict, now: datetime) -> float:
    """
    Calculate Final_Score = (Relevance * User_Weight) * (1 / (1 + Age_en_jours))
    
    - Relevance: Base relevance from content (default 0.5)
    - User_Weight: User's preference for this topic (0-100, normalized to 0-1)
    - Age decay: Fresher content scores higher
    """
    # Get base relevance (from AI or default)
    relevance = item.get("relevance_score", 0.5)
    
    # Get user weight for this topic (0-100 -> 0-1)
    topic = item.get("keyword", item.get("topic_slug", "general"))
    user_weight = user_weights.get(topic, 50) / 100.0
    
    # Calculate age in days
    created_at = item.get("created_at")
    if created_at:
        try:
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                created_dt = created_at
            age_days = (now - created_dt.replace(tzinfo=None)).days
        except:
            age_days = 0
    else:
        age_days = 0
    
    # Age decay factor: 1 / (1 + age_days)
    age_decay = 1.0 / (1.0 + age_days)
    
    # Final score
    final_score = (relevance * user_weight) * age_decay
    
    return final_score


def select_inventory_first(user_id: str, max_segments: int = 8) -> list[dict]:
    """
    INVENTORY-FIRST Selection Algorithm V17
    
    Respects user topic preferences with intelligent fallback.
    
    Algorithm:
    1. Get segments from cache (TODAY only - segments are single-day)
    2. Exclude segments already served to this user (user_history)
    3. Classify topics by priority tier based on user weights
    4. Select from HIGH priority first, then MEDIUM, then LOW
    5. Topics at 0% are EXCLUDED except for Breaking News (exceptional events)
    
    V17 Segment Rule:
    - Segments are ONLY served on their creation day
    - After day J, segment is never re-served to anyone
    
    Priority Tiers:
    - HIGH:    70-100% weight → Served first
    - MEDIUM:  30-69% weight  → Fill gaps
    - LOW:     1-29% weight   → Last resort
    - EXCLUDED: 0% weight     → Never (except breaking news)
    
    Breaking News Exception:
    - relevance_score >= 0.95
    - article_count >= 5 (multi-source)
    - timeliness_score >= 0.8
    → Inject max 1 at end of podcast
    
    Returns: List of selected segments ready for podcast assembly
    """
    log.info(f"🎯 Running INVENTORY-FIRST V17 selection for user {user_id[:8]}...")
    
    now = datetime.now()
    from datetime import timedelta
    # V17: Only today's segments are eligible
    cache_cutoff = (now - timedelta(days=SEGMENT_CACHE_DAYS)).isoformat()
    
    # 1. Get user preferences
    user_weights = get_user_topic_weights(user_id)
    log.info(f"📊 User weights: {user_weights}")
    
    # Classify topics by priority tier
    high_priority_topics = [t for t, w in user_weights.items() if w >= 70]
    medium_priority_topics = [t for t, w in user_weights.items() if 30 <= w < 70]
    low_priority_topics = [t for t, w in user_weights.items() if 1 <= w < 30]
    excluded_topics = [t for t, w in user_weights.items() if w == 0]
    
    log.info(f"   🔴 HIGH (70-100%): {high_priority_topics}")
    log.info(f"   🟡 MEDIUM (30-69%): {medium_priority_topics}")
    log.info(f"   🟢 LOW (1-29%): {low_priority_topics}")
    log.info(f"   ⛔ EXCLUDED (0%): {excluded_topics}")
    
    # 2. Get already-served segment hashes (no re-serve to same user)
    served_hashes = get_user_history_hashes(user_id)
    log.info(f"📚 User has {len(served_hashes)} segments in history")
    
    # 3. Get eligible segments from cache (today only)
    try:
        result = supabase.table("audio_segments") \
            .select("id, content_hash, topic_slug, source_title, source_url, audio_url, audio_duration, script_text, relevance_score, timeliness_score, article_count, created_at") \
            .gte("created_at", cache_cutoff) \
            .order("created_at", desc=True) \
            .limit(200) \
            .execute()
        
        if not result.data:
            log.warning("❌ No segments in cache for today! Falling back to content_queue")
            return select_smart_content(user_id, max_segments)
        
        segments = result.data
        log.info(f"📦 Found {len(segments)} segments in cache (today)")
        
    except Exception as e:
        log.error(f"❌ Failed to query segment cache: {e}")
        return select_smart_content(user_id, max_segments)
    
    # 4. Filter out already-served segments
    eligible = []
    for seg in segments:
        content_hash = seg.get("content_hash", "")
        if content_hash and content_hash not in served_hashes:
            eligible.append(seg)
    
    log.info(f"✅ {len(eligible)} segments eligible (not yet served to user)")
    
    if len(eligible) < max_segments // 2:
        log.warning(f"⚠️ Only {len(eligible)} eligible segments, may need fresh content")
    
    # 5. Calculate Final_Score for each segment
    for seg in eligible:
        seg["_final_score"] = calculate_final_score(seg, user_weights, now)
        seg["keyword"] = seg.get("topic_slug", "general")
    
    # 6. Separate segments by priority tier
    high_candidates = []
    medium_candidates = []
    low_candidates = []
    excluded_candidates = []  # For breaking news check
    
    for seg in eligible:
        topic = seg.get("topic_slug", "general")
        if topic in excluded_topics:
            excluded_candidates.append(seg)
        elif topic in high_priority_topics:
            high_candidates.append(seg)
        elif topic in medium_priority_topics:
            medium_candidates.append(seg)
        elif topic in low_priority_topics:
            low_candidates.append(seg)
        else:
            # Topic not in user weights - treat as medium priority
            medium_candidates.append(seg)
    
    log.info(f"📊 Candidates: HIGH={len(high_candidates)}, MEDIUM={len(medium_candidates)}, LOW={len(low_candidates)}, EXCLUDED={len(excluded_candidates)}")
    
    # 7. Sort each tier by Final_Score (descending)
    high_candidates.sort(key=lambda x: x["_final_score"], reverse=True)
    medium_candidates.sort(key=lambda x: x["_final_score"], reverse=True)
    low_candidates.sort(key=lambda x: x["_final_score"], reverse=True)
    
    # 8. Select segments respecting priority tiers
    selected = []
    
    # First: Take from HIGH priority (up to max)
    for seg in high_candidates:
        if len(selected) < max_segments:
            selected.append(seg)
            log.info(f"   🔴 HIGH: {seg.get('source_title', '')[:40]}... (score: {seg['_final_score']:.3f})")
    
    # Second: Fill with MEDIUM priority
    if len(selected) < max_segments:
        for seg in medium_candidates:
            if len(selected) < max_segments:
                selected.append(seg)
                log.info(f"   🟡 MEDIUM: {seg.get('source_title', '')[:40]}... (score: {seg['_final_score']:.3f})")
    
    # Third: Fill with LOW priority
    if len(selected) < max_segments:
        for seg in low_candidates:
            if len(selected) < max_segments:
                selected.append(seg)
                log.info(f"   🟢 LOW: {seg.get('source_title', '')[:40]}... (score: {seg['_final_score']:.3f})")
    
    log.info(f"📋 Selected {len(selected)} segments from user-preferred topics")
    
    # 9. Breaking News Exception - Check excluded topics for major events
    # Criteria: relevance >= 0.95 AND article_count >= 5 AND timeliness >= 0.8
    BREAKING_NEWS_RELEVANCE = 0.95
    BREAKING_NEWS_ARTICLE_COUNT = 5
    BREAKING_NEWS_TIMELINESS = 0.8
    
    breaking_news = None
    for seg in excluded_candidates:
        relevance = seg.get("relevance_score", 0)
        article_count = seg.get("article_count", 1)
        timeliness = seg.get("timeliness_score", 0.5)
        
        is_breaking = (
            relevance >= BREAKING_NEWS_RELEVANCE and
            article_count >= BREAKING_NEWS_ARTICLE_COUNT and
            timeliness >= BREAKING_NEWS_TIMELINESS
        )
        
        if is_breaking:
            if breaking_news is None or relevance > breaking_news.get("relevance_score", 0):
                breaking_news = seg
    
    # Inject breaking news at end of podcast
    if breaking_news and len(selected) >= 2:
        selected.append(breaking_news)
        
        log.info(f"🚨 BREAKING NEWS injecté: {breaking_news.get('source_title', '')[:40]}...")
        log.info(f"   Topic: {breaking_news.get('topic_slug')} (excluded par user)")
        log.info(f"   Relevance: {breaking_news.get('relevance_score', 0):.2f}, Articles: {breaking_news.get('article_count', 1)}, Timeliness: {breaking_news.get('timeliness_score', 0):.2f}")
    
    # 10. Log final selection
    log.info(f"✅ INVENTORY-FIRST V17: {len(selected)} segments selected")
    for i, seg in enumerate(selected):
        score = seg.get("_final_score", 0)
        topic = seg.get("topic_slug", "?")
        title = seg.get("source_title", "")[:35]
        is_breaking = seg == breaking_news
        marker = "🚨" if is_breaking else f"{i+1}."
        log.info(f"   {marker} [{topic}] {title}... (score: {score:.3f})")
    
    # Convert to format expected by assembler
    formatted = []
    for seg in selected:
        formatted.append({
            "url": seg.get("source_url", ""),
            "title": seg.get("source_title", ""),
            "keyword": seg.get("topic_slug", "general"),
            "content_hash": seg.get("content_hash"),
            "audio_url": seg.get("audio_url"),
            "audio_duration": seg.get("audio_duration"),
            "script_text": seg.get("script_text"),
            "_from_cache": True,
            "_final_score": seg.get("_final_score", 0),
            "_is_breaking_news": seg == breaking_news
        })
    
    return formatted


def select_smart_content(user_id: str, max_articles: int, min_articles: int = 1) -> list[dict]:
    """
    Smart content selection with thematic clustering.
    
    V17 CHANGES:
    - Filters out topics with 0% weight (respects user preferences)
    
    V14.5 CHANGES:
    - min_articles removed (default 1) - generate podcast even with few articles
    - Uses signal mix weights for topic selection
    
    V12 CHANGES:
    - Clustering is LESS aggressive (only groups same EVENT, not same domain)
    - Guarantees minimum number of CLUSTERS (segments), not just articles
    - Falls back to diverse selection if not enough clusters
    
    - Groups similar articles together
    - Prioritizes multi-source topics
    - Returns clusters instead of individual articles
    """
    try:
        # V17: Get user weights to filter excluded topics
        user_weights = get_user_topic_weights(user_id)
        excluded_topics = [t for t, w in user_weights.items() if w == 0]
        log.info(f"⛔ Excluded topics (0% weight): {excluded_topics}")
        
        # V17: Global queue - no user_id filter
        result = supabase.table("content_queue") \
            .select("url, title, keyword, source, source_name, vertical_id") \
            .eq("status", "pending") \
            .order("created_at") \
            .limit(100) \
            .execute()
        
        if not result.data:
            log.warning("❌ No pending content in global queue!")
            return []
        
        items = result.data
        log.info(f"📋 Global queue has {len(items)} PENDING items (before filtering)")
        
        # V17: Filter out excluded topics
        items = [item for item in items if item.get("keyword", "general") not in excluded_topics]
        log.info(f"📋 After filtering excluded topics: {len(items)} items")
        
        if not items:
            log.warning("❌ No items after filtering excluded topics!")
            return []
        
        # Separate priority vs bing
        priority_items = []
        bing_items = []
        
        for item in items:
            source = (item.get("source") or "").lower()
            if "bing" in source:
                bing_items.append(item)
            else:
                priority_items.append(item)
        
        log.info(f"📊 Priority (GSheet/manual): {len(priority_items)}, Bing: {len(bing_items)}")
        
        # If very few items, skip clustering and use all
        if len(items) <= min_articles:
            log.info(f"⚠️ Only {len(items)} items, using ALL without clustering")
            for item in items:
                item["_cluster_theme"] = item.get("title", "")
                item["_cluster_size"] = 1
                item["_cluster_priority"] = "high" if "bing" not in (item.get("source") or "").lower() else "low"
            return items[:max_articles]
        
        # Cluster all items together for theme detection
        all_items = priority_items + bing_items
        clusters = cluster_articles_by_theme(all_items)
        
        # Sort clusters by priority: high > medium > low, then by source_count
        priority_order = {"high": 0, "medium": 1, "low": 2}
        clusters.sort(key=lambda c: (priority_order.get(c["priority"], 2), -c["source_count"]))
        
        # V12: Calculate minimum CLUSTERS needed (not articles)
        # For Flash: we want at least 5-6 distinct segments
        # For Digest: we want at least 8-10 distinct segments
        min_clusters = min_articles  # Each cluster = 1 segment
        
        # Select clusters until we reach max_articles OR min_clusters
        selected_clusters = []
        total_articles = 0
        
        for cluster in clusters:
            cluster_size = len(cluster["articles"])
            
            # For multi-source clusters, include up to 2 articles (not 3)
            if cluster["source_count"] > 1:
                articles_to_take = min(cluster_size, 2)
            else:
                articles_to_take = 1
            
            # V12: Keep selecting until we have enough CLUSTERS
            # Allow going slightly over max_articles to ensure enough segments
            should_select = (
                len(selected_clusters) < min_clusters or  # Need more clusters
                (total_articles + articles_to_take <= max_articles + 2)  # Still under limit
            )
            
            if should_select and len(selected_clusters) < max_articles:  # Hard cap on clusters
                cluster["selected_articles"] = cluster["articles"][:articles_to_take]
                selected_clusters.append(cluster)
                total_articles += articles_to_take
                
                if cluster["source_count"] > 1:
                    log.info(f"🔥 MULTI-SOURCE: {cluster['theme'][:50]}... ({articles_to_take} articles)")
                else:
                    log.info(f"   ✅ Selected: {cluster['articles'][0].get('title', '')[:40]}...")
            
            # Stop only when we have enough clusters AND articles
            if len(selected_clusters) >= min_clusters and total_articles >= max_articles:
                break
        
        # Flatten selected articles with cluster info
        selected = []
        for cluster in selected_clusters:
            for article in cluster.get("selected_articles", []):
                article["_cluster_theme"] = cluster["theme"]
                article["_cluster_size"] = cluster["source_count"]
                article["_cluster_priority"] = cluster["priority"]
                selected.append(article)
        
        multi_count = sum(1 for c in selected_clusters if c["source_count"] > 1)
        log.info(f"✅ Clustering result: {len(selected_clusters)} clusters, {len(selected)} articles ({multi_count} multi-source)")
        
        # V12: Check if we have enough CLUSTERS (segments)
        if len(selected_clusters) < min_clusters:
            log.warning(f"⚠️ Only {len(selected_clusters)} clusters, need at least {min_clusters}")
            log.warning(f"⚠️ This may result in a shorter podcast")
        
        return selected
        
    except Exception as e:
        log.error(f"Smart content selection failed: {e}")
        # Fallback to diverse selection
        log.warning(f"⚠️ Falling back to select_diverse_content due to error")
        return select_diverse_content(user_id, max_articles)


def select_diverse_content(user_id: str, max_articles: int) -> list[dict]:
    """
    Select content prioritizing GSheet sources.
    
    V17: Filters out topics with 0% weight.
    """
    try:
        # V17: Get user weights to filter excluded topics
        user_weights = get_user_topic_weights(user_id)
        excluded_topics = [t for t, w in user_weights.items() if w == 0]
        
        # V17: Global queue - no user_id filter
        result = supabase.table("content_queue") \
            .select("url, title, keyword, source, source_name, vertical_id") \
            .eq("status", "pending") \
            .order("created_at") \
            .limit(100) \
            .execute()
        
        if not result.data:
            log.warning("❌ No pending content in global queue!")
            return []
        
        items = result.data
        
        # V17: Filter out excluded topics
        items = [item for item in items if item.get("keyword", "general") not in excluded_topics]
        
        if not items:
            log.warning("❌ No items after filtering excluded topics!")
            return []
        
        unique_sources = set(i.get("source", "NONE") for i in items)
        log.info(f"📋 Global queue has {len(items)} items (after excluding {len(excluded_topics)} topics), sources: {unique_sources}")
        
        priority_items = []
        bing_items = []
        
        for item in items:
            source = (item.get("source") or "").lower()
            if "bing" in source:
                bing_items.append(item)
            else:
                priority_items.append(item)
        
        log.info(f"📊 Priority (non-bing): {len(priority_items)}, Bing: {len(bing_items)}")
        
        priority_by_topic = {}
        for item in priority_items:
            topic = item.get("keyword") or item.get("vertical_id") or "general"
            if topic not in priority_by_topic:
                priority_by_topic[topic] = []
            priority_by_topic[topic].append(item)
        
        selected = []
        topic_list = list(priority_by_topic.keys())
        idx = 0
        
        while len(selected) < max_articles and topic_list:
            topic = topic_list[idx % len(topic_list)]
            if priority_by_topic.get(topic):
                item = priority_by_topic[topic].pop(0)
                selected.append(item)
                log.info(f"   ✅ Selected: {item.get('title', 'No title')[:40]}... (source={item.get('source')})")
            idx += 1
            topic_list = [t for t in topic_list if priority_by_topic.get(t)]
        
        remaining = max_articles - len(selected)
        if remaining > 0 and bing_items:
            log.info(f"📰 Need {remaining} more, filling from Bing...")
            
            bing_by_topic = {}
            for item in bing_items:
                topic = item.get("keyword") or "news"
                if topic not in bing_by_topic:
                    bing_by_topic[topic] = []
                bing_by_topic[topic].append(item)
            
            topic_list = list(bing_by_topic.keys())
            idx = 0
            while len(selected) < max_articles and topic_list:
                topic = topic_list[idx % len(topic_list)]
                if bing_by_topic.get(topic):
                    item = bing_by_topic[topic].pop(0)
                    selected.append(item)
                    log.info(f"   📰 Added Bing: {item.get('title', 'No title')[:40]}...")
                idx += 1
                topic_list = [t for t in topic_list if bing_by_topic.get(t)]
        
        priority_count = sum(1 for s in selected if "bing" not in (s.get("source") or "").lower())
        bing_count = len(selected) - priority_count
        
        log.info(f"✅ FINAL: {len(selected)} articles ({priority_count} priority, {bing_count} bing)")
        return selected
        
    except Exception as e:
        log.error(f"Content selection failed: {e}")
        return []


# ============================================
# V14: CLUSTER-BASED CONTENT SELECTION
# ============================================

def select_from_clusters(user_id: str, max_topics: int = 15) -> list[dict]:
    """
    V14: Select content from pre-computed daily clusters.
    Falls back to legacy selection if no clusters available.
    
    Returns list of cluster syntheses ready for dialogue generation.
    """
    try:
        from cluster_pipeline import get_daily_clusters
        
        # Get today's clusters for this user
        clusters = get_daily_clusters(user_id)
        
        if not clusters:
            log.warning("⚠️ No daily clusters found, using legacy selection")
            return []
        
        log.info(f"🎯 Found {len(clusters)} pre-computed clusters")
        
        # Convert clusters to format expected by dialogue generator
        items = []
        for cluster in clusters[:max_topics]:
            items.append({
                "keyword": cluster.get("topic", "general"),
                "topic_slug": cluster.get("topic", "general"),
                "title": cluster.get("theme", ""),
                "url": cluster.get("urls", [""])[0] if cluster.get("urls") else "",
                "source_name": ", ".join(cluster.get("sources", ["Multiple sources"])[:2]),
                "content": f"{cluster.get('thesis', '')} {cluster.get('antithesis', '')}",
                "hook": cluster.get("hook", ""),
                "thesis": cluster.get("thesis", ""),
                "antithesis": cluster.get("antithesis", ""),
                "key_data": cluster.get("key_data", []),
                "article_count": cluster.get("article_count", 1),
                "_from_cluster": True,
                "_cluster_score": cluster.get("score", 0)
            })
        
        log.info(f"✅ Selected {len(items)} topics from clusters")
        return items
        
    except ImportError:
        log.warning("⚠️ cluster_pipeline not available, using legacy selection")
        return []
    except Exception as e:
        log.error(f"❌ Cluster selection failed: {e}")
        return []


# ============================================
# MAIN ASSEMBLY
# ============================================

def assemble_lego_podcast(
    user_id: str,
    target_duration: int = 15,
    format_type: str = "digest"
) -> Optional[dict]:
    """Assemble podcast with DIALOGUE segments (Alice & Bob)."""
    
    config = FORMAT_CONFIG.get(format_type, FORMAT_CONFIG["digest"])
    target_minutes = config["duration_minutes"]
    # V17: Use segments instead of articles
    max_segments = config.get("max_segments", 8)
    min_segments = config.get("min_segments", 6)
    
    log.info("=" * 60)
    log.info(f"🎙️ ASSEMBLING PODCAST V17 (Alice & Bob)")
    log.info(f"   Format: {format_type}")
    log.info(f"   Target: {target_minutes} minutes")
    log.info(f"   Segments: {min_segments}-{max_segments} (+ potential breaking news)")
    log.info(f"   Selection: Priority tiers (HIGH → MEDIUM → LOW)")
    log.info("=" * 60)
    
    # V17 DIAGNOSTIC: Count pending content in global queue
    try:
        pending_check = supabase.table("content_queue") \
            .select("id, source, keyword") \
            .eq("status", "pending") \
            .execute()
        
        pending_count = len(pending_check.data) if pending_check.data else 0
        
        # Count by source
        source_counts = {}
        topic_counts = {}
        for item in (pending_check.data or []):
            src = item.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
            topic = item.get("keyword", "unknown")
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        log.info(f"📊 GLOBAL QUEUE DIAGNOSTIC: {pending_count} pending articles")
        log.info(f"   By source: {source_counts}")
        log.info(f"   By topic: {topic_counts}")
        
        if pending_count < min_segments:
            log.warning(f"⚠️ CRITICAL: Only {pending_count} pending articles, need at least {min_segments}!")
    except Exception as e:
        log.warning(f"⚠️ Could not run queue diagnostic: {e}")
    
    try:
        user_result = supabase.table("users") \
            .select("first_name") \
            .eq("id", user_id) \
            .single() \
            .execute()
        first_name = user_result.data.get("first_name", "Ami") if user_result.data else "Ami"
    except:
        first_name = "Ami"
    
    # V14: Inject premium sources (score > 90) into deals category
    try:
        premium_injected = inject_premium_sources_to_deals(user_id)
        if premium_injected > 0:
            log.info(f"🌟 Premium Module: {premium_injected} articles injected into deals")
    except Exception as e:
        log.debug(f"Premium injection skipped: {e}")
    
    # V17: Selection cascade based on priority tiers
    # 1. Try cluster-based selection
    # 2. Try inventory-first (priority tiers)
    # 3. Fallback to smart_content
    
    items = select_from_clusters(user_id, max_segments)
    
    if len(items) < min_segments:
        log.info(f"📦 Only {len(items)} from clusters, trying inventory cache...")
        items = select_inventory_first(user_id, max_segments)
    
    if len(items) < min_segments:
        log.warning(f"⚠️ Only {len(items)} from inventory, using content_queue")
        items = select_smart_content(user_id, max_segments, min_articles=min_segments)
    
    if not items:
        log.warning("❌ No content to process")
        return None
    
    log.info(f"📦 Selected {len(items)} segments for processing")
    
    target_date = date.today()
    edition = "morning" if datetime.now().hour < 14 else "evening"
    
    segments = []
    sources_data = []
    digests_data = []  # Collect digests for later saving
    total_duration = 0
    target_seconds = target_minutes * 60
    
    # V13 FIX: Group items by TOPIC (keyword) for consolidation
    # This ensures ONE segment per topic, not one per article
    # V14.5 FIX: Store topic separately, use title for display
    clusters = {}
    cluster_topics = {}  # Map cluster_key -> topic keyword
    for item in items:
        # Group by topic (keyword) for consolidation
        topic_key = item.get("keyword", item.get("topic_slug", "general"))
        
        # Use article title as cluster key for display (not keyword)
        # Fall back to keyword only if no title
        cluster_display_key = item.get("title") or item.get("_cluster_theme") or topic_key
        
        if topic_key not in clusters:
            clusters[topic_key] = []
            cluster_topics[topic_key] = topic_key
        clusters[topic_key].append(item)
    
    log.info(f"📊 Processing {len(clusters)} topics (consolidated from {len(items)} articles)")
    for topic, topic_items in clusters.items():
        log.info(f"   - {topic}: {len(topic_items)} article(s)")
    
    # Track chapters for player navigation
    chapters = []
    
    # ============================================
    # V14.5: CREATE INTRO BLOCK (Music + Voice + Ephemeride + First Dialogue)
    # Music plays to its full length, even under the start of dialogue
    # ============================================
    from pydub import AudioSegment
    
    # 1. Generate intro voice
    display_name = first_name.strip().title() if first_name else "Ami"
    intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    intro_voice_path = os.path.join(tempfile.gettempdir(), f"intro_voice_{datetime.now().strftime('%H%M%S')}.mp3")
    
    intro_voice_audio = None
    if generate_tts(intro_text, "alice", intro_voice_path):
        intro_voice_audio = AudioSegment.from_mp3(intro_voice_path)
        log.info(f"🎤 Intro voice: {len(intro_voice_audio)//1000}s")
    
    # 2. Generate ephemeride
    ephemeride_audio = None
    ephemeride_data = get_or_create_ephemeride()
    if ephemeride_data and ephemeride_data.get("local_path"):
        try:
            ephemeride_audio = AudioSegment.from_mp3(ephemeride_data["local_path"])
            log.info(f"🎤 Ephemeride: {len(ephemeride_audio)//1000}s")
        except Exception as e:
            log.warning(f"⚠️ Could not load ephemeride: {e}")
    
    # 3. Generate FIRST dialogue segment (to include in intro block with music)
    first_dialogue_audio = None
    first_cluster_key = None
    first_cluster_items = None
    first_segment_data = None
    
    if clusters:
        first_cluster_key = list(clusters.keys())[0]
        first_cluster_items = clusters[first_cluster_key]
        
        # V14.5: Use actual article title for display, not keyword
        first_display_title = first_cluster_items[0].get("title") or first_cluster_items[0].get("_cluster_theme") or first_cluster_key
        
        log.info(f"🎵 Pre-generating first dialogue for intro block: {first_display_title[:50]}")
        
        if len(first_cluster_items) > 1:
            # V14.5: Use first article's title as theme, not keyword
            first_article_title = first_cluster_items[0].get("title") or first_cluster_items[0].get("_cluster_theme") or first_cluster_key
            first_segment_data = get_or_create_multi_source_segment(
                articles=first_cluster_items,
                cluster_theme=first_article_title,
                target_date=target_date,
                edition=edition,
                format_config=config,
                user_id=user_id
            )
        else:
            first_segment_data = get_or_create_segment(
                article=first_cluster_items[0],
                target_date=target_date,
                edition=edition,
                format_config=config,
                user_id=user_id
            )
        
        if first_segment_data and first_segment_data.get("audio_path"):
            try:
                first_dialogue_audio = AudioSegment.from_mp3(first_segment_data["audio_path"])
                log.info(f"🎤 First dialogue: {len(first_dialogue_audio)//1000}s")
            except Exception as e:
                log.warning(f"⚠️ Could not load first dialogue: {e}")
    
    # 4. Create intro block (music underneath everything until music ends)
    if os.path.exists(INTRO_MUSIC_PATH):
        intro_block_audio, intro_block_duration = create_intro_block(
            voice_intro_audio=intro_voice_audio,
            ephemeride_audio=ephemeride_audio,
            first_dialogue_audio=first_dialogue_audio,
            intro_music_path=INTRO_MUSIC_PATH
        )
        
        # Save intro block
        intro_block_path = os.path.join(tempfile.gettempdir(), f"intro_block_{datetime.now().strftime('%H%M%S')}.mp3")
        intro_block_audio.export(intro_block_path, format="mp3", bitrate="192k")
        
        # Add as single segment
        segments.append({
            "type": "intro_block",
            "audio_path": intro_block_path,
            "duration": intro_block_duration
        })
        
        # Add chapters
        chapters.append({"title": "Introduction", "start_time": 0, "type": "intro"})
        
        chapter_time = 2  # Voice starts at 2s
        if intro_voice_audio:
            chapter_time += len(intro_voice_audio) // 1000
        
        if ephemeride_audio:
            chapters.append({"title": "Éphéméride", "start_time": chapter_time, "type": "ephemeride"})
            chapter_time += len(ephemeride_audio) // 1000
        
        if first_dialogue_audio and first_cluster_key:
            chapters.append({
                "title": first_cluster_key.replace("_", " ").title(),
                "start_time": chapter_time,
                "type": "news"
            })
            # Track sources for first segment
            if first_segment_data:
                sources_data.append({
                    "title": first_segment_data.get("title", first_cluster_key),
                    "url": first_cluster_items[0].get("url", ""),
                    "source": first_cluster_items[0].get("source_name", ""),
                    "topic": first_cluster_key
                })
                if first_segment_data.get("digests"):
                    digests_data.extend(first_segment_data["digests"])
            
            # Remove first cluster since it's already in intro block
            del clusters[first_cluster_key]
        
        total_duration = intro_block_duration
        log.info(f"✅ Intro block: {intro_block_duration}s (music + intro + ephemeride + first dialogue)")
    else:
        # Fallback without music
        log.warning("⚠️ No intro music found, using voice only")
        if intro_voice_audio:
            intro_path = os.path.join(tempfile.gettempdir(), f"intro_{datetime.now().strftime('%H%M%S')}.mp3")
            intro_voice_audio.export(intro_path, format="mp3", bitrate="192k")
            segments.append({"type": "intro", "audio_path": intro_path, "duration": len(intro_voice_audio)//1000})
            chapters.append({"title": "Introduction", "start_time": 0, "type": "intro"})
            total_duration += len(intro_voice_audio) // 1000
        
        if ephemeride_audio:
            segments.append({"type": "ephemeride", "audio_path": ephemeride_data["local_path"], "duration": len(ephemeride_audio)//1000})
            chapters.append({"title": "Éphéméride", "start_time": total_duration, "type": "ephemeride"})
            total_duration += len(ephemeride_audio) // 1000
            total_duration += len(ephemeride_audio) // 1000
            total_duration += ephemeride_data.get("duration", 10)
    
    # 3. NEWS SEGMENTS - Process REMAINING clusters with TRANSITIONS
    # Note: First cluster was already included in intro block (if music exists)
    cluster_idx = 0
    previous_topic = None
    
    for cluster_topic, cluster_items in clusters.items():
        cluster_idx += 1
        
        # V14.5: Use actual article title for display, not keyword
        cluster_display_title = cluster_items[0].get("title") or cluster_items[0].get("_cluster_theme") or cluster_topic
        
        # Get topic for transition
        current_topic = cluster_items[0].get("keyword", "general")
        current_vertical = cluster_items[0].get("vertical_id", "general")
        
        # Add TRANSITION between segments
        # V14.5: Always add transition since first dialogue was in intro block
        transition = get_or_create_transition(current_topic, current_vertical)
        if transition:
            segments.append({
                "type": "transition",
                "audio_url": transition.get("audio_url"),
                "duration": transition.get("duration", 2),
                "text": transition.get("text", "")
            })
            total_duration += transition.get("duration", 2)
            log.info(f"🎵 Transition: {transition.get('text', '')} ({transition.get('duration', 0)}s)")
        
        # Record chapter start time (after transition)
        chapter_start = total_duration
        
        if len(cluster_items) > 1:
            # Multi-source topic - create enriched segment
            log.info(f"🔥 Processing MULTI-SOURCE cluster {cluster_idx}: {cluster_display_title[:50]}... ({len(cluster_items)} articles)")
            
            segment = get_or_create_multi_source_segment(
                articles=cluster_items,
                cluster_theme=cluster_display_title,
                target_date=target_date,
                edition=edition,
                format_config=config,
                user_id=user_id  # V12: Pass user_id for previous segment lookup
            )
            
            if segment:
                segments.append({
                    "type": "news",
                    "audio_path": segment.get("audio_path"),
                    "audio_url": segment.get("audio_url"),
                    "duration": segment.get("duration", 90),
                    "title": cluster_display_title,
                    "url": cluster_items[0]["url"]
                })
                
                # Add chapter
                chapters.append({
                    "title": cluster_display_title[:60],  # Truncate long titles
                    "start_time": chapter_start,
                    "type": "news",
                    "topic": current_topic,
                    "url": cluster_items[0]["url"],
                    "multi_source": True
                })
                
                total_duration += segment.get("duration", 90)
                
                # Add all sources
                for article in cluster_items:
                    sources_data.append({
                        "title": article.get("title") or cluster_display_title,
                        "url": article.get("url"),
                        "domain": urlparse(article["url"]).netloc.replace("www.", ""),
                        "cluster": cluster_display_title
                    })
                
                # Collect digests for all articles in cluster
                for digest_item in segment.get("digests", []):
                    digests_data.append(digest_item)
                
                log.info(f"📊 Multi-source segment: {segment.get('duration', 0)}s | Total: {total_duration}s")
        else:
            # Single source - regular processing
            item = cluster_items[0]
            log.info(f"🎯 Processing article {cluster_idx}: {item.get('title', 'No title')[:50]}...")
            
            # Use Perplexity enrichment for ALL formats (Flash + Digest)
            # Cost: ~$0.005/article = $27/month for 15 topics × 2 formats
            use_enrichment = True
            
            segment = get_or_create_segment(
                url=item["url"],
                title=item.get("title", ""),
                topic_slug=item.get("keyword", "general"),
                target_date=target_date,
                edition=edition,
                format_config=config,
                use_enrichment=use_enrichment,
                user_id=user_id,
                source_name=item.get("source_name")  # V13: Media name from GSheet
            )
            
            if segment:
                segments.append({
                    "type": "news",
                    "audio_path": segment.get("audio_path"),
                    "audio_url": segment.get("audio_url"),
                    "duration": segment.get("duration", 60),
                    "title": segment.get("title"),
                    "url": segment.get("url")
                })
                
                # Add chapter
                chapters.append({
                    "title": (segment.get("title") or item.get("title", ""))[:60],
                    "start_time": chapter_start,
                    "type": "news",
                    "topic": current_topic,
                    "url": segment.get("url"),
                    "multi_source": False
                })
                
                total_duration += segment.get("duration", 60)
                
                sources_data.append({
                    "title": segment.get("title"),
                    "url": segment.get("url"),
                    "domain": segment.get("source_name", urlparse(item["url"]).netloc)
                })
                
                # Collect digest for this article
                if segment.get("digest"):
                    digests_data.append({
                        "title": segment.get("title"),
                        "url": segment.get("url"),
                        "digest": segment.get("digest")
                    })
                
                log.info(f"📊 Segment {cluster_idx}: {segment.get('duration', 0)}s | Total: {total_duration}s / {target_seconds}s")
            else:
                log.warning(f"⚠️ Failed to create segment for: {item.get('title', 'No title')[:40]}")
    
    if not sources_data:
        log.error("❌ No segments generated!")
        return None
    
    # 3. OUTRO
    outro = get_or_create_outro()
    if outro:
        segments.append({
            "type": "outro",
            "audio_url": outro.get("audio_url"),
            "duration": outro.get("audio_duration", 5)
        })
        total_duration += outro.get("audio_duration", 5)
    
    log.info(f"📦 Total segments: {len(segments)}, Duration: {total_duration}s ({total_duration//60}m{total_duration%60}s)")
    
    # 4. STITCH
    final_url = stitch_segments(segments, user_id, target_date)
    
    if not final_url:
        log.error("❌ Stitching failed!")
        return None
    
    # 5. CREATE EPISODE
    try:
        # V13: New title format: [Express/Deep Dive] de [PRENOM] du [DATE]
        format_display = "Express" if format_type == "flash" else "Deep Dive"
        title = f"{format_display} de {first_name} du {target_date.strftime('%d %B %Y')}"
        
        episode = supabase.table("episodes").insert({
            "user_id": user_id,
            "title": title,
            "audio_url": final_url,
            "audio_duration": total_duration,
            "sources_data": sources_data,
            "chapters": chapters,  # V12: Add chapters for player navigation
            "summary_text": f"Keernel {format_display} avec {len(sources_data)} sources"
        }).execute()
        
        log.info(f"📚 Episode has {len(chapters)} chapters")
        
        # Mark USED articles as processed
        processed_urls = [s["url"] for s in sources_data]
        if processed_urls:
            supabase.table("content_queue") \
                .update({"status": "processed"}) \
                .eq("user_id", user_id) \
                .in_("url", processed_urls) \
                .execute()
            log.info(f"✅ Marked {len(processed_urls)} articles as processed")
        
        # V13: Get the topics that were covered in this episode
        covered_topics = set()
        for s in sources_data:
            if s.get("topic"):
                covered_topics.add(s["topic"])
        
        # Only delete remaining pending articles from COVERED topics
        # Keep articles from topics that weren't included in this episode
        # Note: 'keyword' is the column name in content_queue
        if covered_topics:
            for topic in covered_topics:
                supabase.table("content_queue") \
                    .delete() \
                    .eq("user_id", user_id) \
                    .eq("status", "pending") \
                    .eq("keyword", topic) \
                    .execute()
            log.info(f"🗑️ Cleared remaining pending articles from {len(covered_topics)} covered topics: {covered_topics}")
        
        # Count remaining pending articles (from uncovered topics)
        remaining = supabase.table("content_queue") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        remaining_count = remaining.count if remaining.count else 0
        if remaining_count > 0:
            log.info(f"📋 {remaining_count} articles still pending for future episodes (from uncovered topics)")
        
        if episode.data:
            episode_id = episode.data[0]["id"]
            
            # Save digests to episode_digests table
            if digests_data:
                log.info(f"📝 Saving {len(digests_data)} digests...")
                for digest_item in digests_data:
                    save_episode_digest(
                        episode_id=episode_id,
                        source_url=digest_item["url"],
                        title=digest_item["title"],
                        digest=digest_item["digest"]
                    )
                log.info(f"✅ Digests saved: {len(digests_data)}")
            
            report_url = generate_episode_report(
                user_id=user_id,
                episode_id=episode_id,
                title=title,
                format_type=format_type,
                sources_data=sources_data,
                total_duration=total_duration,
                target_date=target_date
            )
            
            if report_url:
                supabase.table("episodes") \
                    .update({"report_url": report_url}) \
                    .eq("id", episode_id) \
                    .execute()
            
            # V13: Record segments in user_history for deduplication
            record_user_history(user_id, items, episode_id)
            
            log.info(f"✅ EPISODE CREATED: {total_duration}s, {len(sources_data)} sources")
            return episode.data[0]
        
        return None
        
    except Exception as e:
        log.error(f"Episode creation failed: {e}")
        return None


def stitch_segments(segments: list, user_id: str, target_date: date) -> Optional[str]:
    """
    Combine all segments into final audio file.
    
    V14.5: 
    - Intro block contains music + voice + ephemeride + first dialogue
    - Ambient track plays underneath remaining dialogue segments
    """
    try:
        from pydub import AudioSegment
        import httpx
        
        AMBIENT_VOLUME_DB = -25  # Very quiet background
        AMBIENT_FADE_OUT = 3000  # 3s fade out
        AMBIENT_START_DELAY = 2000  # 2s after intro block
        
        intro_block_audio = None
        dialogue_audios = []
        
        for seg in segments:
            audio_path = seg.get("audio_path")
            audio_url = seg.get("audio_url")
            seg_type = seg.get("type", "unknown")
            
            # Download if needed
            if not audio_path and audio_url:
                audio_path = os.path.join(tempfile.gettempdir(), f"temp_{hash(audio_url)}.mp3")
                try:
                    response = httpx.get(audio_url, timeout=30, follow_redirects=True)
                    response.raise_for_status()
                    with open(audio_path, 'wb') as f:
                        f.write(response.content)
                except Exception as e:
                    log.warning(f"Failed to download: {e}")
                    continue
            
            if not audio_path or not os.path.exists(audio_path):
                continue
            
            try:
                audio = AudioSegment.from_mp3(audio_path)
                
                if seg_type == "intro_block":
                    intro_block_audio = audio
                else:
                    dialogue_audios.append(audio)
                    
            except Exception as e:
                log.warning(f"Failed to load segment: {e}")
        
        # Start with intro block
        if intro_block_audio is None:
            log.error("❌ No intro block found")
            return None
        
        combined = intro_block_audio
        log.info(f"🎵 Intro block: {len(intro_block_audio)//1000}s")
        
        # Concatenate dialogue segments
        if not dialogue_audios:
            log.info("📝 No additional dialogue segments (all in intro block)")
        else:
            transition = AudioSegment.silent(duration=300)
            dialogue_combined = AudioSegment.empty()
            
            for i, audio in enumerate(dialogue_audios):
                dialogue_combined += audio
                if i < len(dialogue_audios) - 1:
                    dialogue_combined += transition
            
            log.info(f"🎤 Dialogue segments: {len(dialogue_combined)//1000}s")
            
            # Get ambient track and mix under dialogue
            ambient_path = get_random_ambient_track()
            
            if ambient_path:
                try:
                    ambient = AudioSegment.from_mp3(ambient_path)
                    log.info(f"🎵 Ambient track: {len(ambient)//1000}s")
                    
                    # Process ambient: lower volume
                    ambient_processed = ambient + AMBIENT_VOLUME_DB
                    
                    # Trim or pad ambient to match dialogue
                    if len(ambient_processed) > len(dialogue_combined):
                        ambient_processed = ambient_processed[:len(dialogue_combined)]
                    
                    # Add fade out
                    if len(ambient_processed) > AMBIENT_FADE_OUT:
                        ambient_processed = ambient_processed.fade_out(AMBIENT_FADE_OUT)
                    
                    # Pad if shorter than dialogue
                    if len(ambient_processed) < len(dialogue_combined):
                        ambient_processed += AudioSegment.silent(
                            duration=len(dialogue_combined) - len(ambient_processed)
                        )
                    
                    # Mix ambient under dialogue
                    dialogue_with_ambient = ambient_processed.overlay(dialogue_combined)
                    log.info(f"✅ Mixed ambient under dialogue")
                    
                    # Add 2s silence then dialogue with ambient
                    combined += AudioSegment.silent(duration=AMBIENT_START_DELAY)
                    combined += dialogue_with_ambient
                    
                except Exception as e:
                    log.warning(f"⚠️ Failed to mix ambient: {e}, using dialogue without ambient")
                    combined += AudioSegment.silent(duration=AMBIENT_START_DELAY)
                    combined += dialogue_combined
            else:
                # No ambient available, just add dialogue
                combined += AudioSegment.silent(duration=AMBIENT_START_DELAY)
                combined += dialogue_combined
        
        if len(combined) == 0:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"podcast_{timestamp}.mp3")
        combined.export(output_path, format="mp3", bitrate="192k")
        
        log.info(f"✅ Final podcast: {len(combined)//1000}s")
        
        remote_path = f"{user_id}/keernel_{target_date.isoformat()}_{timestamp}.mp3"
        
        with open(output_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            remote_path, audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        
        final_url = supabase.storage.from_("audio").get_public_url(remote_path)
        
        try:
            os.remove(output_path)
        except:
            pass
        
        return final_url
        
    except Exception as e:
        log.error(f"Stitching failed: {e}")
        return None


# ============================================
# REPORT GENERATION
# ============================================

def generate_episode_report(
    user_id: str,
    episode_id: str,
    title: str,
    format_type: str,
    sources_data: list[dict],
    total_duration: int,
    target_date: date
) -> Optional[str]:
    """Generate Markdown report for the episode."""
    
    duration_str = f"{total_duration // 60}m {total_duration % 60}s"
    
    report_md = f"""---
title: "{title}"
date: {target_date.isoformat()}
format: {format_type}
duration: {duration_str}
sources_count: {len(sources_data)}
---

# {title}

**Format** : {format_type.title()} ({duration_str})  
**Date** : {target_date.strftime('%d %B %Y')}  
**Sources** : {len(sources_data)} articles

---

## 📰 Sources traitées

"""
    
    for i, source in enumerate(sources_data, 1):
        source_title = source.get("title", "Sans titre")
        source_url = source.get("url", "#")
        source_domain = source.get("domain", urlparse(source_url).netloc)
        
        report_md += f"""### {i}. {source_title}

- **Source** : [{source_domain}]({source_url})

"""
    
    report_md += f"""---

*Rapport généré par Keernel - {datetime.now().strftime('%d/%m/%Y %H:%M')}*
"""
    
    try:
        report_filename = f"report_{target_date.isoformat()}_{episode_id[:8]}.md"
        remote_path = f"reports/{user_id}/{target_date.strftime('%Y/%m')}/{report_filename}"
        
        supabase.storage.from_("reports").upload(
            remote_path,
            report_md.encode('utf-8'),
            {"content-type": "text/markdown", "upsert": "true"}
        )
        
        report_url = supabase.storage.from_("reports").get_public_url(remote_path)
        
        supabase.table("episode_reports").insert({
            "user_id": user_id,
            "episode_id": episode_id,
            "report_url": report_url,
            "report_date": target_date.isoformat(),
            "format_type": format_type,
            "sources_count": len(sources_data),
            "duration_seconds": total_duration,
            "markdown_content": report_md
        }).execute()
        
        log.info(f"📄 Report generated: {report_filename}")
        return report_url
        
    except Exception as e:
        log.error(f"Failed to generate report: {e}")
        return None


# ============================================
# HISTORY & MAINTENANCE
# ============================================

def get_user_history(user_id: str, limit: int = 20) -> List[dict]:
    """Get list of past episode reports for a user."""
    try:
        result = supabase.table("episode_reports") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("report_date", desc=True) \
            .limit(limit) \
            .execute()
        
        return result.data if result.data else []
    except Exception as e:
        log.error(f"Failed to get user history: {e}")
        return []


def cleanup_old_audio_cache(days_to_keep: int = SEGMENT_CACHE_DAYS):
    """Remove audio segments older than specified days."""
    try:
        cutoff_date = (date.today() - timedelta(days=days_to_keep)).isoformat()
        
        old_segments = supabase.table("audio_segments") \
            .select("id, audio_url, date") \
            .lt("date", cutoff_date) \
            .execute()
        
        if not old_segments.data:
            return 0
        
        deleted_count = 0
        for segment in old_segments.data:
            try:
                supabase.table("audio_segments") \
                    .delete() \
                    .eq("id", segment["id"]) \
                    .execute()
                deleted_count += 1
            except:
                pass
        
        log.info(f"🗑️ Cleaned up {deleted_count} old segments")
        return deleted_count
    except Exception as e:
        log.error(f"Cache cleanup failed: {e}")
        return 0
