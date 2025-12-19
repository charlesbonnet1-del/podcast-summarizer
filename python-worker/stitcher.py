"""
Stitcher - Audio Assembly Engine for Singular Daily

Assembles personalized podcasts from multiple segments:
- Segment A: Personalized intro ("Bonjour [Prénom]") - cached by first_name
- Segment B: Daily ephemeride (date, saint, historical fact) - shared by all
- Segment C: Deep Dives (manual URLs) - priority content
- Segment D: Flash News (keyword-based) - filler to reach target duration

Uses FFmpeg for audio concatenation.
"""
import os
import re
import tempfile
import subprocess
from datetime import datetime, date
from typing import Optional
from urllib.parse import urlparse
import unicodedata

import structlog
from dotenv import load_dotenv

from db import supabase
from generator import generate_audio, groq_client
from extractor import extract_content

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONSTANTS
# ============================================

WORDS_PER_MINUTE = 150
INTRO_DURATION_SEC = 5  # Approximate duration of intro
EPHEMERIDE_DURATION_SEC = 45  # Approximate duration of ephemeride

# Target durations in minutes
DURATION_OPTIONS = [5, 15, 20, 30]


# ============================================
# UTILITY FUNCTIONS
# ============================================

def normalize_first_name(name: str) -> str:
    """
    Normalize first name for cache key.
    Lowercase, remove accents, remove special chars.
    """
    if not name:
        return "ami"  # Default
    
    # Lowercase
    name = name.lower().strip()
    
    # Remove accents
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    
    # Keep only alphanumeric
    name = re.sub(r'[^a-z0-9]', '', name)
    
    return name or "ami"


def estimate_duration_from_words(word_count: int) -> int:
    """Estimate audio duration in seconds from word count."""
    minutes = word_count / WORDS_PER_MINUTE
    return int(minutes * 60)


def estimate_words_for_duration(target_seconds: int) -> int:
    """Estimate word count needed for target duration."""
    minutes = target_seconds / 60
    return int(minutes * WORDS_PER_MINUTE)


def get_domain(url: str) -> str:
    """Extract domain name from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        return domain
    except:
        return "source"


# ============================================
# SEGMENT A: PERSONALIZED INTRO
# ============================================

def get_or_create_intro(first_name: str) -> dict | None:
    """
    Get cached intro for first_name, or create it if not exists.
    Returns {"audio_url": str, "duration": int} or None.
    """
    normalized = normalize_first_name(first_name)
    
    # Check cache
    try:
        result = supabase.table("cached_intros") \
            .select("*") \
            .eq("first_name_normalized", normalized) \
            .single() \
            .execute()
        
        if result.data:
            log.info("Using cached intro", first_name=normalized)
            return {
                "audio_url": result.data["audio_url"],
                "duration": result.data["audio_duration"]
            }
    except:
        pass  # Not found, will create
    
    # Generate new intro
    log.info("Generating new intro", first_name=normalized)
    
    # Use display name (capitalize first letter)
    display_name = first_name.strip().title() if first_name else "Ami"
    intro_script = f"Bonjour {display_name}, bienvenue dans votre podcast personnalisé."
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"intro_{normalized}_{timestamp}.mp3")
    
    audio_path = generate_audio(intro_script, voice="alloy", output_path=temp_path)
    
    if not audio_path:
        log.error("Failed to generate intro audio", first_name=normalized)
        return None
    
    # Upload to storage
    try:
        filename = f"intros/welcome_{normalized}.mp3"
        
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        
        # Upload to Supabase Storage
        supabase.storage.from_("audio").upload(
            filename,
            audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        
        # Get public URL
        audio_url = supabase.storage.from_("audio").get_public_url(filename)
        
        # Get duration
        from generator import get_audio_duration
        duration = get_audio_duration(audio_path)
        
        # Save to cache
        supabase.table("cached_intros").upsert({
            "first_name_normalized": normalized,
            "audio_url": audio_url,
            "audio_duration": duration
        }).execute()
        
        # Cleanup temp file
        os.remove(audio_path)
        
        log.info("Intro cached", first_name=normalized, duration=duration)
        return {"audio_url": audio_url, "duration": duration}
        
    except Exception as e:
        log.error("Failed to cache intro", error=str(e))
        if os.path.exists(audio_path):
            os.remove(audio_path)
        return None


# ============================================
# SEGMENT B: DAILY EPHEMERIDE
# ============================================

def get_or_create_ephemeride(target_date: date = None) -> dict | None:
    """
    Get or create daily ephemeride (date, saint, historical fact).
    Shared by all users for the same day.
    Returns {"audio_url": str, "duration": int, "script": str} or None.
    """
    if target_date is None:
        target_date = date.today()
    
    date_str = target_date.isoformat()
    
    # Check cache
    try:
        result = supabase.table("daily_ephemeride") \
            .select("*") \
            .eq("date", date_str) \
            .single() \
            .execute()
        
        if result.data and result.data.get("audio_url"):
            log.info("Using cached ephemeride", date=date_str)
            return {
                "audio_url": result.data["audio_url"],
                "duration": result.data["audio_duration"],
                "script": result.data["script"]
            }
    except:
        pass  # Not found, will create
    
    # Generate ephemeride script with LLM
    log.info("Generating ephemeride", date=date_str)
    
    if not groq_client:
        log.error("Groq client not available")
        return None
    
    # Format date in French
    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    except:
        pass
    
    formatted_date = target_date.strftime("%A %d %B %Y").capitalize()
    
    prompt = f"""Génère une éphéméride radio pour le {formatted_date}.

STRUCTURE (environ 60 mots, style radio dynamique) :
1. La date du jour, joliment formulée
2. Le saint du jour (ou fête laïque)
3. UN fait historique marquant pour cette date (surprenant ou mémorable)

STYLE :
- Phrases courtes et percutantes
- Présent de narration
- Pas de listes, que du texte fluide
- Termine par une transition vers le contenu ("Et maintenant, vos actualités...")

Génère UNIQUEMENT le texte, prêt à être lu."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Tu es un animateur radio français dynamique. Tu génères des éphémérides courtes et engageantes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=200
        )
        
        script = response.choices[0].message.content.strip()
        word_count = len(script.split())
        
        log.info("Ephemeride script generated", words=word_count)
        
    except Exception as e:
        log.error("Failed to generate ephemeride script", error=str(e))
        return None
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"ephemeride_{date_str}_{timestamp}.mp3")
    
    audio_path = generate_audio(script, voice="alloy", output_path=temp_path)
    
    if not audio_path:
        log.error("Failed to generate ephemeride audio")
        return None
    
    # Upload to storage
    try:
        filename = f"ephemerides/ephemeride_{date_str}.mp3"
        
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            filename,
            audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        
        audio_url = supabase.storage.from_("audio").get_public_url(filename)
        
        from generator import get_audio_duration
        duration = get_audio_duration(audio_path)
        
        # Save to cache
        supabase.table("daily_ephemeride").upsert({
            "date": date_str,
            "script": script,
            "audio_url": audio_url,
            "audio_duration": duration
        }).execute()
        
        os.remove(audio_path)
        
        log.info("Ephemeride cached", date=date_str, duration=duration)
        return {"audio_url": audio_url, "duration": duration, "script": script}
        
    except Exception as e:
        log.error("Failed to cache ephemeride", error=str(e))
        if os.path.exists(audio_path):
            os.remove(audio_path)
        return None


# ============================================
# SEGMENT C & D: CONTENT SEGMENTS
# ============================================

def get_or_create_segment(url: str, segment_type: str, target_words: int = 300) -> dict | None:
    """
    Get cached segment for URL, or create it.
    segment_type: 'deep_dive' (longer, more detailed) or 'flash_news' (shorter)
    Returns {"audio_url": str, "duration": int, "title": str, "script": str} or None.
    """
    today = date.today().isoformat()
    
    # Check cache
    try:
        result = supabase.table("processed_segments") \
            .select("*") \
            .eq("url", url) \
            .eq("date", today) \
            .single() \
            .execute()
        
        if result.data and result.data.get("audio_url"):
            log.info("Using cached segment", url=url[:50])
            return {
                "audio_url": result.data["audio_url"],
                "duration": result.data["audio_duration"],
                "title": result.data["title"],
                "script": result.data["script"]
            }
    except:
        pass  # Not found, will create
    
    # Extract content
    log.info("Processing content", url=url[:60], type=segment_type)
    
    extraction = extract_content(url)
    if not extraction:
        log.warning("Failed to extract content", url=url[:60])
        return None
    
    source_type, title, content = extraction
    source_name = get_domain(url)
    
    # Generate script with LLM
    if not groq_client:
        log.error("Groq client not available")
        return None
    
    if segment_type == "deep_dive":
        style_instruction = """STYLE DEEP DIVE :
- Développe le sujet en profondeur (environ {words} mots)
- Trouve l'angle intéressant, l'insight surprenant
- Cite la source naturellement ("D'après {source}...")
- Structure : accroche → développement → conclusion avec perspective"""
    else:
        style_instruction = """STYLE FLASH NEWS :
- Synthèse rapide et percutante (environ {words} mots)
- Va droit au but, l'essentiel uniquement
- Cite la source ("Selon {source}...")
- Une phrase d'accroche, les faits clés, une phrase de conclusion"""
    
    prompt = f"""Transforme ce contenu en script audio radio.

SOURCE : {source_name}
TITRE : {title}

CONTENU :
{content[:4000]}

{style_instruction.format(words=target_words, source=source_name)}

RÈGLES ABSOLUES :
- Écris pour l'oreille. Phrases courtes. Sujet-Verbe-Complément.
- Présent de narration, ton dynamique
- PAS de listes à puces, que du texte fluide
- Ne sois pas neutre : trouve ce qui est intéressant ou surprenant

Génère UNIQUEMENT le script, prêt à être lu."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Tu es un journaliste radio français. Tu écris des scripts audio dynamiques et engageants."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=target_words * 2
        )
        
        script = response.choices[0].message.content.strip()
        word_count = len(script.split())
        
        log.info("Segment script generated", words=word_count, type=segment_type)
        
    except Exception as e:
        log.error("Failed to generate segment script", error=str(e))
        return None
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title[:30])
    temp_path = os.path.join(tempfile.gettempdir(), f"segment_{safe_title}_{timestamp}.mp3")
    
    audio_path = generate_audio(script, voice="alloy", output_path=temp_path)
    
    if not audio_path:
        log.error("Failed to generate segment audio")
        return None
    
    # Upload to storage
    try:
        filename = f"segments/{today}/{segment_type}_{timestamp}.mp3"
        
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            filename,
            audio_data,
            {"content-type": "audio/mpeg"}
        )
        
        audio_url = supabase.storage.from_("audio").get_public_url(filename)
        
        from generator import get_audio_duration
        duration = get_audio_duration(audio_path)
        
        # Save to cache
        supabase.table("processed_segments").upsert({
            "url": url,
            "date": today,
            "segment_type": segment_type,
            "title": title,
            "script": script,
            "audio_url": audio_url,
            "audio_duration": duration,
            "word_count": word_count,
            "source_name": source_name
        }, on_conflict="url,date").execute()
        
        os.remove(audio_path)
        
        log.info("Segment cached", title=title[:40], duration=duration)
        return {
            "audio_url": audio_url,
            "duration": duration,
            "title": title,
            "script": script
        }
        
    except Exception as e:
        log.error("Failed to cache segment", error=str(e))
        if os.path.exists(audio_path):
            os.remove(audio_path)
        return None


# ============================================
# FFMPEG STITCHER
# ============================================

def download_audio(url: str, output_path: str) -> bool:
    """Download audio file from URL."""
    import httpx
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        log.error("Failed to download audio", url=url[:60], error=str(e))
        return False


def stitch_audio_segments(segment_paths: list[str], output_path: str) -> bool:
    """
    Concatenate multiple MP3 files using FFmpeg.
    Returns True if successful.
    """
    if not segment_paths:
        return False
    
    # Create concat file
    concat_file = os.path.join(tempfile.gettempdir(), "concat_list.txt")
    
    try:
        with open(concat_file, 'w') as f:
            for path in segment_paths:
                # Escape single quotes in path
                escaped = path.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
        
        # Run FFmpeg
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            log.error("FFmpeg failed", stderr=result.stderr[:500])
            return False
        
        log.info("Audio stitched successfully", output=output_path)
        return True
        
    except Exception as e:
        log.error("Stitching failed", error=str(e))
        return False
    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


# ============================================
# MAIN ASSEMBLY FUNCTION
# ============================================

def assemble_podcast(
    user_id: str,
    first_name: str,
    manual_urls: list[str],  # High priority content
    auto_urls: list[str],    # News to fill remaining time
    target_duration: int = 15  # minutes
) -> dict | None:
    """
    Assemble a complete podcast for a user.
    
    Returns {
        "audio_url": str,
        "duration": int,
        "segments": list[dict],
        "sources_data": list[dict]
    } or None.
    """
    log.info("Assembling podcast", 
             user_id=user_id[:8], 
             target_min=target_duration,
             manual_count=len(manual_urls),
             auto_count=len(auto_urls))
    
    target_seconds = target_duration * 60
    segments = []
    sources_data = []
    total_duration = 0
    temp_files = []
    
    try:
        # =====================
        # SEGMENT A: INTRO
        # =====================
        intro = get_or_create_intro(first_name)
        if intro:
            temp_path = os.path.join(tempfile.gettempdir(), f"dl_intro_{user_id[:8]}.mp3")
            if download_audio(intro["audio_url"], temp_path):
                segments.append({"type": "intro", "path": temp_path, "duration": intro["duration"]})
                temp_files.append(temp_path)
                total_duration += intro["duration"]
        
        # =====================
        # SEGMENT B: EPHEMERIDE
        # =====================
        ephemeride = get_or_create_ephemeride()
        if ephemeride:
            temp_path = os.path.join(tempfile.gettempdir(), f"dl_ephemeride_{user_id[:8]}.mp3")
            if download_audio(ephemeride["audio_url"], temp_path):
                segments.append({"type": "ephemeride", "path": temp_path, "duration": ephemeride["duration"]})
                temp_files.append(temp_path)
                total_duration += ephemeride["duration"]
        
        # Calculate remaining time for content
        remaining_seconds = target_seconds - total_duration
        
        # =====================
        # SEGMENT C: DEEP DIVES (Manual URLs - Priority)
        # =====================
        deep_dive_budget = int(remaining_seconds * 0.7)  # 70% for manual content
        deep_dive_used = 0
        
        for url in manual_urls:
            if deep_dive_used >= deep_dive_budget:
                break
            
            # Calculate words based on remaining budget
            remaining_budget = deep_dive_budget - deep_dive_used
            target_words = estimate_words_for_duration(min(remaining_budget, 180))  # Max 3 min per article
            target_words = max(200, min(target_words, 500))  # Between 200-500 words
            
            segment = get_or_create_segment(url, "deep_dive", target_words)
            if segment:
                temp_path = os.path.join(tempfile.gettempdir(), f"dl_dd_{len(segments)}_{user_id[:8]}.mp3")
                if download_audio(segment["audio_url"], temp_path):
                    segments.append({"type": "deep_dive", "path": temp_path, "duration": segment["duration"]})
                    temp_files.append(temp_path)
                    deep_dive_used += segment["duration"]
                    total_duration += segment["duration"]
                    
                    sources_data.append({
                        "title": segment["title"],
                        "url": url,
                        "domain": get_domain(url),
                        "type": "deep_dive"
                    })
        
        # =====================
        # SEGMENT D: FLASH NEWS (Fill remaining time)
        # =====================
        flash_budget = target_seconds - total_duration
        flash_used = 0
        
        for url in auto_urls:
            if flash_used >= flash_budget or total_duration >= target_seconds:
                break
            
            # Short segments for news (60-90 seconds each)
            remaining_budget = flash_budget - flash_used
            target_words = estimate_words_for_duration(min(remaining_budget, 90))
            target_words = max(100, min(target_words, 200))  # Between 100-200 words
            
            segment = get_or_create_segment(url, "flash_news", target_words)
            if segment:
                temp_path = os.path.join(tempfile.gettempdir(), f"dl_fn_{len(segments)}_{user_id[:8]}.mp3")
                if download_audio(segment["audio_url"], temp_path):
                    segments.append({"type": "flash_news", "path": temp_path, "duration": segment["duration"]})
                    temp_files.append(temp_path)
                    flash_used += segment["duration"]
                    total_duration += segment["duration"]
                    
                    sources_data.append({
                        "title": segment["title"],
                        "url": url,
                        "domain": get_domain(url),
                        "type": "flash_news"
                    })
        
        # =====================
        # STITCH ALL SEGMENTS
        # =====================
        if len(segments) < 2:
            log.warning("Not enough segments to create podcast")
            return None
        
        # Order: intro → ephemeride → deep_dives → flash_news
        ordered_paths = [s["path"] for s in segments]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"podcast_{user_id[:8]}_{timestamp}.mp3")
        
        if not stitch_audio_segments(ordered_paths, output_path):
            log.error("Failed to stitch podcast")
            return None
        
        # Upload final podcast
        filename = f"{user_id}/episode_{timestamp}.mp3"
        
        with open(output_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            filename,
            audio_data,
            {"content-type": "audio/mpeg"}
        )
        
        audio_url = supabase.storage.from_("audio").get_public_url(filename)
        
        from generator import get_audio_duration
        final_duration = get_audio_duration(output_path)
        
        os.remove(output_path)
        
        log.info("Podcast assembled", 
                 duration_sec=final_duration, 
                 target_sec=target_seconds,
                 segments=len(segments))
        
        return {
            "audio_url": audio_url,
            "duration": final_duration,
            "segments": [{"type": s["type"], "duration": s["duration"]} for s in segments],
            "sources_data": sources_data
        }
        
    except Exception as e:
        log.error("Podcast assembly failed", error=str(e))
        return None
    
    finally:
        # Cleanup temp files
        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass


# ============================================
# ENTRY POINT FOR WORKER
# ============================================

def generate_podcast_for_user(user_id: str) -> dict | None:
    """
    Main entry point: generate a complete podcast for a user.
    Fetches user preferences, content queue, and assembles the podcast.
    """
    log.info("Starting podcast generation", user_id=user_id[:8])
    
    # Get user info
    try:
        user_result = supabase.table("users") \
            .select("first_name, settings") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if not user_result.data:
            log.error("User not found", user_id=user_id[:8])
            return None
        
        first_name = user_result.data.get("first_name") or "Ami"
        settings = user_result.data.get("settings") or {}
        target_duration = settings.get("target_duration", 15)
        
    except Exception as e:
        log.error("Failed to get user", error=str(e))
        return None
    
    # Get pending content from queue
    try:
        queue_result = supabase.table("content_queue") \
            .select("url, priority, source") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .order("priority", desc=True) \
            .order("created_at") \
            .execute()
        
        if not queue_result.data:
            log.warning("No pending content", user_id=user_id[:8])
            return None
        
        # Separate manual (high priority) from auto
        manual_urls = [item["url"] for item in queue_result.data if item.get("priority") == "high" or item.get("source") == "manual"]
        auto_urls = [item["url"] for item in queue_result.data if item.get("priority") != "high" and item.get("source") != "manual"]
        
    except Exception as e:
        log.error("Failed to get queue", error=str(e))
        return None
    
    # Assemble podcast
    result = assemble_podcast(
        user_id=user_id,
        first_name=first_name,
        manual_urls=manual_urls,
        auto_urls=auto_urls,
        target_duration=target_duration
    )
    
    if not result:
        # Mark items as failed
        supabase.table("content_queue") \
            .update({"status": "failed"}) \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        return None
    
    # Create episode record
    try:
        today = date.today()
        title = f"{first_name}'s Daily - {today.strftime('%d %B %Y')}"
        
        episode = supabase.table("episodes").insert({
            "user_id": user_id,
            "title": title,
            "audio_url": result["audio_url"],
            "audio_duration": result["duration"],
            "sources_data": result["sources_data"],
            "summary_text": f"Episode avec {len(result['sources_data'])} sources"
        }).execute()
        
        # Mark queue items as processed
        supabase.table("content_queue") \
            .update({"status": "processed"}) \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        
        log.info("Episode created", 
                 episode_id=episode.data[0]["id"] if episode.data else None,
                 duration=result["duration"])
        
        return episode.data[0] if episode.data else None
        
    except Exception as e:
        log.error("Failed to create episode", error=str(e))
        return None
