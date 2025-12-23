"""
Keernel Stitcher V2 - Lego Architecture

ARCHITECTURE LEGO:
1. Intro personnalisée (généré à la volée, ~5sec)
2. Segments news (CACHÉS par topic/date/edition)
3. Outro mutualisée (~5sec)

Le cache permet de réutiliser les segments audio entre utilisateurs.
Un segment = 1 article = 1 fichier audio (~60-90sec)

Coût théorique:
- Sans cache: 100 users * 10 articles * $0.01 = $10/jour
- Avec cache: 50 articles uniques * $0.01 = $0.50/jour
- Économie: 95%
"""
import os
import hashlib
import tempfile
from datetime import datetime, date, timezone
from typing import Optional
import structlog
from dotenv import load_dotenv

from db import supabase
from generator import generate_audio, groq_client, get_audio_duration
from extractor import extract_content

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONSTANTS
# ============================================

WORDS_PER_MINUTE = 150
SEGMENT_CACHE_DAYS = 7

# Format configurations
FORMAT_CONFIG = {
    "flash": {
        "duration": 4,
        "max_articles": 4,
        "words_per_article": 100,
        "style": "ultra-concis"
    },
    "digest": {
        "duration": 15,
        "max_articles": 8,
        "words_per_article": 200,
        "style": "approfondi"
    }
}

# ============================================
# SEGMENT SCRIPT PROMPT
# ============================================

SEGMENT_PROMPT = """Tu es journaliste radio. Écris un segment de {word_count} mots sur cet article.

## RÈGLES
- Style: {style}
- Commence DIRECTEMENT par l'info (pas de "Passons à", "Voici")
- Phrases courtes (< 20 mots)
- Phonétique TTS: "LLM" → "elle-elle-aime", "CEO" → "si-i-o"
- JAMAIS de markdown ou listes

## SOURCE
Titre: {title}
{content}

## SCRIPT ({word_count} mots, style {style}):"""


# ============================================
# SEGMENT CACHING
# ============================================

def get_content_hash(url: str, content: str) -> str:
    """Génère un hash unique pour le contenu."""
    data = f"{url}:{content[:1000]}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def get_cached_segment(content_hash: str, target_date: date, edition: str) -> Optional[dict]:
    """
    Vérifie si un segment audio existe déjà en cache.
    
    Returns:
        dict with audio_url, duration, script_text if found
        None if not cached
    """
    try:
        result = supabase.table("audio_segments") \
            .select("id, audio_url, audio_duration, script_text") \
            .eq("content_hash", content_hash) \
            .eq("date", target_date.isoformat()) \
            .eq("edition", edition) \
            .single() \
            .execute()
        
        if result.data:
            # Incrémenter le compteur d'utilisation
            supabase.table("audio_segments") \
                .update({"use_count": result.data.get("use_count", 0) + 1}) \
                .eq("id", result.data["id"]) \
                .execute()
            
            log.info("Cache HIT", hash=content_hash[:8])
            return result.data
        
        return None
        
    except Exception as e:
        log.debug("Cache miss or error", error=str(e))
        return None


def cache_segment(
    content_hash: str,
    topic_slug: str,
    target_date: date,
    edition: str,
    source_url: str,
    source_title: str,
    script_text: str,
    audio_url: str,
    audio_duration: int
) -> bool:
    """
    Sauvegarde un segment audio en cache.
    """
    try:
        from urllib.parse import urlparse
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
        
        log.info("Segment cached", hash=content_hash[:8], topic=topic_slug)
        return True
        
    except Exception as e:
        log.warning("Failed to cache segment", error=str(e))
        return False


# ============================================
# SEGMENT GENERATION
# ============================================

def generate_segment_script(
    title: str,
    content: str,
    word_count: int = 150,
    style: str = "concis"
) -> Optional[str]:
    """Génère le script pour un segment."""
    if not groq_client:
        log.error("Groq client not available")
        return None
    
    try:
        prompt = SEGMENT_PROMPT.format(
            word_count=word_count,
            style=style,
            title=title,
            content=content[:4000]
        )
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        script = response.choices[0].message.content.strip()
        actual_words = len(script.split())
        log.info("Segment script generated", words=actual_words, target=word_count)
        
        return script
        
    except Exception as e:
        log.error("Failed to generate segment script", error=str(e))
        return None


def get_or_create_segment(
    url: str,
    title: str,
    topic_slug: str,
    target_date: date,
    edition: str,
    format_config: dict
) -> Optional[dict]:
    """
    Récupère ou crée un segment audio pour un article.
    
    C'est le cœur de l'architecture Lego:
    1. Extract content
    2. Check cache
    3. Generate if missing
    4. Return segment info
    """
    log.info("Processing segment", url=url[:50])
    
    # 1. Extract content
    extraction_result = extract_content(url)
    if not extraction_result:
        log.warning("Failed to extract content", url=url[:50])
        return None
    
    source_type, extracted_title, content = extraction_result
    
    if not content or len(content) < 100:
        log.warning("Content too short", url=url[:50], length=len(content) if content else 0)
        return None
    
    # Use extracted title if original is empty
    if not title and extracted_title:
        title = extracted_title
    
    # 2. Generate hash and check cache
    content_hash = get_content_hash(url, content)
    
    cached = get_cached_segment(content_hash, target_date, edition)
    if cached:
        return {
            "audio_url": cached["audio_url"],
            "duration": cached["audio_duration"],
            "script": cached["script_text"],
            "title": title,
            "url": url,
            "cached": True
        }
    
    # 3. Generate script
    script = generate_segment_script(
        title=title,
        content=content,
        word_count=format_config["words_per_article"],
        style=format_config["style"]
    )
    
    if not script:
        return None
    
    # 4. Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"segment_{content_hash[:8]}_{timestamp}.mp3")
    
    audio_path = generate_audio(script, output_path=temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    # 5. Upload to storage
    remote_path = f"segments/{target_date.isoformat()}/{edition}/{content_hash[:16]}.mp3"
    audio_url = upload_segment(audio_path, remote_path)
    
    if not audio_url:
        # Fallback: keep local path
        audio_url = audio_path
    
    # 6. Cache the segment
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
    
    return {
        "audio_url": audio_url,
        "audio_path": audio_path,
        "duration": duration,
        "script": script,
        "title": title,
        "url": url,
        "cached": False
    }


def upload_segment(local_path: str, remote_path: str) -> Optional[str]:
    """Upload segment to Supabase storage."""
    try:
        with open(local_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            remote_path,
            audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        
        return supabase.storage.from_("audio").get_public_url(remote_path)
    except Exception as e:
        log.warning("Failed to upload segment", error=str(e))
        return None


# ============================================
# INTRO/OUTRO (Personnalisés ou cachés)
# ============================================

def get_or_create_intro(first_name: str) -> Optional[dict]:
    """Get or create personalized intro."""
    from stitcher import get_or_create_intro as legacy_intro
    return legacy_intro(first_name)


def get_or_create_outro() -> Optional[dict]:
    """Get cached outro or create standard one."""
    try:
        result = supabase.table("cached_outros") \
            .select("audio_url, audio_duration") \
            .eq("outro_type", "standard") \
            .single() \
            .execute()
        
        if result.data:
            log.info("Using cached outro")
            return result.data
    except:
        pass
    
    # Generate standard outro
    outro_script = "C'était votre Keernel du jour. À demain pour de nouvelles informations."
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"outro_{timestamp}.mp3")
    
    audio_path = generate_audio(outro_script, output_path=temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    # Upload and cache
    remote_path = "outros/standard.mp3"
    audio_url = upload_segment(audio_path, remote_path)
    
    if audio_url:
        try:
            supabase.table("cached_outros").upsert({
                "outro_type": "standard",
                "audio_url": audio_url,
                "audio_duration": duration,
                "script_text": outro_script
            }).execute()
        except:
            pass
    
    return {
        "audio_url": audio_url or audio_path,
        "audio_duration": duration
    }


# ============================================
# LEGO ASSEMBLY
# ============================================

def assemble_lego_podcast(
    user_id: str,
    target_duration: int = 15,
    format_type: str = "digest"
) -> Optional[dict]:
    """
    Assemble podcast using Lego architecture.
    
    Structure:
    [Intro Perso] + [Segment 1] + [Segment 2] + ... + [Outro]
    
    Les segments sont cachés et réutilisés entre utilisateurs.
    """
    log.info("Assembling Lego podcast", user_id=user_id[:8], format=format_type, target_min=target_duration)
    
    # Get format config
    config = FORMAT_CONFIG.get(format_type, FORMAT_CONFIG["digest"])
    max_articles = config["max_articles"]
    
    # Get user info
    try:
        user_result = supabase.table("users") \
            .select("first_name") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        first_name = user_result.data.get("first_name", "Ami") if user_result.data else "Ami"
    except:
        first_name = "Ami"
    
    # Get pending content
    try:
        # Priorité: gsheet_rss > bing_news
        queue_result = supabase.table("content_queue") \
            .select("url, title, keyword, source, vertical_id") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .order("created_at") \
            .limit(max_articles * 2) \
            .execute()
        
        if not queue_result.data:
            log.warning("No pending content")
            return None
        
        # Prioritize sources
        gsheet_items = [i for i in queue_result.data if i.get("source") in ("gsheet_rss", "rss", "library")]
        bing_items = [i for i in queue_result.data if i.get("source") not in ("gsheet_rss", "rss", "library")]
        
        # GSheet first, then Bing
        items = (gsheet_items + bing_items)[:max_articles]
        
        log.info("Content selected", gsheet=len(gsheet_items), bing=len(bing_items), selected=len(items))
        
    except Exception as e:
        log.error("Failed to get queue", error=str(e))
        return None
    
    # Determine date/edition
    target_date = date.today()
    edition = "morning" if datetime.now().hour < 14 else "evening"
    
    # ============================================
    # ASSEMBLE SEGMENTS
    # ============================================
    
    segments = []
    sources_data = []
    total_duration = 0
    cache_hits = 0
    cache_misses = 0
    
    # 1. INTRO
    intro = get_or_create_intro(first_name)
    if intro:
        segments.append({
            "type": "intro",
            "audio_path": intro.get("local_path"),
            "audio_url": intro.get("audio_url"),
            "duration": intro.get("duration", 5)
        })
        total_duration += intro.get("duration", 5)
    
    # 2. NEWS SEGMENTS (avec cache)
    for item in items:
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
            
            if segment.get("cached"):
                cache_hits += 1
            else:
                cache_misses += 1
            
            sources_data.append({
                "title": segment.get("title"),
                "url": segment.get("url"),
                "domain": extract_domain(segment.get("url", ""))
            })
            
            # Check duration limit
            target_seconds = target_duration * 60
            if total_duration >= target_seconds - 30:
                log.info("Duration target reached", current=total_duration, target=target_seconds)
                break
    
    if not sources_data:
        log.warning("No segments generated")
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
    
    log.info("Segments assembled", 
             total=len(segments), 
             duration=total_duration,
             cache_hits=cache_hits,
             cache_misses=cache_misses)
    
    # ============================================
    # STITCH AUDIO FILES
    # ============================================
    
    final_audio_url = stitch_segments(segments, user_id, target_date)
    
    if not final_audio_url:
        log.error("Failed to stitch segments")
        return None
    
    # ============================================
    # CREATE EPISODE
    # ============================================
    
    try:
        title = f"Keernel {format_type.title()} - {target_date.strftime('%d %B %Y')}"
        
        episode = supabase.table("episodes").insert({
            "user_id": user_id,
            "title": title,
            "audio_url": final_audio_url,
            "audio_duration": total_duration,
            "sources_data": sources_data,
            "summary_text": f"Keernel {format_type} avec {len(sources_data)} sources"
        }).execute()
        
        # Mark content as processed
        processed_urls = [s["url"] for s in sources_data]
        supabase.table("content_queue") \
            .update({"status": "processed"}) \
            .eq("user_id", user_id) \
            .in_("url", processed_urls) \
            .execute()
        
        # Record segment composition
        if episode.data:
            episode_id = episode.data[0]["id"]
            record_episode_composition(episode_id, segments)
            
            log.info("Episode created", 
                    episode_id=episode_id,
                    format=format_type,
                    cache_savings=f"{cache_hits}/{cache_hits+cache_misses}")
            
            return episode.data[0]
        
        return None
        
    except Exception as e:
        log.error("Failed to create episode", error=str(e))
        return None


def stitch_segments(segments: list, user_id: str, target_date: date) -> Optional[str]:
    """
    Combine tous les segments audio en un fichier final.
    """
    try:
        from pydub import AudioSegment
        import httpx
        
        combined = AudioSegment.empty()
        
        for seg in segments:
            audio_path = seg.get("audio_path")
            audio_url = seg.get("audio_url")
            
            # Download if URL only
            if not audio_path and audio_url:
                audio_path = os.path.join(tempfile.gettempdir(), f"temp_{hash(audio_url)}.mp3")
                try:
                    response = httpx.get(audio_url, timeout=30, follow_redirects=True)
                    response.raise_for_status()
                    with open(audio_path, 'wb') as f:
                        f.write(response.content)
                except Exception as e:
                    log.warning("Failed to download segment", error=str(e))
                    continue
            
            if audio_path and os.path.exists(audio_path):
                try:
                    audio = AudioSegment.from_mp3(audio_path)
                    combined += audio
                except Exception as e:
                    log.warning("Failed to load segment", error=str(e))
        
        if len(combined) == 0:
            return None
        
        # Export final
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = os.path.join(tempfile.gettempdir(), f"keernel_{user_id[:8]}_{timestamp}.mp3")
        combined.export(final_path, format="mp3", bitrate="128k")
        
        # Upload
        remote_path = f"episodes/{user_id}/{target_date.isoformat()}/keernel.mp3"
        
        with open(final_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            remote_path,
            audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        
        return supabase.storage.from_("audio").get_public_url(remote_path)
        
    except Exception as e:
        log.error("Failed to stitch segments", error=str(e))
        return None


def record_episode_composition(episode_id: str, segments: list):
    """Enregistre quels segments composent l'épisode."""
    try:
        for i, seg in enumerate(segments):
            supabase.table("episode_segments").insert({
                "episode_id": episode_id,
                "segment_type": seg.get("type"),
                "position": i,
                "duration": seg.get("duration")
            }).execute()
    except Exception as e:
        log.warning("Failed to record composition", error=str(e))


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except:
        return "unknown"
