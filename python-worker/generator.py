"""
Keernel Generator V3.1 - Dual Voice Dialogue (Fixed)

Architecture:
- Groq (Llama 3.3 70B) for script generation
- OpenAI TTS for dual voice synthesis (Breeze & Vale)
- No Azure TTS

Dialogue Format:
- [VOICE_A] Breeze: L'expert pédagogue (voix: "nova")
- [VOICE_B] Vale: Le challenger pragmatique (voix: "onyx")

FIX: Improved parsing to handle LLM output variations
"""
import os
import re
import tempfile
from datetime import datetime
from urllib.parse import urlparse
import structlog

log = structlog.get_logger()

# ============================================
# CLIENTS INITIALIZATION
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
# VOICE CONFIGURATION (Fixed Duo)
# ============================================

# Breeze: Expert pédagogue - voix claire et posée
VOICE_BREEZE = "nova"

# Vale: Challenger pragmatique - voix plus grave et directe
VOICE_VALE = "onyx"

# Voice tags in script
VOICE_TAG_A = "[VOICE_A]"  # Breeze
VOICE_TAG_B = "[VOICE_B]"  # Vale

# ============================================
# DIALOGUE SYSTEM PROMPT
# ============================================

DIALOGUE_SYSTEM_PROMPT = """Tu es un scénariste de podcast professionnel. Tu crées des scripts de dialogue entre deux hôtes en français.

## LES DEUX HÔTES

**Breeze** ([VOICE_A]) - L'Expert Pédagogue
- Pose le cadre, expose les faits, les chiffres et le contexte
- Vulgarise sans simplifier à l'excès
- Ton : Calme, précis, informatif

**Vale** ([VOICE_B]) - Le Challenger Pragmatique  
- Pose les questions que se pose l'auditeur
- Souligne les risques, limites et implications concrètes
- Ton : Direct, interrogatif, terre-à-terre
- Questions types : "Concrètement, ça change quoi ?", "Oui mais le risque c'est...", "Attends, ça veut dire que..."

## RÈGLES D'OR

### Style Anti-IA (CRUCIAL)
INTERDICTIONS ABSOLUES :
- Superlatifs : "révolutionnaire", "incroyable", "passionnant", "fascinant"
- Enthousiasme artificiel : "C'est vraiment excitant !", "Quelle époque formidable !"
- Bruit conversationnel : "C'est une super question Vale", "Je suis content d'être là"
- Méta-discours : "Passons à notre prochain sujet", "Comme on l'a vu"

AUTORISÉ :
- Ton factuel et analytique
- Scepticisme constructif
- Questions directes et pragmatiques

### Accessibilité
- L'auditeur est intelligent mais NON-EXPERT du sujet
- Tout terme technique doit être expliqué par sa fonction ou son impact
- Pas de jargon brut : "L-L-M, c'est-à-dire un modèle de langage comme ChatGPT..."

### Phonétique TTS (OBLIGATOIRE)
Écris les anglicismes phonétiquement pour OpenAI TTS :
- "LLM" → "elle-elle-aime"
- "GPU" → "jé-pé-u"  
- "CEO" → "si-i-o"
- "AI" → "A-I"
- "startup" → "start-eupe"
- "blockchain" → "bloque-chaîne"
- "NVIDIA" → "ène-vidia"
- "OpenAI" → "Opène-A-I"
- "ChatGPT" → "Tchatte-G-P-T"

### Format du Script - CRITIQUE
Chaque réplique DOIT commencer par [VOICE_A] ou [VOICE_B] sur sa propre ligne.
ALTERNE OBLIGATOIREMENT entre [VOICE_A] et [VOICE_B].

EXEMPLE CORRECT :
[VOICE_A]
Breeze expose un fait ou une information.

[VOICE_B]
Vale réagit, questionne ou nuance.

[VOICE_A]
Breeze répond ou approfondit.

[VOICE_B]
Vale conclut avec une perspective pratique.

### Structure Narrative
1. ACCROCHE : Breeze ou Vale lance le sujet
2. DÉVELOPPEMENT : Ping-pong OBLIGATOIRE entre les deux voix
3. CONCLUSION : Insight pratique ou perspective

### Rythme
- Répliques de 2-4 phrases maximum
- ALTERNANCE OBLIGATOIRE (jamais deux [VOICE_A] ou deux [VOICE_B] consécutifs)
- Minimum 4 répliques au total (2 de chaque voix)
"""

DIALOGUE_USER_PROMPT = """Crée un script de dialogue podcast de {duration} minutes (~{word_count} mots au total).

## SOURCES À COUVRIR :
{sources}

## CONTRAINTES STRICTES :
1. Format : Chaque réplique commence par [VOICE_A] ou [VOICE_B]
2. ALTERNANCE OBLIGATOIRE entre les voix (jamais deux [VOICE_A] ou [VOICE_B] consécutifs)
3. Minimum 6 répliques (3 de chaque voix)
4. Durée : ~{word_count} mots total
5. Style : Factuel, analytique, ZÉRO superlatif

## STRUCTURE :
- Breeze ([VOICE_A]) : Faits, contexte, chiffres
- Vale ([VOICE_B]) : Questions, limites, implications concrètes

Script (commence directement par [VOICE_A] ou [VOICE_B]) :"""


# ============================================
# SCRIPT NORMALIZATION
# ============================================

def normalize_voice_tags(script: str) -> str:
    """
    Normalize voice tags to ensure consistent format.
    Handles variations like [VOICE A], [voice_a], [Voice_A], etc.
    """
    # Pattern to catch various formats
    patterns = [
        (r'\[VOICE[\s_-]*A\]', '[VOICE_A]'),
        (r'\[VOICE[\s_-]*B\]', '[VOICE_B]'),
        (r'\[voice[\s_-]*a\]', '[VOICE_A]'),
        (r'\[voice[\s_-]*b\]', '[VOICE_B]'),
        (r'\[Voice[\s_-]*A\]', '[VOICE_A]'),
        (r'\[Voice[\s_-]*B\]', '[VOICE_B]'),
        (r'\*\*\[VOICE_A\]\*\*', '[VOICE_A]'),
        (r'\*\*\[VOICE_B\]\*\*', '[VOICE_B]'),
        (r'VOICE_A:', '[VOICE_A]'),
        (r'VOICE_B:', '[VOICE_B]'),
        (r'Breeze\s*:', '[VOICE_A]'),
        (r'Vale\s*:', '[VOICE_B]'),
        (r'\[Breeze\]', '[VOICE_A]'),
        (r'\[Vale\]', '[VOICE_B]'),
    ]
    
    normalized = script
    for pattern, replacement in patterns:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    
    return normalized


# ============================================
# DIALOGUE SCRIPT GENERATION
# ============================================

def generate_dialogue_script(
    sources: list[dict],
    target_duration: int = 10
) -> str | None:
    """
    Generate a dual-voice dialogue script using Groq Llama 3.
    
    Returns script with [VOICE_A] and [VOICE_B] tags.
    """
    if not sources:
        log.warning("No sources provided")
        return None
    
    if not groq_client:
        log.error("Groq client not initialized - missing GROQ_API_KEY")
        return None
    
    # ~150 words per minute for dialogue
    target_word_count = target_duration * 150
    
    # Format sources
    sources_text = ""
    for i, source in enumerate(sources, 1):
        content = source.get("content", "")[:5000]
        sources_text += f"\n---\nSource {i}: {source.get('title', 'Sans titre')}\nURL: {source.get('url', 'N/A')}\n\n{content}\n"
    
    user_prompt = DIALOGUE_USER_PROMPT.format(
        duration=target_duration,
        word_count=target_word_count,
        sources=sources_text
    )
    
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            log.info("Generating dialogue script", 
                    num_sources=len(sources), 
                    target_duration=target_duration,
                    attempt=attempt + 1)
            
            extra_instruction = ""
            if attempt > 0:
                extra_instruction = "\n\nATTENTION CRITIQUE: Tu DOIS alterner entre [VOICE_A] et [VOICE_B]. Minimum 3 répliques de chaque voix!"
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": DIALOGUE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt + extra_instruction}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            
            script = response.choices[0].message.content
            
            # Normalize the script
            script = normalize_voice_tags(script)
            
            # Count voice tags
            voice_a_count = script.count(VOICE_TAG_A)
            voice_b_count = script.count(VOICE_TAG_B)
            word_count = len(script.split())
            
            log.info("Script generated", 
                    attempt=attempt + 1,
                    word_count=word_count, 
                    voice_a_count=voice_a_count,
                    voice_b_count=voice_b_count)
            
            # Validate both voices are present
            if voice_a_count >= 2 and voice_b_count >= 2:
                log.info("Dialogue script validated successfully")
                return script
            
            log.warning("Script missing sufficient voice tags", 
                       voice_a=voice_a_count, 
                       voice_b=voice_b_count)
            
        except Exception as e:
            log.error("Failed to generate dialogue script", 
                     attempt=attempt + 1, 
                     error=str(e))
    
    log.error("All attempts failed to generate valid dialogue script")
    return None


# ============================================
# SCRIPT PARSING (IMPROVED)
# ============================================

def parse_dialogue_script(script: str) -> list[dict]:
    """
    Parse a dialogue script into voice segments.
    
    Returns list of {"voice": "A"|"B", "text": "..."}
    """
    if not script:
        log.error("Empty script provided to parser")
        return []
    
    # First normalize the tags
    script = normalize_voice_tags(script)
    
    segments = []
    
    # Split by voice tags (case insensitive, flexible spacing)
    pattern = r'\[VOICE_([AB])\]'
    parts = re.split(pattern, script, flags=re.IGNORECASE)
    
    log.debug("Script parsing", 
             script_length=len(script),
             parts_count=len(parts),
             first_100_chars=script[:100])
    
    # parts[0] is before first tag (usually empty or preamble)
    # Then alternates: voice_letter, text, voice_letter, text...
    
    i = 1
    while i < len(parts):
        voice = parts[i].upper()  # Ensure uppercase "A" or "B"
        
        if voice not in ("A", "B"):
            log.warning("Invalid voice identifier", voice=voice)
            i += 1
            continue
        
        if i + 1 < len(parts):
            text = parts[i + 1].strip()
            # Clean up the text
            text = re.sub(r'^\s*\n+', '', text)  # Remove leading newlines
            text = re.sub(r'\n+\s*$', '', text)  # Remove trailing newlines
            text = text.strip()
            
            if text:
                segments.append({
                    "voice": voice,
                    "text": text
                })
                log.debug("Parsed segment", 
                         index=len(segments),
                         voice=voice, 
                         text_length=len(text),
                         preview=text[:50] + "..." if len(text) > 50 else text)
        i += 2
    
    # Log summary
    voice_a_segments = sum(1 for s in segments if s["voice"] == "A")
    voice_b_segments = sum(1 for s in segments if s["voice"] == "B")
    
    log.info("Dialogue parsed", 
            total_segments=len(segments),
            voice_a_segments=voice_a_segments,
            voice_b_segments=voice_b_segments)
    
    if voice_b_segments == 0:
        log.error("NO VOICE_B SEGMENTS FOUND - Script may not be dialogue format")
        log.debug("Full script for debugging", script=script[:500])
    
    return segments


# ============================================
# DUAL VOICE TTS (OpenAI Only)
# ============================================

def generate_dialogue_audio(
    script: str,
    output_path: str = None
) -> str | None:
    """
    Generate audio for a dialogue script with two distinct voices.
    
    1. Parse script into voice segments
    2. Generate audio for each segment with appropriate voice
    3. Combine into final audio file
    """
    if not script:
        log.warning("No script provided")
        return None
    
    if not openai_client:
        log.error("OpenAI client not initialized - missing OPENAI_API_KEY")
        return None
    
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"dialogue_{timestamp}.mp3")
    
    # Parse script
    segments = parse_dialogue_script(script)
    
    if not segments:
        log.error("No segments parsed from script - falling back to single voice")
        # Fallback: generate as single voice
        return generate_single_voice_audio(script, VOICE_BREEZE, output_path)
    
    # Check if we have both voices
    voices_used = set(s["voice"] for s in segments)
    log.info("Generating dialogue audio", 
            segments=len(segments),
            voices_used=list(voices_used))
    
    if "B" not in voices_used:
        log.warning("Only VOICE_A found - no dialogue detected")
    
    # Generate audio for each segment
    audio_files = []
    
    for i, segment in enumerate(segments):
        voice = VOICE_BREEZE if segment["voice"] == "A" else VOICE_VALE
        text = segment["text"]
        
        log.info(f"Generating segment {i+1}/{len(segments)}", 
                voice=voice, 
                voice_id=segment["voice"],
                chars=len(text))
        
        try:
            segment_path = output_path.replace(".mp3", f"_seg{i:03d}.mp3")
            
            # Handle OpenAI 4096 char limit
            if len(text) > 4000:
                # Split long segments
                chunks = split_text_for_tts(text, 3800)
                chunk_files = []
                
                for j, chunk in enumerate(chunks):
                    chunk_path = output_path.replace(".mp3", f"_seg{i:03d}_chunk{j}.mp3")
                    response = openai_client.audio.speech.create(
                        model="tts-1-hd",
                        voice=voice,
                        input=chunk
                    )
                    response.stream_to_file(chunk_path)
                    chunk_files.append(chunk_path)
                
                # Combine chunks
                combine_audio_files(chunk_files, segment_path)
                
                # Cleanup chunk files
                for cf in chunk_files:
                    try:
                        os.remove(cf)
                    except:
                        pass
            else:
                response = openai_client.audio.speech.create(
                    model="tts-1-hd",
                    voice=voice,
                    input=text
                )
                response.stream_to_file(segment_path)
            
            audio_files.append(segment_path)
            log.debug("Segment audio generated", segment=i, voice=voice, chars=len(text))
            
        except Exception as e:
            log.error("Failed to generate segment audio", segment=i, error=str(e))
            continue
    
    if not audio_files:
        log.error("No audio segments generated")
        return None
    
    # Combine all segments with small pauses
    try:
        combine_dialogue_audio(audio_files, output_path)
        
        # Cleanup segment files
        for f in audio_files:
            try:
                os.remove(f)
            except:
                pass
        
        duration = get_audio_duration(output_path)
        log.info("Dialogue audio generated", 
                output_path=output_path, 
                duration_sec=duration,
                segments=len(audio_files),
                voices_used=list(voices_used))
        
        return output_path
        
    except Exception as e:
        log.error("Failed to combine dialogue audio", error=str(e))
        return None


def generate_single_voice_audio(text: str, voice: str, output_path: str) -> str | None:
    """Fallback single voice generation."""
    try:
        if len(text) <= 4000:
            response = openai_client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input=text
            )
            response.stream_to_file(output_path)
        else:
            chunks = split_text_for_tts(text, 3800)
            audio_files = []
            for i, chunk in enumerate(chunks):
                chunk_path = output_path.replace(".mp3", f"_part{i}.mp3")
                response = openai_client.audio.speech.create(
                    model="tts-1-hd",
                    voice=voice,
                    input=chunk
                )
                response.stream_to_file(chunk_path)
                audio_files.append(chunk_path)
            combine_audio_files(audio_files, output_path)
            for f in audio_files:
                try:
                    os.remove(f)
                except:
                    pass
        return output_path
    except Exception as e:
        log.error("Single voice generation failed", error=str(e))
        return None


def combine_dialogue_audio(input_files: list[str], output_path: str):
    """
    Combine dialogue segments with natural pauses between speakers.
    """
    from pydub import AudioSegment
    
    # Small pause between speakers (300ms)
    pause = AudioSegment.silent(duration=300)
    
    combined = AudioSegment.empty()
    
    for i, file_path in enumerate(input_files):
        try:
            audio = AudioSegment.from_mp3(file_path)
            combined += audio
            
            # Add pause after each segment (except last)
            if i < len(input_files) - 1:
                combined += pause
                
        except Exception as e:
            log.warning("Failed to load segment", file=file_path, error=str(e))
    
    # Export with good quality
    combined.export(output_path, format="mp3", bitrate="192k")


# ============================================
# LEGACY COMPATIBLE FUNCTIONS
# ============================================

def generate_audio(
    script: str,
    voice: str = "nova",
    output_path: str = None
) -> str | None:
    """
    Legacy function - now uses OpenAI TTS directly.
    For dialogue scripts, use generate_dialogue_audio() instead.
    """
    if not script:
        log.warning("No script provided")
        return None
    
    if not openai_client:
        log.error("OpenAI client not initialized")
        return None
    
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"audio_{timestamp}.mp3")
    
    # Normalize script first
    script = normalize_voice_tags(script)
    
    # Check if this is a dialogue script
    if VOICE_TAG_A in script and VOICE_TAG_B in script:
        log.info("Dialogue detected, using dual-voice generation")
        return generate_dialogue_audio(script, output_path)
    elif VOICE_TAG_A in script or VOICE_TAG_B in script:
        log.warning("Only one voice tag found - attempting dialogue anyway")
        return generate_dialogue_audio(script, output_path)
    
    # Single voice generation
    try:
        valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        if voice not in valid_voices:
            voice = "nova"
        
        log.info("Generating single-voice audio", voice=voice)
        
        if len(script) <= 4000:
            response = openai_client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input=script
            )
            response.stream_to_file(output_path)
        else:
            chunks = split_text_for_tts(script, 3800)
            audio_files = []
            
            for i, chunk in enumerate(chunks):
                chunk_path = output_path.replace(".mp3", f"_part{i}.mp3")
                response = openai_client.audio.speech.create(
                    model="tts-1-hd",
                    voice=voice,
                    input=chunk
                )
                response.stream_to_file(chunk_path)
                audio_files.append(chunk_path)
            
            combine_audio_files(audio_files, output_path)
            
            for f in audio_files:
                try:
                    os.remove(f)
                except:
                    pass
        
        duration = get_audio_duration(output_path)
        log.info("Audio generated", output_path=output_path, duration_sec=duration)
        return output_path
        
    except Exception as e:
        log.error("Failed to generate audio", error=str(e))
        return None


# Keep old function name for compatibility
def generate_podcast_script(
    sources: list[dict],
    target_duration: int = 10,
    language: str = "fr"
) -> str | None:
    """
    Legacy wrapper - now generates dialogue script.
    """
    return generate_dialogue_script(sources, target_duration)


# ============================================
# UTILITY FUNCTIONS
# ============================================

def split_text_for_tts(text: str, max_size: int) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    chunks = []
    current = ""
    
    sentences = text.replace("...", "…").split(". ")
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if not sentence.endswith((".", "!", "?", "…")):
            sentence += "."
        
        if len(current) + len(sentence) + 1 <= max_size:
            current += " " + sentence if current else sentence
        else:
            if current:
                chunks.append(current.strip())
            current = sentence
    
    if current:
        chunks.append(current.strip())
    
    return chunks


def combine_audio_files(input_files: list[str], output_path: str):
    """Combine multiple audio files using pydub."""
    from pydub import AudioSegment
    
    combined = AudioSegment.empty()
    for file_path in input_files:
        audio = AudioSegment.from_mp3(file_path)
        combined += audio
    
    combined.export(output_path, format="mp3", bitrate="192k")


def get_audio_duration(file_path: str) -> int:
    """Get duration of audio file in seconds."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(file_path)
        return len(audio) // 1000
    except:
        return 0


# ============================================
# TITLE GENERATION
# ============================================

def generate_episode_title(sources: list[dict], script: str = None) -> str:
    """Generate episode title."""
    today = datetime.now().strftime("%d %B")
    
    if len(sources) == 1:
        title = sources[0].get('title', 'Votre contenu')[:50]
        return f"{today} - {title}"
    
    if not groq_client:
        return f"Keernel - {today}"
    
    try:
        source_titles = [s.get('title', '')[:50] for s in sources[:5]]
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Génère un titre court et factuel (max 50 caractères) qui résume ces sujets. Pas de guillemets, pas de superlatifs."},
                {"role": "user", "content": f"Sujets: {', '.join(source_titles)}"}
            ],
            temperature=0.7,
            max_tokens=30
        )
        
        title = response.choices[0].message.content.strip().strip('"\'')
        return f"{today} - {title}"
    except:
        return f"Keernel - {today}"


# ============================================
# BUILD SOURCES DATA (for Show Notes)
# ============================================

def build_sources_data(sources: list[dict]) -> list[dict]:
    """Build sources_data JSON for episode show notes."""
    result = []
    
    for source in sources:
        url = source.get("url", "")
        domain = ""
        try:
            domain = urlparse(url).netloc.replace("www.", "")
        except:
            pass
        
        result.append({
            "title": source.get("title", "Source"),
            "url": url,
            "domain": domain or "unknown"
        })
    
    return result
