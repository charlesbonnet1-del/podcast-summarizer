"""
Keernel Stitcher V6 - FIXED DURATION + BULLETPROOF DIALOGUE

FIXES:
1. Duration: flash=4min, digest=15min (was reading wrong field)
2. Speed: 1.2x for dynamic delivery (was 1.1)
3. Dialogue: Strict prompt with examples + guaranteed alternation
"""
import os
import re
import tempfile
from datetime import datetime, date
from urllib.parse import urlparse

import structlog
from dotenv import load_dotenv

from db import supabase
from extractor import extract_content

load_dotenv()
log = structlog.get_logger()

# ============================================
# CLIENTS
# ============================================

from groq import Groq
groq_client = None
if os.getenv("GROQ_API_KEY"):
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    log.info("✅ Groq client initialized")
else:
    log.error("❌ GROQ_API_KEY not set!")

from openai import OpenAI
openai_client = None
if os.getenv("OPENAI_API_KEY"):
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    log.info("✅ OpenAI client initialized")
else:
    log.error("❌ OPENAI_API_KEY not set!")

# ============================================
# CONFIGURATION
# ============================================

VOICE_BREEZE = "nova"   # Voice A - Expert
VOICE_VALE = "onyx"     # Voice B - Challenger

# Duration mapping (in minutes)
FORMAT_DURATION = {
    "flash": 4,
    "digest": 15
}

# TTS speed (1.0 = normal, 1.2 = 20% faster)
TTS_SPEED = 1.2

# Words per minute for estimation
WORDS_PER_MINUTE = 150

# ============================================
# DIALOGUE PROMPTS - STRICT FORMAT
# ============================================

SYSTEM_PROMPT = """Tu es un scripteur de podcast. Tu génères des DIALOGUES entre deux hôtes.

BREEZE (tag [A]) = Expert pédagogue qui explique clairement
VALE (tag [B]) = Challenger curieux qui pose des questions

## FORMAT OBLIGATOIRE

Chaque réplique DOIT commencer par [A] ou [B] sur une ligne seule:

[A]
Première réplique de Breeze.

[B]
Vale répond ou questionne.

[A]
Breeze développe.

[B]
Vale conclut.

## RÈGLES STRICTES

1. TOUJOURS alterner [A] et [B] - JAMAIS deux [A] ou deux [B] de suite
2. MINIMUM 6 répliques (3 de chaque)
3. Chaque réplique = 1-3 phrases maximum
4. Style oral naturel: "Bon,", "Écoute,", "En fait,"
5. Vale pose des QUESTIONS, pas juste des commentaires
6. ZÉRO liste à puces, ZÉRO énumération

## EXEMPLE CORRECT

[A]
Tu savais que Google vient de perdre 100 milliards en bourse en une seule journée?

[B]
Attends, comment c'est possible? Ils ont fait quoi?

[A]
Leur IA Bard a fait une erreur factuelle en direct lors d'une démo. Les investisseurs ont paniqué.

[B]
Une seule erreur et boom, 100 milliards? C'est dingue la pression sur ces boîtes.

[A]
Exactement. Ça montre à quel point la course à l'IA est devenue un enjeu financier énorme.

[B]
Et du coup, ça change quoi pour nous, les utilisateurs?
"""

USER_PROMPT = """Transforme ce contenu en dialogue de {words} mots entre Breeze [A] et Vale [B].

CONTENU À TRANSFORMER:
{content}

RAPPEL: Utilise [A] et [B], alterne strictement, minimum 6 répliques.

GÉNÈRE LE DIALOGUE:"""

# ============================================
# PARSING - ULTRA ROBUST
# ============================================

def parse_to_segments(script: str) -> list[dict]:
    """Parse script into voice segments with guaranteed alternation."""
    if not script:
        log.error("❌ Empty script!")
        return []
    
    log.info("📝 Parsing script", length=len(script))
    
    # Normalize all tag formats
    normalized = script
    replacements = [
        (r'\[VOICE_A\]', '\n[A]\n'),
        (r'\[VOICE_B\]', '\n[B]\n'),
        (r'\[VOICE A\]', '\n[A]\n'),
        (r'\[VOICE B\]', '\n[B]\n'),
        (r'VOICE_A:', '\n[A]\n'),
        (r'VOICE_B:', '\n[B]\n'),
        (r'Breeze\s*:', '\n[A]\n'),
        (r'Vale\s*:', '\n[B]\n'),
        (r'\*\*Breeze\*\*', '\n[A]\n'),
        (r'\*\*Vale\*\*', '\n[B]\n'),
        (r'Speaker A:', '\n[A]\n'),
        (r'Speaker B:', '\n[B]\n'),
        (r'Host 1:', '\n[A]\n'),
        (r'Host 2:', '\n[B]\n'),
        (r'\[Breeze\]', '\n[A]\n'),
        (r'\[Vale\]', '\n[B]\n'),
        (r'A:', '\n[A]\n'),
        (r'B:', '\n[B]\n'),
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
        text = re.sub(r'^\s*\n+', '', text)
        text = re.sub(r'\n+\s*$', '', text)
        text = text.strip()
        
        if voice in ('A', 'B') and text and len(text) > 10:
            segments.append({'voice': voice, 'text': text})
        i += 2
    
    # FALLBACK: Split by paragraphs if no tags found
    if not segments:
        log.warning("⚠️ No voice tags found, using paragraph fallback")
        paragraphs = [p.strip() for p in script.split('\n\n') if p.strip() and len(p.strip()) > 20]
        if not paragraphs:
            paragraphs = [p.strip() for p in script.split('\n') if p.strip() and len(p.strip()) > 20]
        
        for i, para in enumerate(paragraphs[:10]):
            segments.append({
                'voice': 'A' if i % 2 == 0 else 'B',
                'text': para
            })
    
    # FORCE alternation - this guarantees dialogue
    if len(segments) >= 2:
        for i in range(len(segments)):
            segments[i]['voice'] = 'A' if i % 2 == 0 else 'B'
    
    voice_a = sum(1 for s in segments if s['voice'] == 'A')
    voice_b = sum(1 for s in segments if s['voice'] == 'B')
    
    log.info(f"✅ PARSED: {len(segments)} segments, A={voice_a}, B={voice_b}")
    
    return segments


# ============================================
# TTS GENERATION
# ============================================

def generate_tts(text: str, voice: str, output_path: str) -> bool:
    """Generate TTS with OpenAI at faster speed."""
    if not openai_client:
        log.error("❌ OpenAI client not available!")
        return False
    
    try:
        log.info(f"🎤 TTS: {voice}, {len(text)} chars, speed={TTS_SPEED}")
        
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


def generate_dialogue_audio(script: str, output_path: str) -> str | None:
    """Generate dialogue audio with both voices."""
    
    log.info("🎙️ Generating dialogue audio")
    
    segments = parse_to_segments(script)
    
    if not segments:
        log.error("❌ No segments!")
        return None
    
    audio_files = []
    
    for i, seg in enumerate(segments):
        voice = VOICE_BREEZE if seg['voice'] == 'A' else VOICE_VALE
        seg_path = output_path.replace('.mp3', f'_seg{i:03d}.mp3')
        
        log.info(f"🎤 Segment {i+1}/{len(segments)}: {voice} ({seg['voice']})")
        
        if generate_tts(seg['text'], voice, seg_path):
            audio_files.append(seg_path)
    
    if not audio_files:
        return None
    
    # Combine with short pauses
    try:
        from pydub import AudioSegment
        
        combined = AudioSegment.empty()
        pause = AudioSegment.silent(duration=250)  # 250ms between turns
        
        for i, path in enumerate(audio_files):
            combined += AudioSegment.from_mp3(path)
            if i < len(audio_files) - 1:
                combined += pause
        
        combined.export(output_path, format='mp3', bitrate='192k')
        
        # Cleanup temp files
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

def generate_dialogue_script(content: str, target_words: int) -> str | None:
    """Generate dialogue script with Groq."""
    
    if not groq_client:
        log.error("❌ Groq client not available!")
        return None
    
    prompt = USER_PROMPT.format(words=target_words, content=content[:6000])
    
    log.info(f"📝 Generating {target_words}-word script")
    
    for attempt in range(3):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=target_words * 4
            )
            
            script = response.choices[0].message.content
            
            # Quick validation
            has_a = '[A]' in script or '[a]' in script.lower()
            has_b = '[B]' in script or '[b]' in script.lower()
            
            log.info(f"📄 Script generated (attempt {attempt+1}): has_A={has_a}, has_B={has_b}")
            
            if has_a or has_b:
                return script
            
            # If no tags, try again with stronger instruction
            prompt = prompt + "\n\nATTENTION: Tu DOIS utiliser [A] et [B] pour marquer chaque réplique!"
            
        except Exception as e:
            log.error(f"❌ Generation failed: {e}")
    
    return None


# ============================================
# SEGMENT CREATION
# ============================================

def create_segment(url: str, target_words: int) -> dict | None:
    """Create audio segment from URL."""
    
    log.info(f"🔗 Processing: {url[:60]}...")
    
    extraction = extract_content(url)
    if not extraction:
        log.warning(f"⚠️ Extraction failed: {url[:60]}")
        return None
    
    source_type, title, content = extraction
    log.info(f"📰 Extracted: {title[:50]}, {len(content)} chars")
    
    script = generate_dialogue_script(content, target_words)
    if not script:
        log.error("❌ Script generation failed")
        return None
    
    timestamp = datetime.now().strftime("%H%M%S")
    safe_title = re.sub(r'[^a-z0-9]', '', title.lower()[:15])
    temp_path = os.path.join(tempfile.gettempdir(), f"seg_{safe_title}_{timestamp}.mp3")
    
    audio_path = generate_dialogue_audio(script, temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    log.info(f"✅ Segment: {title[:40]}, {duration}s")
    
    return {
        "local_path": audio_path,
        "duration": duration,
        "title": title
    }


# ============================================
# INTRO
# ============================================

def create_intro(first_name: str) -> dict | None:
    """Create intro with Breeze voice."""
    
    display_name = first_name.strip().title() if first_name else "Ami"
    intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    
    log.info(f"🎤 Creating intro for {display_name}")
    
    temp_path = os.path.join(tempfile.gettempdir(), f"intro_{datetime.now().strftime('%H%M%S')}.mp3")
    
    if generate_tts(intro_text, VOICE_BREEZE, temp_path):
        return {
            "local_path": temp_path,
            "duration": get_audio_duration(temp_path)
        }
    return None


# ============================================
# UTILITIES
# ============================================

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace('www.', '')
    except:
        return "source"


def upload_audio(local_path: str, remote_path: str) -> str | None:
    try:
        with open(local_path, 'rb') as f:
            data = f.read()
        supabase.storage.from_("audio").upload(
            remote_path, data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        return supabase.storage.from_("audio").get_public_url(remote_path)
    except Exception as e:
        log.error(f"❌ Upload failed: {e}")
        return None


# ============================================
# MAIN ASSEMBLY
# ============================================

def assemble_podcast(user_id: str, first_name: str, urls: list[str], target_minutes: int) -> dict | None:
    """Assemble podcast with correct duration."""
    
    log.info("=" * 50)
    log.info(f"🎙️ ASSEMBLING PODCAST")
    log.info(f"   Target: {target_minutes} minutes")
    log.info(f"   URLs: {len(urls)}")
    log.info("=" * 50)
    
    segments = []
    sources = []
    temp_files = []
    total_duration = 0
    target_seconds = target_minutes * 60
    
    try:
        # 1. INTRO (~5 seconds)
        intro = create_intro(first_name)
        if intro:
            segments.append(intro["local_path"])
            temp_files.append(intro["local_path"])
            total_duration += intro["duration"]
            log.info(f"✅ Intro: {intro['duration']}s")
        
        # 2. CALCULATE words per segment to hit target duration
        # Formula: target_seconds * WORDS_PER_MINUTE / 60 = total words needed
        # Divide by number of URLs
        remaining_seconds = target_seconds - total_duration
        total_words_needed = int(remaining_seconds * WORDS_PER_MINUTE / 60)
        num_urls = min(len(urls), 5)  # Max 5 sources
        words_per_segment = max(200, total_words_needed // num_urls)
        
        log.info(f"📊 Target: {remaining_seconds}s = {total_words_needed} words")
        log.info(f"📊 Per segment: {words_per_segment} words x {num_urls} URLs")
        
        # 3. GENERATE SEGMENTS
        for url in urls[:num_urls]:
            # Stop if we've reached target duration
            if total_duration >= target_seconds * 0.9:
                log.info(f"⏱️ Reached 90% of target ({total_duration}s), stopping")
                break
            
            seg = create_segment(url, words_per_segment)
            if seg:
                segments.append(seg["local_path"])
                temp_files.append(seg["local_path"])
                total_duration += seg["duration"]
                sources.append({
                    "title": seg["title"],
                    "url": url,
                    "domain": get_domain(url)
                })
                log.info(f"📊 Running total: {total_duration}s / {target_seconds}s")
        
        if len(segments) < 2:
            log.error("❌ Not enough segments!")
            return None
        
        # 4. COMBINE
        from pydub import AudioSegment
        combined = AudioSegment.empty()
        
        for path in segments:
            combined += AudioSegment.from_mp3(path)
        
        output_path = os.path.join(tempfile.gettempdir(), f"podcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3")
        combined.export(output_path, format="mp3", bitrate="192k")
        
        final_duration = len(combined) // 1000
        
        # 5. UPLOAD
        remote = f"{user_id}/keernel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        audio_url = upload_audio(output_path, remote)
        
        # Cleanup
        os.remove(output_path)
        for f in temp_files:
            try:
                os.remove(f)
            except:
                pass
        
        log.info(f"✅ PODCAST COMPLETE: {final_duration}s ({final_duration//60}m{final_duration%60}s)")
        
        return {
            "audio_url": audio_url,
            "duration": final_duration,
            "sources_data": sources
        }
        
    except Exception as e:
        log.error(f"❌ Assembly failed: {e}")
        return None


# ============================================
# ENTRY POINT
# ============================================

def generate_podcast_for_user(user_id: str) -> dict | None:
    """Main entry point."""
    
    log.info("=" * 60)
    log.info("🚀 GENERATE PODCAST FOR USER")
    log.info("=" * 60)
    
    # Get user preferences
    try:
        user = supabase.table("users").select("first_name, preferred_format").eq("id", user_id).single().execute()
        first_name = user.data.get("first_name") or "Ami"
        preferred_format = user.data.get("preferred_format") or "digest"
    except:
        first_name = "Ami"
        preferred_format = "digest"
    
    # Convert format to minutes
    target_minutes = FORMAT_DURATION.get(preferred_format, 15)
    
    log.info(f"👤 User: {first_name}")
    log.info(f"📻 Format: {preferred_format} = {target_minutes} minutes")
    
    # Get content queue
    try:
        queue = supabase.table("content_queue").select("url").eq("user_id", user_id).eq("status", "pending").execute()
        urls = [item["url"] for item in queue.data] if queue.data else []
    except:
        urls = []
    
    log.info(f"📋 Queue: {len(urls)} URLs")
    
    if not urls:
        log.warning("⚠️ No content in queue!")
        return None
    
    # Assemble podcast
    result = assemble_podcast(user_id, first_name, urls, target_minutes)
    
    if not result:
        supabase.table("content_queue").update({"status": "failed"}).eq("user_id", user_id).eq("status", "pending").execute()
        return None
    
    # Create episode
    try:
        today = date.today()
        title = f"Keernel - {today.strftime('%d %B %Y')}"
        
        episode = supabase.table("episodes").insert({
            "user_id": user_id,
            "title": title,
            "audio_url": result["audio_url"],
            "audio_duration": result["duration"],
            "sources_data": result["sources_data"]
        }).execute()
        
        supabase.table("content_queue").update({"status": "processed"}).eq("user_id", user_id).eq("status", "pending").execute()
        
        log.info(f"✅ EPISODE CREATED: {result['duration']}s")
        return episode.data[0] if episode.data else None
        
    except Exception as e:
        log.error(f"❌ Episode creation failed: {e}")
        return None
