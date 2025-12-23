"""
Keernel Stitcher V5 - BULLETPROOF DIALOGUE

Ce fichier GARANTIT un dialogue entre Breeze et Vale.
Si le LLM ne génère pas de dialogue, on FORCE l'alternance.

DEBUG: Tous les logs sont explicites pour tracer le problème.
"""
import os
import re
import tempfile
from datetime import datetime, date
from urllib.parse import urlparse
import unicodedata

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
# VOICES
# ============================================

VOICE_BREEZE = "nova"   # Voix A - Expert
VOICE_VALE = "onyx"     # Voix B - Challenger

# ============================================
# PROMPTS
# ============================================

SYSTEM_PROMPT = """Tu génères des DIALOGUES podcast entre deux hôtes.

HÔTE A (Breeze) - Expert qui explique
HÔTE B (Vale) - Challenger qui questionne

FORMAT OBLIGATOIRE - Chaque réplique sur ce format EXACT:

[A]
Texte de Breeze ici.

[B]
Texte de Vale ici.

[A]
Breeze continue.

[B]
Vale répond.

RÈGLES:
- Utilise [A] et [B] comme tags (pas [VOICE_A])
- Alterne TOUJOURS entre [A] et [B]
- Minimum 4 répliques (2 de chaque)
- Style conversationnel naturel
- Pas de listes, pas de résumé ennuyeux
"""

USER_PROMPT_TEMPLATE = """Transforme ce contenu en dialogue captivant de {words} mots.

CONTENU:
{content}

RAPPEL FORMAT:
[A]
Breeze parle.

[B]
Vale répond.

Génère le dialogue maintenant:"""

# ============================================
# PARSING - ULTRA ROBUST
# ============================================

def parse_to_segments(script: str) -> list[dict]:
    """
    Parse ANY script format into voice segments.
    Handles [A], [B], [VOICE_A], [VOICE_B], Breeze:, Vale:, etc.
    """
    if not script:
        log.error("❌ Empty script!")
        return []
    
    log.info("📝 Parsing script", length=len(script), preview=script[:200])
    
    # Normalize all possible formats to [A] and [B]
    normalized = script
    
    # Replace various formats
    replacements = [
        (r'\[VOICE_A\]', '\n[A]\n'),
        (r'\[VOICE_B\]', '\n[B]\n'),
        (r'\[VOICE A\]', '\n[A]\n'),
        (r'\[VOICE B\]', '\n[B]\n'),
        (r'\[Voice_A\]', '\n[A]\n'),
        (r'\[Voice_B\]', '\n[B]\n'),
        (r'VOICE_A:', '\n[A]\n'),
        (r'VOICE_B:', '\n[B]\n'),
        (r'Breeze\s*:', '\n[A]\n'),
        (r'Vale\s*:', '\n[B]\n'),
        (r'\*\*Breeze\*\*\s*:', '\n[A]\n'),
        (r'\*\*Vale\*\*\s*:', '\n[B]\n'),
        (r'Speaker A\s*:', '\n[A]\n'),
        (r'Speaker B\s*:', '\n[B]\n'),
        (r'Host 1\s*:', '\n[A]\n'),
        (r'Host 2\s*:', '\n[B]\n'),
        (r'\[Breeze\]', '\n[A]\n'),
        (r'\[Vale\]', '\n[B]\n'),
    ]
    
    for pattern, repl in replacements:
        normalized = re.sub(pattern, repl, normalized, flags=re.IGNORECASE)
    
    # Now parse [A] and [B] tags
    segments = []
    
    # Split by [A] or [B]
    pattern = r'\[([AB])\]'
    parts = re.split(pattern, normalized)
    
    log.info("📊 Split result", parts_count=len(parts))
    
    # parts = ['before', 'A', 'text', 'B', 'text', ...]
    i = 1
    while i < len(parts) - 1:
        voice = parts[i].upper()
        text = parts[i + 1].strip()
        
        # Clean the text
        text = re.sub(r'^\s*\n+', '', text)
        text = re.sub(r'\n+\s*$', '', text)
        text = text.strip()
        
        if voice in ('A', 'B') and text and len(text) > 5:
            segments.append({'voice': voice, 'text': text})
            log.debug(f"✅ Segment {len(segments)}: Voice {voice}, {len(text)} chars")
        
        i += 2
    
    # If no segments found, FALLBACK: split by paragraphs
    if not segments:
        log.warning("⚠️ No voice tags found, using paragraph fallback")
        paragraphs = [p.strip() for p in script.split('\n\n') if p.strip() and len(p.strip()) > 20]
        
        if not paragraphs:
            paragraphs = [p.strip() for p in script.split('\n') if p.strip() and len(p.strip()) > 20]
        
        for i, para in enumerate(paragraphs[:10]):  # Max 10 segments
            segments.append({
                'voice': 'A' if i % 2 == 0 else 'B',
                'text': para
            })
    
    # FORCE alternation if needed
    if segments:
        voices_found = set(s['voice'] for s in segments)
        log.info(f"📊 Voices found: {voices_found}")
        
        if len(voices_found) == 1:
            log.warning("⚠️ Only one voice! Forcing alternation...")
            for i, seg in enumerate(segments):
                seg['voice'] = 'A' if i % 2 == 0 else 'B'
    
    # Final count
    voice_a = sum(1 for s in segments if s['voice'] == 'A')
    voice_b = sum(1 for s in segments if s['voice'] == 'B')
    
    log.info(f"✅ PARSED: {len(segments)} segments, Voice A: {voice_a}, Voice B: {voice_b}")
    
    return segments


# ============================================
# AUDIO GENERATION
# ============================================

def generate_tts(text: str, voice: str, output_path: str) -> bool:
    """Generate TTS audio with OpenAI."""
    if not openai_client:
        log.error("❌ OpenAI client not available!")
        return False
    
    try:
        log.info(f"🎤 TTS: {voice}, {len(text)} chars")
        
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
            speed=1.1  # Slightly faster
        )
        response.stream_to_file(output_path)
        
        log.info(f"✅ Audio saved: {output_path}")
        return True
        
    except Exception as e:
        log.error(f"❌ TTS failed: {e}")
        return False


def generate_dialogue_audio(script: str, output_path: str) -> str | None:
    """Generate audio with BOTH voices."""
    
    log.info("🎙️ Starting dialogue audio generation")
    
    segments = parse_to_segments(script)
    
    if not segments:
        log.error("❌ No segments to generate!")
        return None
    
    # Check we have both voices
    voices = set(s['voice'] for s in segments)
    log.info(f"🔊 Generating audio for voices: {voices}")
    
    if 'B' not in voices:
        log.error("❌ NO VOICE B DETECTED - This will be a monologue!")
    
    audio_files = []
    
    for i, seg in enumerate(segments):
        voice = VOICE_BREEZE if seg['voice'] == 'A' else VOICE_VALE
        text = seg['text']
        
        seg_path = output_path.replace('.mp3', f'_seg{i:03d}.mp3')
        
        log.info(f"🎤 Segment {i+1}/{len(segments)}: {voice} ({seg['voice']})")
        
        if generate_tts(text, voice, seg_path):
            audio_files.append(seg_path)
        else:
            log.warning(f"⚠️ Segment {i} failed, skipping")
    
    if not audio_files:
        log.error("❌ No audio files generated!")
        return None
    
    # Combine with pydub
    try:
        from pydub import AudioSegment
        
        combined = AudioSegment.empty()
        pause = AudioSegment.silent(duration=300)  # 300ms pause
        
        for i, path in enumerate(audio_files):
            audio = AudioSegment.from_mp3(path)
            combined += audio
            if i < len(audio_files) - 1:
                combined += pause
        
        combined.export(output_path, format='mp3', bitrate='192k')
        
        # Cleanup
        for f in audio_files:
            try:
                os.remove(f)
            except:
                pass
        
        log.info(f"✅ Combined audio: {output_path}")
        return output_path
        
    except Exception as e:
        log.error(f"❌ Combine failed: {e}")
        return None


def get_audio_duration(path: str) -> int:
    """Get duration in seconds."""
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_mp3(path)) // 1000
    except:
        return 0


# ============================================
# CONTENT GENERATION
# ============================================

def generate_dialogue_script(content: str, target_words: int = 200) -> str | None:
    """Generate dialogue script with Groq."""
    
    if not groq_client:
        log.error("❌ Groq client not available!")
        return None
    
    prompt = USER_PROMPT_TEMPLATE.format(
        words=target_words,
        content=content[:5000]
    )
    
    log.info(f"📝 Generating script with Groq ({target_words} words)")
    
    for attempt in range(3):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=target_words * 3
            )
            
            script = response.choices[0].message.content
            
            log.info(f"📄 Script generated (attempt {attempt+1})", 
                    length=len(script),
                    has_A='[A]' in script or '[VOICE_A]' in script,
                    has_B='[B]' in script or '[VOICE_B]' in script)
            
            # Test parse
            segments = parse_to_segments(script)
            voice_b_count = sum(1 for s in segments if s['voice'] == 'B')
            
            if voice_b_count >= 2:
                log.info(f"✅ Valid dialogue script with {voice_b_count} Vale segments")
                return script
            
            log.warning(f"⚠️ Only {voice_b_count} Vale segments, retrying...")
            
        except Exception as e:
            log.error(f"❌ Generation attempt {attempt+1} failed: {e}")
    
    log.error("❌ All attempts failed!")
    return None


# ============================================
# SEGMENT CREATION
# ============================================

def create_segment(url: str, target_words: int = 250) -> dict | None:
    """Create audio segment from URL."""
    
    log.info(f"🔗 Processing: {url[:60]}...")
    
    # Extract content
    extraction = extract_content(url)
    if not extraction:
        log.warning(f"⚠️ Extraction failed: {url[:60]}")
        return None
    
    source_type, title, content = extraction
    log.info(f"📰 Extracted: {title[:50]}")
    
    # Generate script
    script = generate_dialogue_script(content, target_words)
    if not script:
        log.error("❌ Script generation failed")
        return None
    
    # Generate audio
    timestamp = datetime.now().strftime("%H%M%S")
    safe_title = re.sub(r'[^a-z0-9]', '', title.lower()[:15])
    temp_path = os.path.join(tempfile.gettempdir(), f"seg_{safe_title}_{timestamp}.mp3")
    
    audio_path = generate_dialogue_audio(script, temp_path)
    if not audio_path:
        log.error("❌ Audio generation failed")
        return None
    
    duration = get_audio_duration(audio_path)
    log.info(f"✅ Segment created: {title[:40]}, {duration}s")
    
    return {
        "local_path": audio_path,
        "duration": duration,
        "title": title
    }


# ============================================
# INTRO (Single voice - Breeze)
# ============================================

def create_intro(first_name: str) -> dict | None:
    """Create intro with Breeze voice."""
    
    display_name = first_name.strip().title() if first_name else "Ami"
    intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    
    log.info(f"🎤 Creating intro for {display_name}")
    
    timestamp = datetime.now().strftime("%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"intro_{timestamp}.mp3")
    
    if generate_tts(intro_text, VOICE_BREEZE, temp_path):
        return {
            "local_path": temp_path,
            "duration": get_audio_duration(temp_path)
        }
    
    return None


# ============================================
# UTILITY
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

def assemble_podcast(user_id: str, first_name: str, urls: list[str], target_duration: int = 15) -> dict | None:
    """Assemble full podcast."""
    
    log.info(f"🎙️ STARTING PODCAST ASSEMBLY")
    log.info(f"   User: {user_id[:8]}")
    log.info(f"   URLs: {len(urls)}")
    log.info(f"   Target: {target_duration} min")
    
    segments = []
    sources = []
    temp_files = []
    
    try:
        # 1. INTRO
        intro = create_intro(first_name)
        if intro:
            segments.append(intro["local_path"])
            temp_files.append(intro["local_path"])
            log.info(f"✅ Intro: {intro['duration']}s")
        
        # 2. CONTENT SEGMENTS
        target_seconds = target_duration * 60
        words_per_seg = max(150, min(350, target_seconds // max(1, len(urls))))
        
        for url in urls[:5]:  # Max 5 URLs
            seg = create_segment(url, words_per_seg)
            if seg:
                segments.append(seg["local_path"])
                temp_files.append(seg["local_path"])
                sources.append({
                    "title": seg["title"],
                    "url": url,
                    "domain": get_domain(url)
                })
        
        if len(segments) < 2:
            log.error("❌ Not enough segments!")
            return None
        
        # 3. COMBINE
        from pydub import AudioSegment
        combined = AudioSegment.empty()
        for path in segments:
            combined += AudioSegment.from_mp3(path)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"podcast_{timestamp}.mp3")
        combined.export(output_path, format="mp3", bitrate="192k")
        
        duration = len(combined) // 1000
        
        # 4. UPLOAD
        remote = f"{user_id}/keernel_{timestamp}.mp3"
        audio_url = upload_audio(output_path, remote)
        
        # Cleanup
        os.remove(output_path)
        for f in temp_files:
            try:
                os.remove(f)
            except:
                pass
        
        log.info(f"✅ PODCAST COMPLETE: {duration}s, {len(sources)} sources")
        
        return {
            "audio_url": audio_url,
            "duration": duration,
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
    
    log.info("=" * 50)
    log.info("🚀 GENERATE PODCAST FOR USER")
    log.info("=" * 50)
    
    # Get user
    try:
        user = supabase.table("users").select("first_name, target_duration").eq("id", user_id).single().execute()
        first_name = user.data.get("first_name") or "Ami"
        target_duration = user.data.get("target_duration") or 15
    except:
        first_name = "Ami"
        target_duration = 15
    
    log.info(f"👤 User: {first_name}, Target: {target_duration}min")
    
    # Get queue
    try:
        queue = supabase.table("content_queue").select("url").eq("user_id", user_id).eq("status", "pending").execute()
        urls = [item["url"] for item in queue.data] if queue.data else []
    except:
        urls = []
    
    log.info(f"📋 Queue: {len(urls)} URLs")
    
    if not urls:
        log.warning("⚠️ No content in queue!")
        return None
    
    # Assemble
    result = assemble_podcast(user_id, first_name, urls, target_duration)
    
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
        
        log.info(f"✅ EPISODE CREATED!")
        return episode.data[0] if episode.data else None
        
    except Exception as e:
        log.error(f"❌ Episode creation failed: {e}")
        return None
