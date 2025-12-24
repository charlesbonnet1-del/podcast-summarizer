"""
Keernel Stitcher V2 - COMPLETE REWRITE

FIXES APPLIED:
1. DIALOGUE: Each segment is a dialogue between Breeze [A] and Vale [B]
2. DURATION: flash=4min (600 words), digest=15min (2000 words) 
3. SOURCE DIVERSITY: Diversify by topic/vertical, not just by source type
4. SOURCE CITATION: Each segment mentions the source name
5. TTS SPEED: 1.05 (natural, not rushed)
6. MULTIPLE TOPICS: Ensure we cover different topics user subscribed to
"""
import os
import hashlib
import tempfile
from datetime import datetime, date, timezone
from typing import Optional
from urllib.parse import urlparse
import re

import structlog
from dotenv import load_dotenv

from db import supabase
from extractor import extract_content

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

VOICE_BREEZE = "nova"   # Voice A - Expert
VOICE_VALE = "onyx"     # Voice B - Challenger
TTS_SPEED = 1.05        # Natural speed (1.0 = normal)

WORDS_PER_MINUTE = 150
SEGMENT_CACHE_DAYS = 7

# Format configurations - FIXED DURATIONS
FORMAT_CONFIG = {
    "flash": {
        "duration_minutes": 4,
        "total_words": 600,        # 4 min * 150 wpm
        "max_articles": 3,
        "words_per_article": 200,
        "style": "dynamique et percutant"
    },
    "digest": {
        "duration_minutes": 15,
        "total_words": 2000,       # ~13 min of content + intro/outro
        "max_articles": 6,
        "words_per_article": 350,
        "style": "approfondi et analytique"
    }
}

# ============================================
# DIALOGUE PROMPT - THIS IS THE KEY FIX
# ============================================

DIALOGUE_SEGMENT_PROMPT = """Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.

## LES HÔTES
- BREEZE [A] = Expert qui explique clairement
- VALE [B] = Challenger curieux qui pose des questions

## FORMAT OBLIGATOIRE
Chaque réplique DOIT commencer par [A] ou [B]:

[A]
Breeze parle.

[B]
Vale répond ou questionne.

## RÈGLES STRICTES
1. ALTERNER [A] et [B] - jamais deux [A] ou deux [B] de suite
2. Minimum 4 répliques (2 de chaque)
3. Style oral naturel: "Écoute,", "En fait,", "Tu vois,"
4. Vale pose des QUESTIONS
5. ZÉRO liste, ZÉRO bullet points
6. CITE LA SOURCE au début: "Selon {source}..." ou "D'après {source}..."

## SOURCE
Titre: {title}
Source: {source_name}
Contenu:
{content}

## GÉNÈRE LE DIALOGUE ({word_count} mots, style {style}):"""

# ============================================
# OPENAI & GROQ CLIENTS
# ============================================

from groq import Groq
groq_client = None
if os.getenv("GROQ_API_KEY"):
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    log.info("✅ Groq client initialized")

from openai import OpenAI
openai_client = None
if os.getenv("OPENAI_API_KEY"):
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    log.info("✅ OpenAI client initialized")

# ============================================
# TTS GENERATION
# ============================================

def generate_tts(text: str, voice: str, output_path: str) -> bool:
    """Generate TTS with OpenAI."""
    if not openai_client:
        log.error("❌ OpenAI client not available!")
        return False
    
    try:
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
            speed=TTS_SPEED
        )
        response.stream_to_file(output_path)
        return True
    except Exception as e:
        log.error(f"❌ TTS failed: {e}")
        return False


def get_audio_duration(path: str) -> int:
    """Get audio duration in seconds."""
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_mp3(path)) // 1000
    except:
        return 0

# ============================================
# DIALOGUE PARSING - GUARANTEED ALTERNATION
# ============================================

def parse_dialogue_to_segments(script: str) -> list[dict]:
    """Parse dialogue script into voice segments with GUARANTEED alternation."""
    if not script:
        return []
    
    # Normalize tags
    normalized = script
    replacements = [
        (r'\[VOICE_A\]', '\n[A]\n'),
        (r'\[VOICE_B\]', '\n[B]\n'),
        (r'Breeze\s*:', '\n[A]\n'),
        (r'Vale\s*:', '\n[B]\n'),
        (r'\*\*Breeze\*\*', '\n[A]\n'),
        (r'\*\*Vale\*\*', '\n[B]\n'),
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
            segments.append({'voice': 'A' if i % 2 == 0 else 'B', 'text': para})
    
    # FORCE alternation - GUARANTEES dialogue
    for i in range(len(segments)):
        segments[i]['voice'] = 'A' if i % 2 == 0 else 'B'
    
    return segments


def generate_dialogue_audio(script: str, output_path: str) -> str | None:
    """Generate dialogue audio with BOTH voices."""
    
    segments = parse_dialogue_to_segments(script)
    
    if not segments:
        log.error("❌ No segments!")
        return None
    
    voice_a = sum(1 for s in segments if s['voice'] == 'A')
    voice_b = sum(1 for s in segments if s['voice'] == 'B')
    log.info(f"🎙️ Generating dialogue: {len(segments)} segments, A={voice_a}, B={voice_b}")
    
    audio_files = []
    
    for i, seg in enumerate(segments):
        voice = VOICE_BREEZE if seg['voice'] == 'A' else VOICE_VALE
        seg_path = output_path.replace('.mp3', f'_seg{i:03d}.mp3')
        
        if generate_tts(seg['text'], voice, seg_path):
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
# SCRIPT GENERATION - DIALOGUE FORMAT
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
            
            # Retry with stronger instruction
            prompt += "\n\nATTENTION: Tu DOIS utiliser [A] et [B] pour chaque réplique!"
        
        # Return anyway, fallback will handle it
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
            # Increment use count
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
# SEGMENT CREATION - WITH DIALOGUE
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
    
    # Get source name from URL
    source_name = urlparse(url).netloc.replace("www.", "")
    
    # 2. Check cache
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
            "cached": True
        }
    
    # 3. Generate DIALOGUE script (not monologue!)
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
        "cached": False
    }


# ============================================
# INTRO/OUTRO
# ============================================

def get_or_create_intro(first_name: str) -> Optional[dict]:
    """Get or create personalized intro."""
    from stitcher import get_or_create_intro as legacy_intro
    return legacy_intro(first_name)


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
    
    # Generate outro
    outro_text = "C'était votre Keernel du jour. À demain pour de nouvelles découvertes!"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"outro_{timestamp}.mp3")
    
    if not generate_tts(outro_text, VOICE_BREEZE, temp_path):
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
# CONTENT SELECTION - DIVERSIFY TOPICS
# ============================================

def select_diverse_content(user_id: str, max_articles: int) -> list[dict]:
    """
    Select content ensuring DIVERSITY across topics.
    
    Instead of just taking first N items, we:
    1. Group by topic/vertical
    2. Take 1-2 from each topic
    3. Fill remaining slots with highest priority
    """
    try:
        # Get all pending content
        result = supabase.table("content_queue") \
            .select("url, title, keyword, source, vertical_id") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .order("created_at") \
            .limit(50) \
            .execute()
        
        if not result.data:
            return []
        
        items = result.data
        
        # Group by topic
        by_topic = {}
        for item in items:
            topic = item.get("keyword") or item.get("vertical_id") or "general"
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(item)
        
        log.info(f"📊 Content diversity: {len(by_topic)} topics, {len(items)} total items")
        
        # Select 1-2 per topic, round-robin style
        selected = []
        topic_list = list(by_topic.keys())
        idx = 0
        
        while len(selected) < max_articles and any(by_topic.values()):
            topic = topic_list[idx % len(topic_list)]
            if by_topic[topic]:
                selected.append(by_topic[topic].pop(0))
            idx += 1
            
            # Remove empty topics
            topic_list = [t for t in topic_list if by_topic.get(t)]
            if not topic_list:
                break
        
        log.info(f"✅ Selected {len(selected)} diverse articles from {len(by_topic)} topics")
        return selected
        
    except Exception as e:
        log.error(f"Content selection failed: {e}")
        return []


# ============================================
# MAIN ASSEMBLY - LEGO ARCHITECTURE
# ============================================

def assemble_lego_podcast(
    user_id: str,
    target_duration: int = 15,
    format_type: str = "digest"
) -> Optional[dict]:
    """
    Assemble podcast with DIALOGUE segments.
    
    Structure:
    [Intro] + [Dialogue Segment 1] + [Dialogue Segment 2] + ... + [Outro]
    """
    
    config = FORMAT_CONFIG.get(format_type, FORMAT_CONFIG["digest"])
    target_minutes = config["duration_minutes"]
    max_articles = config["max_articles"]
    
    log.info("=" * 60)
    log.info(f"🎙️ ASSEMBLING LEGO PODCAST")
    log.info(f"   Format: {format_type}")
    log.info(f"   Target: {target_minutes} minutes")
    log.info(f"   Max articles: {max_articles}")
    log.info("=" * 60)
    
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
    
    # Get DIVERSE content
    items = select_diverse_content(user_id, max_articles)
    
    if not items:
        log.warning("❌ No content to process")
        return None
    
    target_date = date.today()
    edition = "morning" if datetime.now().hour < 14 else "evening"
    
    segments = []
    sources_data = []
    total_duration = 0
    target_seconds = target_minutes * 60
    
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
    
    # 2. NEWS SEGMENTS (DIALOGUE format)
    for item in items:
        # Stop if we're at 90% of target duration
        if total_duration >= target_seconds * 0.9:
            log.info(f"⏱️ Reached 90% target ({total_duration}s), stopping")
            break
        
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
            
            log.info(f"📊 Running total: {total_duration}s / {target_seconds}s")
    
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
        
        # Mark as processed
        processed_urls = [s["url"] for s in sources_data]
        supabase.table("content_queue") \
            .update({"status": "processed"}) \
            .eq("user_id", user_id) \
            .in_("url", processed_urls) \
            .execute()
        
        if episode.data:
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
        transition = AudioSegment.silent(duration=500)  # 500ms between segments
        
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
        
        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"podcast_{timestamp}.mp3")
        combined.export(output_path, format="mp3", bitrate="192k")
        
        # Upload
        remote_path = f"{user_id}/keernel_{target_date.isoformat()}_{timestamp}.mp3"
        
        with open(output_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            remote_path, audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        
        final_url = supabase.storage.from_("audio").get_public_url(remote_path)
        
        # Cleanup
        try:
            os.remove(output_path)
        except:
            pass
        
        return final_url
        
    except Exception as e:
        log.error(f"Stitching failed: {e}")
        return None


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc.replace("www.", "")
    except:
        return ""


def record_episode_composition(episode_id: str, segments: list):
    """Record which segments were used (for analytics)."""
    pass  # Optional analytics
