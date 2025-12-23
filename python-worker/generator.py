"""
Keernel Generator V4 - Captivating Dialogue

EXPORTS for stitcher.py:
- VOICE_BREEZE, VOICE_VALE
- VOICE_TAG_A, VOICE_TAG_B  
- groq_client, openai_client
- get_audio_duration
- generate_dialogue_audio (if needed externally)
"""
import os
import re
import tempfile
from datetime import datetime
from urllib.parse import urlparse
import structlog

log = structlog.get_logger()

# ============================================
# CLIENTS
# ============================================

from groq import Groq
groq_client = None
if os.getenv("GROQ_API_KEY"):
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

from openai import OpenAI
openai_client = None
if os.getenv("OPENAI_API_KEY"):
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================
# VOICE CONFIG
# ============================================

VOICE_BREEZE = "nova"
VOICE_VALE = "onyx"
VOICE_TAG_A = "[VOICE_A]"
VOICE_TAG_B = "[VOICE_B]"

# ============================================
# AUDIO UTILS
# ============================================

def get_audio_duration(file_path: str) -> int:
    """Get duration in seconds."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(file_path)
        return len(audio) // 1000
    except:
        return 0


def normalize_voice_tags(script: str) -> str:
    """Normalize various voice tag formats to [VOICE_A] and [VOICE_B]."""
    patterns = [
        # Standard variations
        (r'\[VOICE[\s_-]*A\]', '[VOICE_A]'),
        (r'\[VOICE[\s_-]*B\]', '[VOICE_B]'),
        (r'\[voice[\s_-]*a\]', '[VOICE_A]'),
        (r'\[voice[\s_-]*b\]', '[VOICE_B]'),
        # Colon format
        (r'VOICE_A\s*:', '[VOICE_A]\n'),
        (r'VOICE_B\s*:', '[VOICE_B]\n'),
        # Bold markdown
        (r'\*\*\[VOICE_A\]\*\*', '[VOICE_A]'),
        (r'\*\*\[VOICE_B\]\*\*', '[VOICE_B]'),
        (r'\*\*VOICE_A\*\*\s*:', '[VOICE_A]\n'),
        (r'\*\*VOICE_B\*\*\s*:', '[VOICE_B]\n'),
        # Name formats
        (r'Breeze\s*:', '[VOICE_A]\n'),
        (r'Vale\s*:', '[VOICE_B]\n'),
        (r'\[Breeze\]', '[VOICE_A]'),
        (r'\[Vale\]', '[VOICE_B]'),
        (r'\*\*Breeze\*\*\s*:', '[VOICE_A]\n'),
        (r'\*\*Vale\*\*\s*:', '[VOICE_B]\n'),
        # Speaker format  
        (r'Speaker\s*A\s*:', '[VOICE_A]\n'),
        (r'Speaker\s*B\s*:', '[VOICE_B]\n'),
        (r'Host\s*1\s*:', '[VOICE_A]\n'),
        (r'Host\s*2\s*:', '[VOICE_B]\n'),
        # Numbered voices
        (r'\[VOICE\s*1\]', '[VOICE_A]'),
        (r'\[VOICE\s*2\]', '[VOICE_B]'),
    ]
    result = script
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def force_voice_alternation(segments: list[dict]) -> list[dict]:
    """Ensure voices alternate properly - if all same voice, force alternation."""
    if not segments:
        return segments
    
    voices = set(s["voice"] for s in segments)
    
    if len(voices) == 1:
        log.warning("Only one voice detected, forcing alternation")
        for i, seg in enumerate(segments):
            seg["voice"] = "A" if i % 2 == 0 else "B"
    else:
        for i in range(1, len(segments)):
            if segments[i]["voice"] == segments[i-1]["voice"]:
                segments[i]["voice"] = "B" if segments[i-1]["voice"] == "A" else "A"
    
    return segments


def parse_dialogue_script(script: str) -> list[dict]:
    """Parse into voice segments with robust fallback."""
    if not script:
        return []
    
    script = normalize_voice_tags(script)
    segments = []
    
    pattern = r'\[VOICE_([AB])\]'
    parts = re.split(pattern, script, flags=re.IGNORECASE)
    
    i = 1
    while i < len(parts):
        voice = parts[i].upper()
        if voice in ("A", "B") and i + 1 < len(parts):
            text = parts[i + 1].strip()
            text = re.sub(r'^\s*\n+', '', text)
            text = re.sub(r'\n+\s*$', '', text)
            if text:
                segments.append({"voice": voice, "text": text})
        i += 2
    
    # FALLBACK: If no voice tags found, split by paragraphs and alternate
    if not segments:
        log.warning("No voice tags parsed, using paragraph fallback")
        paragraphs = [p.strip() for p in script.split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in script.split('\n') if p.strip()]
        for i, para in enumerate(paragraphs):
            if para and len(para) > 10:
                segments.append({"voice": "A" if i % 2 == 0 else "B", "text": para})
    
    # Force proper alternation
    segments = force_voice_alternation(segments)
    
    return segments


def generate_dialogue_audio(script: str, output_path: str) -> str | None:
    """Generate dual-voice audio."""
    if not openai_client:
        return None
    
    segments = parse_dialogue_script(script)
    if not segments:
        log.error("No segments parsed")
        return None
    
    audio_files = []
    
    for i, seg in enumerate(segments):
        voice = VOICE_BREEZE if seg["voice"] == "A" else VOICE_VALE
        seg_path = output_path.replace(".mp3", f"_seg{i:03d}.mp3")
        
        try:
            response = openai_client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input=seg["text"],
                speed=1.05
            )
            response.stream_to_file(seg_path)
            audio_files.append(seg_path)
        except Exception as e:
            log.error(f"Segment {i} failed", error=str(e))
    
    if not audio_files:
        return None
    
    try:
        from pydub import AudioSegment
        pause = AudioSegment.silent(duration=250)
        combined = AudioSegment.empty()
        
        for i, path in enumerate(audio_files):
            combined += AudioSegment.from_mp3(path)
            if i < len(audio_files) - 1:
                combined += pause
        
        combined.export(output_path, format="mp3", bitrate="192k")
        
        for f in audio_files:
            try:
                os.remove(f)
            except:
                pass
        
        return output_path
    except Exception as e:
        log.error("Combine failed", error=str(e))
        return None


# ============================================
# LEGACY FUNCTIONS (for compatibility)
# ============================================

def generate_dialogue_script(sources: list[dict], target_duration: int = 10) -> str | None:
    """Legacy - now handled in stitcher."""
    return None


def generate_audio(script: str, voice: str = "nova", output_path: str = None) -> str | None:
    """Legacy wrapper."""
    if not output_path:
        output_path = os.path.join(tempfile.gettempdir(), f"audio_{datetime.now().strftime('%H%M%S')}.mp3")
    
    script = normalize_voice_tags(script)
    
    if VOICE_TAG_A in script or VOICE_TAG_B in script:
        return generate_dialogue_audio(script, output_path)
    
    # Single voice
    if not openai_client:
        return None
    
    try:
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=script,
            speed=1.05
        )
        response.stream_to_file(output_path)
        return output_path
    except:
        return None
