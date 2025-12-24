"""
Keernel Stitcher V2 - COMPLETE REWRITE

FIXES APPLIED:
1. DIALOGUE: Each segment is a dialogue between Breeze [A] and Vale [B]
2. DURATION: flash=4min (600 words), digest=15min (2000 words) 
3. SOURCE DIVERSITY: Diversify by topic/vertical, not just by source type
4. SOURCE CITATION: Each segment mentions the source name
5. TTS SPEED: 1.05 (natural, not rushed)
6. MULTIPLE TOPICS: Ensure we cover different topics user subscribed to

V2.1 ADDITIONS:
7. AUDIO ARCHIVE: Keep 7 days of cached audio
8. DATA REPORTS: Generate Markdown reports for each episode
9. HISTORY: get_user_history() function for past reports
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
# CONFIGURATION
# ============================================

VOICE_BREEZE = "nova"   # Voice A - Expert
VOICE_VALE = "onyx"     # Voice B - Challenger
TTS_SPEED = 1.05        # Natural speed (1.0 = normal)

WORDS_PER_MINUTE = 150
SEGMENT_CACHE_DAYS = 7  # Keep audio cache for 7 days
REPORT_RETENTION_DAYS = 365  # Keep reports for 1 year

# Format configurations - OPTIMIZED FOR DENSITY
# TTS at 1.05x speed ≈ 160 words/minute
# More articles with shorter segments = higher information density
FORMAT_CONFIG = {
    "flash": {
        "duration_minutes": 4,
        "total_words": 900,           # Target ~4-5 min
        "max_articles": 7,            # 7 articles for high density
        "words_per_article": 130,     # ~35-40 seconds per article
        "style": "ultra-concis et percutant"
    },
    "digest": {
        "duration_minutes": 15,
        "total_words": 2800,          # Target ~15 min
        "max_articles": 12,           # 12 sources for comprehensive coverage
        "words_per_article": 240,     # ~1 min per article
        "style": "approfondi et analytique"
    }
}

# ============================================
# DIALOGUE PROMPT - THIS IS THE KEY FIX
# ============================================

DIALOGUE_SEGMENT_PROMPT = """Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.

## LES HÔTES
- [A] = Expert qui explique clairement
- [B] = Challenger curieux qui pose des questions

## FORMAT OBLIGATOIRE
Chaque réplique DOIT commencer par [A] ou [B] seul sur une ligne:

[A]
Le texte que dit l'expert.

[B]
Le texte que dit le challenger.

## RÈGLES STRICTES
1. ALTERNER [A] et [B] - jamais deux [A] ou deux [B] de suite
2. Minimum 6 répliques (3 de chaque)
3. Style oral naturel: "Écoute,", "En fait,", "Tu vois,"
4. [B] pose des QUESTIONS
5. ZÉRO liste, ZÉRO bullet points
6. CITE LA SOURCE dans la première réplique: "Selon {source_name}..."
7. INTERDIT: Ne jamais écrire "Breeze répond", "Vale questionne", "(il explique)" ou toute didascalie

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

def clean_stage_directions(text: str) -> str:
    """Remove stage directions like 'Breeze répond', 'Vale questionne', etc."""
    # Remove common stage directions at the start
    patterns_to_remove = [
        r'^Breeze\s+(répond|explique|continue|ajoute|conclut|questionne|demande|s\'exclame|lance|commente)\s*[:\.\,]?\s*',
        r'^Vale\s+(répond|explique|continue|ajoute|conclut|questionne|demande|s\'exclame|lance|commente)\s*[:\.\,]?\s*',
        r'^\(Breeze[^)]*\)\s*',
        r'^\(Vale[^)]*\)\s*',
        r'^\*Breeze[^*]*\*\s*',
        r'^\*Vale[^*]*\*\s*',
        r'^Breeze\s*:\s*',
        r'^Vale\s*:\s*',
    ]
    
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Also remove inline stage directions
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
        
        # CLEAN stage directions
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
# CONTENT SELECTION - PRIORITIZE GSHEET + DIVERSIFY
# ============================================

def select_diverse_content(user_id: str, max_articles: int) -> list[dict]:
    """
    Select content with:
    1. PRIORITY to gsheet/rss/library sources (NOT bing)
    2. DIVERSITY across topics
    3. Fill remaining with bing_news ONLY if needed
    """
    try:
        # Get all pending content
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
        
        # Log all unique source values for debugging
        unique_sources = set(i.get("source", "NONE") for i in items)
        log.info(f"📋 Queue has {len(items)} items, sources: {unique_sources}")
        
        # Separate by source type - ANYTHING that's NOT bing is priority
        # GSheet RSS typically has source="gsheet_rss" or similar
        priority_items = []
        bing_items = []
        
        for item in items:
            source = (item.get("source") or "").lower()
            # Bing sources contain "bing" in the name
            if "bing" in source:
                bing_items.append(item)
            else:
                # Everything else is priority (gsheet, rss, manual, library, etc.)
                priority_items.append(item)
        
        log.info(f"📊 Priority (non-bing): {len(priority_items)}, Bing: {len(bing_items)}")
        
        # Group priority items by topic for diversity
        priority_by_topic = {}
        for item in priority_items:
            topic = item.get("keyword") or item.get("vertical_id") or "general"
            if topic not in priority_by_topic:
                priority_by_topic[topic] = []
            priority_by_topic[topic].append(item)
        
        # Select from priority sources first, round-robin by topic
        selected = []
        topic_list = list(priority_by_topic.keys())
        idx = 0
        
        # Take from priority until we have enough or run out
        while len(selected) < max_articles and topic_list:
            topic = topic_list[idx % len(topic_list)]
            if priority_by_topic.get(topic):
                item = priority_by_topic[topic].pop(0)
                selected.append(item)
                log.info(f"   ✅ Selected: {item.get('title', 'No title')[:40]}... (source={item.get('source')})")
            idx += 1
            topic_list = [t for t in topic_list if priority_by_topic.get(t)]
        
        # Fill remaining slots with bing_news ONLY if we don't have enough
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
        
        # Final count
        priority_count = sum(1 for s in selected if "bing" not in (s.get("source") or "").lower())
        bing_count = len(selected) - priority_count
        
        log.info(f"✅ FINAL: {len(selected)} articles ({priority_count} priority, {bing_count} bing)")
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
    
    # 2. NEWS SEGMENTS (DIALOGUE format) - Process ALL selected articles
    for idx, item in enumerate(items):
        log.info(f"🎯 Processing article {idx+1}/{len(items)}: {item.get('title', 'No title')[:50]}...")
        
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
            
            log.info(f"📊 Segment {idx+1}: {segment.get('duration', 0)}s | Total: {total_duration}s / {target_seconds}s")
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
        
        # CLEAR ALL remaining pending articles (they're now stale)
        # This prevents old articles from accumulating
        clear_result = supabase.table("content_queue") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        
        cleared_count = len(clear_result.data) if clear_result.data else 0
        log.info(f"🗑️ Cleared {cleared_count} stale pending articles")
        
        if episode.data:
            episode_id = episode.data[0]["id"]
            
            # 6. GENERATE MARKDOWN REPORT
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
                # Update episode with report URL
                supabase.table("episodes") \
                    .update({"report_url": report_url}) \
                    .eq("id", episode_id) \
                    .execute()
            
            log.info(f"✅ EPISODE CREATED: {total_duration}s, {len(sources_data)} sources, report={bool(report_url)}")
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


# ============================================
# MARKDOWN REPORT GENERATION
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
    """
    Generate a structured Markdown report for the episode.
    
    Returns the report URL after uploading to storage.
    """
    
    # Build Markdown content
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
        source_domain = source.get("domain", extract_domain(source_url))
        
        report_md += f"""### {i}. {source_title}

- **Source** : [{source_domain}]({source_url})
- **URL** : {source_url}

"""
    
    report_md += f"""---

## 📊 Résumé

- **Durée totale** : {duration_str}
- **Format** : {format_type.title()}
- **Articles couverts** : {len(sources_data)}
- **Généré le** : {datetime.now().strftime('%d/%m/%Y à %H:%M')}

---

*Rapport généré automatiquement par Keernel*
"""
    
    # Upload to storage
    try:
        report_filename = f"report_{target_date.isoformat()}_{episode_id[:8]}.md"
        remote_path = f"reports/{user_id}/{target_date.strftime('%Y/%m')}/{report_filename}"
        
        supabase.storage.from_("reports").upload(
            remote_path,
            report_md.encode('utf-8'),
            {"content-type": "text/markdown", "upsert": "true"}
        )
        
        report_url = supabase.storage.from_("reports").get_public_url(remote_path)
        
        # Save reference in database
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
# USER HISTORY
# ============================================

def get_user_history(user_id: str, limit: int = 20) -> List[dict]:
    """
    Get list of past episode reports for a user.
    
    Returns list of reports with:
    - id, episode_id, report_url, report_date
    - format_type, sources_count, duration_seconds
    """
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


def get_user_history_this_week(user_id: str) -> List[dict]:
    """
    Get reports from the last 7 days.
    """
    try:
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        
        result = supabase.table("episode_reports") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("report_date", week_ago) \
            .order("report_date", desc=True) \
            .execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        log.error(f"Failed to get weekly history: {e}")
        return []


# ============================================
# AUDIO CACHE CLEANUP (Keep 7 days)
# ============================================

def cleanup_old_audio_cache(days_to_keep: int = SEGMENT_CACHE_DAYS):
    """
    Remove audio segments older than specified days.
    Keeps the last 7 days by default.
    """
    try:
        cutoff_date = (date.today() - timedelta(days=days_to_keep)).isoformat()
        
        # Get old segments
        old_segments = supabase.table("audio_segments") \
            .select("id, audio_url, date") \
            .lt("date", cutoff_date) \
            .execute()
        
        if not old_segments.data:
            log.info("No old segments to clean up")
            return 0
        
        deleted_count = 0
        
        for segment in old_segments.data:
            try:
                # Delete from storage if URL is from our bucket
                audio_url = segment.get("audio_url", "")
                if "supabase" in audio_url and "/segments/" in audio_url:
                    # Extract path from URL
                    path_match = re.search(r'/segments/(.+)$', audio_url)
                    if path_match:
                        storage_path = f"segments/{path_match.group(1)}"
                        supabase.storage.from_("audio").remove([storage_path])
                
                # Delete from database
                supabase.table("audio_segments") \
                    .delete() \
                    .eq("id", segment["id"]) \
                    .execute()
                
                deleted_count += 1
                
            except Exception as e:
                log.warning(f"Failed to delete segment {segment['id']}: {e}")
        
        log.info(f"🗑️ Cleaned up {deleted_count} old audio segments (older than {days_to_keep} days)")
        return deleted_count
        
    except Exception as e:
        log.error(f"Cache cleanup failed: {e}")
        return 0


def run_daily_maintenance():
    """
    Run daily maintenance tasks:
    - Clean up old audio cache
    - Keep reports permanently
    """
    log.info("🔧 Running daily maintenance...")
    
    # Clean audio cache (keep 7 days)
    deleted = cleanup_old_audio_cache(SEGMENT_CACHE_DAYS)
    
    log.info(f"✅ Maintenance complete. Deleted {deleted} old segments.")
    return {"deleted_segments": deleted}
