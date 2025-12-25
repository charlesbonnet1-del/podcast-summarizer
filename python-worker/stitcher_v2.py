"""
Keernel Stitcher V11 - Cartesia TTS with Alice & Bob

VOICE SYSTEM:
- Primary: Cartesia Sonic 3.0
  - Alice (Helpful French Lady) = Lead, explains
  - Bob (Pierre) = Challenger, questions
- Fallback: OpenAI TTS (nova/onyx)

NO Azure voices - completely removed.

CHANGES:
- Breeze/Vale → Alice/Bob
- Azure removed
- Cartesia as primary TTS
- OpenAI as fallback only
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
# Alice = "Helpful French Lady" - friendly, helpful, leads the conversation
# Bob = "Pierre" - French male voice, asks questions
#
# ⚠️ IMPORTANT: Find the correct Voice IDs in Cartesia Playground:
#    1. Go to https://play.cartesia.ai/
#    2. Search for "Helpful French Lady" → Copy the voice ID
#    3. Search for "Pierre" (French male) → Copy the voice ID
#    4. Replace the placeholders below
#
# These are placeholder IDs - replace with actual IDs from Cartesia
CARTESIA_VOICE_ALICE = os.getenv("CARTESIA_VOICE_ALICE", "a3520a8f-226a-428d-9fcd-b0a4711a6829")
CARTESIA_VOICE_BOB = os.getenv("CARTESIA_VOICE_BOB", "ab7c61f5-3daa-47dd-a23b-4ac0aac5f5c3")

# Fallback OpenAI voices (only used if Cartesia fails)
OPENAI_VOICE_ALICE = "nova"    # Female
OPENAI_VOICE_BOB = "onyx"      # Male

# Model
CARTESIA_MODEL = "sonic-3"

# Speed (Cartesia uses -1.0 to 1.0, 0 = normal)
CARTESIA_SPEED = 0.0  # Normal speed

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

# ============================================
# CONFIGURATION
# ============================================

WORDS_PER_MINUTE = 150
SEGMENT_CACHE_DAYS = 7
REPORT_RETENTION_DAYS = 365

# Format configurations - OPTIMIZED FOR DENSITY
FORMAT_CONFIG = {
    "flash": {
        "duration_minutes": 4,
        "total_words": 900,
        "max_articles": 7,
        "words_per_article": 130,
        "style": "ultra-concis et percutant"
    },
    "digest": {
        "duration_minutes": 15,
        "total_words": 2800,
        "max_articles": 12,
        "words_per_article": 240,
        "style": "approfondi et analytique"
    }
}

# ============================================
# DIALOGUE PROMPT - ALICE & BOB
# ============================================

DIALOGUE_SEGMENT_PROMPT = """Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.

## LES HÔTES
- [A] ALICE = Experte qui mène la conversation, explique clairement
- [B] BOB = Challenger curieux qui pose des questions pertinentes

## FORMAT OBLIGATOIRE
Chaque réplique DOIT commencer par [A] ou [B] seul sur une ligne:

[A]
Alice parle et explique.

[B]
Bob questionne ou réagit.

## RÈGLES STRICTES
1. ALTERNER [A] et [B] - jamais deux [A] ou deux [B] de suite
2. ALICE [A] commence TOUJOURS en premier
3. Minimum 6 répliques (3 de chaque)
4. Style oral naturel français: "Écoute,", "En fait,", "Tu vois,"
5. BOB [B] pose des QUESTIONS
6. ZÉRO liste, ZÉRO bullet points
7. CITE LA SOURCE dans la première réplique: "Selon {source_name}..."
8. INTERDIT: Ne jamais écrire "Alice répond", "Bob questionne" ou toute didascalie

## SOURCE
Titre: {title}
Source: {source_name}
Contenu:
{content}

## GÉNÈRE LE DIALOGUE ({word_count} mots, style {style}):"""


# Multi-source prompt for topics covered by multiple articles
DIALOGUE_MULTI_SOURCE_PROMPT = """Tu es scripteur de podcast. Écris un DIALOGUE ENRICHI de {word_count} mots entre deux hôtes.

## CONTEXTE SPÉCIAL
Ce sujet est couvert par PLUSIEURS SOURCES - c'est donc un sujet d'actualité majeur !
Tu dois CROISER et COMPARER les informations des différentes sources.

## LES HÔTES
- [A] ALICE = Experte qui synthétise les différentes sources
- [B] BOB = Challenger qui compare et questionne les différents angles

## FORMAT OBLIGATOIRE
Chaque réplique DOIT commencer par [A] ou [B] seul sur une ligne:

[A]
Alice synthétise et compare.

[B]
Bob questionne ou souligne les différences.

## RÈGLES STRICTES
1. ALTERNER [A] et [B] - jamais deux [A] ou deux [B] de suite
2. ALICE [A] commence TOUJOURS en premier
3. Minimum 8 répliques (4 de chaque) - sujet plus riche !
4. Style oral naturel français
5. CITE LES DIFFÉRENTES SOURCES: "Selon Le Monde...", "De son côté, Les Échos rapportent..."
6. COMPARE les points de vue ou informations complémentaires
7. ZÉRO liste, ZÉRO bullet points

## SOURCES ({source_count} articles sur ce sujet)
{sources_content}

## GÉNÈRE LE DIALOGUE ({word_count} mots, style {style}, en croisant les sources):"""

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
    """Generate TTS using Cartesia Sonic 3.0"""
    if not cartesia_client:
        return False
    
    try:
        log.info(f"🎤 Cartesia TTS: {len(text)} chars, voice={voice_id[:8]}...")
        
        # Generate audio bytes
        audio_bytes = b""
        for chunk in cartesia_client.tts.bytes(
            model_id=CARTESIA_MODEL,
            transcript=text,
            voice={"mode": "id", "id": voice_id},
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
        
        log.info(f"✅ Cartesia audio saved: {len(audio_bytes)} bytes")
        return True
        
    except Exception as e:
        log.error(f"❌ Cartesia TTS failed: {e}")
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
    
    voice_type: "alice" or "bob"
    """
    # Map voice type to voice IDs
    if voice_type == "alice":
        cartesia_voice = CARTESIA_VOICE_ALICE
        openai_voice = OPENAI_VOICE_ALICE
    else:  # bob
        cartesia_voice = CARTESIA_VOICE_BOB
        openai_voice = OPENAI_VOICE_BOB
    
    # Try Cartesia first
    if cartesia_client and generate_tts_cartesia(text, cartesia_voice, output_path):
        return True
    
    # Fallback to OpenAI
    log.warning(f"⚠️ Falling back to OpenAI TTS")
    return generate_tts_openai(text, openai_voice, output_path)


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
# SCRIPT GENERATION
# ============================================

def generate_dialogue_segment_script(
    title: str,
    content: str,
    source_name: str,
    word_count: int = 200,
    style: str = "dynamique"
) -> Optional[str]:
    """Generate DIALOGUE script for a segment."""
    if not groq_client:
        log.error("Groq client not available")
        return None
    
    try:
        prompt = DIALOGUE_SEGMENT_PROMPT.format(
            word_count=word_count,
            style=style,
            title=title,
            source_name=source_name,
            content=content[:4000]
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
                log.info(f"✅ Dialogue script generated: {len(script.split())} words")
                return script
            
            prompt += "\n\nATTENTION: Tu DOIS utiliser [A] et [B] pour chaque réplique!"
        
        return script
        
    except Exception as e:
        log.error(f"Failed to generate script: {e}")
        return None


# ============================================
# SEGMENT CACHING
# ============================================

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
    format_config: dict
) -> Optional[dict]:
    """Create or retrieve a DIALOGUE segment for an article."""
    
    log.info(f"📰 Processing: {title[:50]}...")
    
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
    
    source_name = urlparse(url).netloc.replace("www.", "")
    
    # 2. Extract digest metadata (for episode_digests)
    digest = extract_article_digest(
        title=title,
        content=content,
        source_name=source_name,
        url=url
    )
    
    # 3. Check cache
    content_hash = get_content_hash(url, content)
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
    
    # 4. Generate DIALOGUE script
    script = generate_dialogue_segment_script(
        title=title,
        content=content,
        source_name=source_name,
        word_count=format_config["words_per_article"],
        style=format_config["style"]
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
    format_config: dict
) -> Optional[dict]:
    """Create an enriched segment from multiple articles on the same topic."""
    
    log.info(f"🔥 Creating multi-source segment: {cluster_theme[:50]}... ({len(articles)} sources)")
    
    # 1. Extract content from all articles
    extracted_articles = []
    all_digests = []
    
    for article in articles:
        extraction = extract_content(article["url"])
        if extraction:
            source_type, extracted_title, content = extraction
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
    
    # 3. Generate dialogue with multi-source prompt
    # More words for richer multi-source content
    word_count = int(format_config["words_per_article"] * 1.5)
    
    prompt = DIALOGUE_MULTI_SOURCE_PROMPT.format(
        word_count=word_count,
        source_count=len(extracted_articles),
        sources_content=sources_content,
        style=format_config["style"]
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

def mix_intro_with_music(voice_audio, intro_music_path: str, first_segment_audio=None) -> tuple:
    """
    Mix voice intro with background music using professional ducking.
    
    If first_segment_audio is provided, it starts playing during the music fade-out
    to avoid dead air between intro and content.
    """
    from pydub import AudioSegment
    
    MUSIC_SOLO_END = 4000      # 0-4s: music solo
    DUCK_DURATION = 2000       # 4-6s: ducking
    DUCK_END = 6000            # 6s: ducked
    FADE_START = 10000         # 10s: start fade (was 12s - shortened)
    MUSIC_END = 14000          # 14s: music ends
    DUCK_DB = -20
    
    if not os.path.exists(intro_music_path):
        log.warning(f"⚠️ Intro music not found, using voice only")
        return voice_audio, len(voice_audio) // 1000
    
    music = AudioSegment.from_mp3(intro_music_path)
    
    if len(music) > MUSIC_END:
        music = music[:MUSIC_END]
    elif len(music) < MUSIC_END:
        music = music + AudioSegment.silent(duration=MUSIC_END - len(music))
    
    # Part 1: Solo music (0s - 4s)
    part1_solo = music[:MUSIC_SOLO_END]
    
    # Part 2: Progressive ducking (4s - 6s)
    part2_ducking = music[MUSIC_SOLO_END:DUCK_END]
    ducked_part2 = AudioSegment.empty()
    slice_duration = 100
    num_slices = DUCK_DURATION // slice_duration
    
    for i in range(num_slices):
        start = i * slice_duration
        end = start + slice_duration
        slice_audio = part2_ducking[start:end]
        progress = i / num_slices
        db_reduction = DUCK_DB * progress
        ducked_part2 += slice_audio + db_reduction
    
    # Part 3: Background (6s - 10s) at -20dB - SHORTENED
    part3_background = music[DUCK_END:FADE_START] + DUCK_DB
    
    # Part 4: Fade out (10s - 14s) - LONGER FADE
    part4_fadeout = (music[FADE_START:MUSIC_END] + DUCK_DB).fade_out(4000)
    
    # Combine music parts
    processed_music = part1_solo + ducked_part2 + part3_background + part4_fadeout
    
    # Position intro voice starting at 4s
    voice_with_padding = AudioSegment.silent(duration=MUSIC_SOLO_END) + voice_audio
    
    # Extend voice track to match music length
    if len(voice_with_padding) < MUSIC_END:
        voice_with_padding += AudioSegment.silent(duration=MUSIC_END - len(voice_with_padding))
    
    # Mix intro voice on music
    mixed = processed_music.overlay(voice_with_padding)
    
    # Apply gentle fade in
    mixed = mixed.fade_in(500)
    
    # IMPORTANT: Trim to 8 seconds to avoid dead air
    # The first dialogue segment will start immediately after
    TRIM_POINT = 8000  # 8 seconds - just after intro voice ends
    
    # Only trim if voice is short (< 4 seconds of speech)
    voice_duration = len(voice_audio)
    if voice_duration < 4000:
        # Trim and add quick fade out on music
        mixed = mixed[:TRIM_POINT]
        # Quick fade out on last 500ms
        fade_portion = mixed[-500:].fade_out(500)
        mixed = mixed[:-500] + fade_portion
    
    return mixed, len(mixed) // 1000


def get_or_create_intro(first_name: str) -> Optional[dict]:
    """Get or create personalized intro WITH background music."""
    from pydub import AudioSegment
    
    display_name = first_name.strip().title() if first_name else "Ami"
    intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    
    log.info(f"🎤 Creating intro for {display_name}")
    
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
        mixed_audio, total_duration = mix_intro_with_music(voice_audio, INTRO_MUSIC_PATH)
        
        final_path = os.path.join(tempfile.gettempdir(), f"intro_mixed_{timestamp}.mp3")
        mixed_audio.export(final_path, format="mp3", bitrate="192k")
        
        try:
            os.remove(voice_path)
        except:
            pass
        
        log.info(f"✅ Intro with music: {total_duration}s")
        
        return {
            "local_path": final_path,
            "duration": total_duration,
            "audio_duration": total_duration
        }
    else:
        log.warning(f"⚠️ No intro music, using voice only")
        return {
            "local_path": voice_path,
            "duration": voice_duration,
            "audio_duration": voice_duration
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

CLUSTERING_PROMPT = """Analyse ces titres d'articles et regroupe ceux qui parlent du MÊME SUJET.

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

RÈGLES:
- Un article peut être dans UN SEUL cluster
- Les articles seuls (pas de doublon) = cluster avec 1 seul indice
- priority "high" = 3+ articles sur le même sujet (actualité majeure)
- priority "medium" = 2 articles sur le même sujet
- priority "low" = article seul
- Les indices commencent à 0

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


def select_smart_content(user_id: str, max_articles: int) -> list[dict]:
    """
    Smart content selection with thematic clustering.
    - Groups similar articles together
    - Prioritizes multi-source topics
    - Returns clusters instead of individual articles
    """
    try:
        result = supabase.table("content_queue") \
            .select("url, title, keyword, source, vertical_id") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .order("created_at") \
            .limit(100) \
            .execute()
        
        if not result.data:
            log.warning("❌ No pending content in queue!")
            return []
        
        items = result.data
        log.info(f"📋 Queue has {len(items)} items")
        
        # Separate priority vs bing
        priority_items = []
        bing_items = []
        
        for item in items:
            source = (item.get("source") or "").lower()
            if "bing" in source:
                bing_items.append(item)
            else:
                priority_items.append(item)
        
        log.info(f"📊 Priority: {len(priority_items)}, Bing: {len(bing_items)}")
        
        # Cluster all items together for theme detection
        all_items = priority_items + bing_items
        clusters = cluster_articles_by_theme(all_items)
        
        # Sort clusters by priority: high > medium > low, then by source_count
        priority_order = {"high": 0, "medium": 1, "low": 2}
        clusters.sort(key=lambda c: (priority_order.get(c["priority"], 2), -c["source_count"]))
        
        # Select clusters until we reach max_articles
        selected_clusters = []
        total_articles = 0
        
        for cluster in clusters:
            cluster_size = len(cluster["articles"])
            
            # For multi-source clusters, we might include all articles
            # For single-source, just 1
            if cluster["source_count"] > 1:
                # Multi-source: include up to 3 articles from same topic
                articles_to_take = min(cluster_size, 3)
            else:
                articles_to_take = 1
            
            if total_articles + articles_to_take <= max_articles + 2:  # Small buffer for rich topics
                cluster["selected_articles"] = cluster["articles"][:articles_to_take]
                selected_clusters.append(cluster)
                total_articles += articles_to_take
                
                if cluster["source_count"] > 1:
                    log.info(f"🔥 MULTI-SOURCE: {cluster['theme'][:50]}... ({articles_to_take} articles)")
                else:
                    log.info(f"   ✅ Selected: {cluster['articles'][0].get('title', '')[:40]}...")
            
            if total_articles >= max_articles:
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
        log.info(f"✅ FINAL: {len(selected)} articles in {len(selected_clusters)} topics ({multi_count} multi-source)")
        
        return selected
        
    except Exception as e:
        log.error(f"Smart content selection failed: {e}")
        return []


def select_diverse_content(user_id: str, max_articles: int) -> list[dict]:
    """Select content prioritizing GSheet sources."""
    try:
        result = supabase.table("content_queue") \
            .select("url, title, keyword, source, vertical_id") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .order("created_at") \
            .limit(100) \
            .execute()
        
        if not result.data:
            log.warning("❌ No pending content in queue!")
            return []
        
        items = result.data
        
        unique_sources = set(i.get("source", "NONE") for i in items)
        log.info(f"📋 Queue has {len(items)} items, sources: {unique_sources}")
        
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
    max_articles = config["max_articles"]
    
    log.info("=" * 60)
    log.info(f"🎙️ ASSEMBLING PODCAST (Alice & Bob)")
    log.info(f"   Format: {format_type}")
    log.info(f"   Target: {target_minutes} minutes")
    log.info(f"   Max articles: {max_articles}")
    log.info("=" * 60)
    
    try:
        user_result = supabase.table("users") \
            .select("first_name") \
            .eq("id", user_id) \
            .single() \
            .execute()
        first_name = user_result.data.get("first_name", "Ami") if user_result.data else "Ami"
    except:
        first_name = "Ami"
    
    # Use smart clustering selection
    items = select_smart_content(user_id, max_articles)
    
    if not items:
        log.warning("❌ No content to process")
        return None
    
    target_date = date.today()
    edition = "morning" if datetime.now().hour < 14 else "evening"
    
    segments = []
    sources_data = []
    digests_data = []  # Collect digests for later saving
    total_duration = 0
    target_seconds = target_minutes * 60
    
    # Group items by cluster for multi-source processing
    clusters = {}
    for item in items:
        cluster_theme = item.get("_cluster_theme", item.get("title", ""))
        if cluster_theme not in clusters:
            clusters[cluster_theme] = []
        clusters[cluster_theme].append(item)
    
    # 1. INTRO
    intro = get_or_create_intro(first_name)
    if intro:
        segments.append({
            "type": "intro",
            "audio_url": intro.get("audio_url"),
            "audio_path": intro.get("local_path"),
            "duration": intro.get("audio_duration", intro.get("duration", 5))
        })
        total_duration += intro.get("audio_duration", intro.get("duration", 5))
        log.info(f"✅ Intro: {total_duration}s")
    
    # 2. NEWS SEGMENTS - Process by cluster
    cluster_idx = 0
    for cluster_theme, cluster_items in clusters.items():
        cluster_idx += 1
        
        if len(cluster_items) > 1:
            # Multi-source topic - create enriched segment
            log.info(f"🔥 Processing MULTI-SOURCE cluster {cluster_idx}: {cluster_theme[:50]}... ({len(cluster_items)} articles)")
            
            segment = get_or_create_multi_source_segment(
                articles=cluster_items,
                cluster_theme=cluster_theme,
                target_date=target_date,
                edition=edition,
                format_config=config
            )
            
            if segment:
                segments.append({
                    "type": "news",
                    "audio_path": segment.get("audio_path"),
                    "audio_url": segment.get("audio_url"),
                    "duration": segment.get("duration", 90),
                    "title": f"[MULTI] {cluster_theme}",
                    "url": cluster_items[0]["url"]
                })
                total_duration += segment.get("duration", 90)
                
                # Add all sources
                for article in cluster_items:
                    sources_data.append({
                        "title": article.get("title"),
                        "url": article.get("url"),
                        "domain": urlparse(article["url"]).netloc.replace("www.", ""),
                        "cluster": cluster_theme
                    })
                
                # Collect digests for all articles in cluster
                for digest_item in segment.get("digests", []):
                    digests_data.append(digest_item)
                
                log.info(f"📊 Multi-source segment: {segment.get('duration', 0)}s | Total: {total_duration}s")
        else:
            # Single source - regular processing
            item = cluster_items[0]
            log.info(f"🎯 Processing article {cluster_idx}: {item.get('title', 'No title')[:50]}...")
            
            segment = get_or_create_segment(
                url=item["url"],
                title=item.get("title", ""),
                topic_slug=item.get("keyword", "general"),
                target_date=target_date,
                edition=edition,
                format_config=config
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
        title = f"Keernel {format_type.title()} - {target_date.strftime('%d %B %Y')}"
        
        episode = supabase.table("episodes").insert({
            "user_id": user_id,
            "title": title,
            "audio_url": final_url,
            "audio_duration": total_duration,
            "sources_data": sources_data,
            "summary_text": f"Keernel {format_type} avec {len(sources_data)} sources"
        }).execute()
        
        # Mark USED articles as processed
        processed_urls = [s["url"] for s in sources_data]
        supabase.table("content_queue") \
            .update({"status": "processed"}) \
            .eq("user_id", user_id) \
            .in_("url", processed_urls) \
            .execute()
        
        # CLEAR ALL remaining pending articles
        clear_result = supabase.table("content_queue") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        
        cleared_count = len(clear_result.data) if clear_result.data else 0
        log.info(f"🗑️ Cleared {cleared_count} stale pending articles")
        
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
            
            log.info(f"✅ EPISODE CREATED: {total_duration}s, {len(sources_data)} sources")
            return episode.data[0]
        
        return None
        
    except Exception as e:
        log.error(f"Episode creation failed: {e}")
        return None


def stitch_segments(segments: list, user_id: str, target_date: date) -> Optional[str]:
    """Combine all segments into final audio file."""
    try:
        from pydub import AudioSegment
        import httpx
        
        combined = AudioSegment.empty()
        transition = AudioSegment.silent(duration=500)
        
        for seg in segments:
            audio_path = seg.get("audio_path")
            audio_url = seg.get("audio_url")
            
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
            
            if audio_path and os.path.exists(audio_path):
                try:
                    audio = AudioSegment.from_mp3(audio_path)
                    combined += audio
                    combined += transition
                except Exception as e:
                    log.warning(f"Failed to load segment: {e}")
        
        if len(combined) == 0:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"podcast_{timestamp}.mp3")
        combined.export(output_path, format="mp3", bitrate="192k")
        
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
