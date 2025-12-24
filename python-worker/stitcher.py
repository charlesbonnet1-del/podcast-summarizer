"""
Keernel Stitcher V6 - Compatible with stitcher_v2.py

EXPORTS for stitcher_v2:
- get_or_create_intro(first_name) -> cached/created intro
- generate_dialogue_audio(script, output_path) -> dialogue audio
- get_audio_duration(path) -> seconds

FIXES:
1. Speed: 1.2x for dynamic delivery
2. Dialogue: Strict alternation with [A]/[B] tags
3. get_or_create_intro: Added for stitcher_v2 compatibility
"""
import os
import re
import hashlib
import tempfile
from datetime import datetime, date
from urllib.parse import urlparse
from typing import Optional

import structlog
from dotenv import load_dotenv

from db import supabase

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

from openai import OpenAI
openai_client = None
if os.getenv("OPENAI_API_KEY"):
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    log.info("✅ OpenAI client initialized")

# ============================================
# CONFIGURATION
# ============================================

VOICE_BREEZE = "nova"   # Voice A - Expert
VOICE_VALE = "onyx"     # Voice B - Challenger

# TTS speed (1.0 = normal, 1.05 = slightly faster but natural)
TTS_SPEED = 1.05

# ============================================
# DIALOGUE PROMPTS - STRICT FORMAT
# ============================================



SYSTEM_PROMPT = """Tu es un scripteur de podcast. Tu génères des DIALOGUES entre deux hôtes.
Ton but est de concentrer le maximum de valeur et d’informations importantes dans ce dialogue entre deux journalistes.

BREEZE (tag [A]) = Expert pédagogue qui explique clairement
VALE (tag [B]) = Challenger curieux qui cherche à approfondir

## FORMAT OBLIGATOIRE

Chaque réplique DOIT commencer par [A] ou [B] sur une ligne seule:

[A]
Première réplique de Breeze.

[B]
Vale répond en approfondissant ou expliquant les conséquences.

[A]
Breeze développe.

[B]
Vale conclut.

## RÈGLES STRICTES

1. TOUJOURS alterner [A] et [B] - JAMAIS deux [A] ou deux [B] de suite
2. MINIMUM 6 répliques (3 de chaque)
3. Chaque réplique = 1-3 phrases maximum
4. Style oral conversationnel et journalistique : affirmatif, renseigné, cite ses sources.
5. Vale enrichi les affirmations de Breeze.
6. ZÉRO liste à puces, ZÉRO énumération.
7. Un contenu le plus riche possible : des chiffres si l’input le permet, des exemples. Les informations les plus impactantes de l’input doivent se trouver l’output.

## EXEMPLE CORRECT

[A]
Google vient de perdre 100 milliards en bourse en une seule journée.

[B]
En effet, leur IA Bard a fait une erreur factuelle en direct lors d'une démo. Les investisseurs ont paniqué.

[A]
Contrairement à Open AI qui maintient une croissance fulgurante avec 800 millions d’utilisateurs quotidiens dans le monde.

[B]
Tu as raison, et selon le Financial Times, Anthropic prépare une IPO à 600 milliards d’euros.

[A]
Exactement. Ça montre l’ampleur du marché de l’IA puisqu’Open AI cherche également à s’introduire en bourse selon un article du 24 décembre des Echos.

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
    """Parse script into voice segments with GUARANTEED alternation."""
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
    
    # FORCE alternation - this GUARANTEES dialogue
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
    """Generate dialogue audio with BOTH voices."""
    
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
# INTRO - CACHED (for stitcher_v2 compatibility)
# ============================================

def get_or_create_intro(first_name: str) -> Optional[dict]:
    """
    Get cached intro or create new one.
    
    This function is called by stitcher_v2.py
    
    Returns:
        dict with audio_url and audio_duration
    """
    display_name = first_name.strip().title() if first_name else "Ami"
    
    # Generate a hash for caching
    intro_hash = hashlib.md5(display_name.encode()).hexdigest()[:16]
    
    # Check cache first
    try:
        cached = supabase.table("cached_intros") \
            .select("audio_url, audio_duration") \
            .eq("name_hash", intro_hash) \
            .single() \
            .execute()
        
        if cached.data:
            log.info(f"📦 Using cached intro for {display_name}")
            return cached.data
    except:
        pass
    
    # Create new intro
    log.info(f"🎤 Creating intro for {display_name}")
    
    intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    
    timestamp = datetime.now().strftime("%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"intro_{timestamp}.mp3")
    
    if not generate_tts(intro_text, VOICE_BREEZE, temp_path):
        return None
    
    duration = get_audio_duration(temp_path)
    
    # Upload to storage
    remote_path = f"intros/{intro_hash}.mp3"
    try:
        with open(temp_path, 'rb') as f:
            data = f.read()
        supabase.storage.from_("audio").upload(
            remote_path, data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        audio_url = supabase.storage.from_("audio").get_public_url(remote_path)
    except Exception as e:
        log.error(f"❌ Upload failed: {e}")
        audio_url = None
    
    # Cache the result
    if audio_url:
        try:
            supabase.table("cached_intros").upsert({
                "name_hash": intro_hash,
                "first_name": display_name,
                "audio_url": audio_url,
                "audio_duration": duration
            }).execute()
        except:
            pass
    
    # Cleanup temp file
    try:
        os.remove(temp_path)
    except:
        pass
    
    return {
        "audio_url": audio_url,
        "audio_duration": duration
    }


# ============================================
# SCRIPT GENERATION (for segment creation)
# ============================================

def generate_dialogue_script(content: str, target_words: int) -> str | None:
    """Generate dialogue script with Groq."""
    
    if not groq_client:
        log.error("❌ Groq client not available!")
        return None
    
    prompt = USER_PROMPT.format(words=target_words, content=content[:6000])
    
    log.info(f"📝 Generating {target_words}-word dialogue script")
    
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
            
            # Validation
            has_a = '[A]' in script or '[a]' in script.lower()
            has_b = '[B]' in script or '[b]' in script.lower()
            
            log.info(f"📄 Script generated (attempt {attempt+1}): has_A={has_a}, has_B={has_b}")
            
            if has_a or has_b:
                return script
            
            # Retry with stronger instruction
            prompt = prompt + "\n\nATTENTION: Tu DOIS utiliser [A] et [B] pour marquer chaque réplique!"
            
        except Exception as e:
            log.error(f"❌ Generation failed: {e}")
    
    return None


# ============================================
# UTILITY EXPORTS
# ============================================

def upload_audio(local_path: str, remote_path: str) -> str | None:
    """Upload audio to Supabase storage."""
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


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc.replace('www.', '')
    except:
        return "source"
