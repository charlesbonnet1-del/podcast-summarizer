"""
Keernel Generator V5 - Minimal exports for stitcher.py

This file exists for backward compatibility.
All logic is now in stitcher.py
"""
import os
import structlog

log = structlog.get_logger()

# ============================================
# CLIENTS (exported for compatibility)
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
# VOICE CONFIG (exported)
# ============================================

VOICE_BREEZE = "nova"
VOICE_VALE = "onyx"
VOICE_TAG_A = "[VOICE_A]"
VOICE_TAG_B = "[VOICE_B]"

# ============================================
# UTILITY (exported)
# ============================================

def get_audio_duration(file_path: str) -> int:
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_mp3(file_path)) // 1000
    except:
        return 0

def generate_dialogue_audio(script: str, output_path: str) -> str | None:
    """Wrapper - actual logic in stitcher.py"""
    from stitcher import generate_dialogue_audio as _gen
    return _gen(script, output_path)

def generate_dialogue_script(sources: list, duration: int = 10) -> str | None:
    """Legacy - not used"""
    return None

def generate_audio(script: str, voice: str = "nova", output_path: str = None) -> str | None:
    """Legacy wrapper"""
    if not output_path:
        import tempfile
        from datetime import datetime
        output_path = os.path.join(tempfile.gettempdir(), f"audio_{datetime.now().strftime('%H%M%S')}.mp3")
    
    if '[A]' in script or '[B]' in script or '[VOICE_' in script:
        return generate_dialogue_audio(script, output_path)
    
    # Single voice
    if not openai_client:
        return None
    try:
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=script
        )
        response.stream_to_file(output_path)
        return output_path
    except:
        return None
