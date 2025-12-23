"""
Keernel Generator V3 - Dual Voice Dialogue

Architecture:
- Groq (Llama 3.3 70B) for script generation
- OpenAI TTS for dual voice synthesis (Breeze & Vale)
- No Azure TTS

Dialogue Format:
- [VOICE_A] Breeze: L'expert pédagogue (voix: "nova")
- [VOICE_B] Vale: Le challenger pragmatique (voix: "onyx")
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

### Format du Script
Chaque réplique DOIT commencer par [VOICE_A] ou [VOICE_B] sur sa propre ligne :

[VOICE_A]
Breeze expose un fait ou une information.

[VOICE_B]
Vale réagit, questionne ou nuance.

[VOICE_A]
Breeze répond ou approfondit.

### Structure Narrative
1. ACCROCHE : Vale pose une question intrigante ou Breeze balance un fait percutant
2. DÉVELOPPEMENT : Ping-pong naturel entre les deux voix
3. CONCLUSION : Insight pratique ou perspective (pas de "merci d'avoir écouté")

### Rythme
- Répliques de 2-4 phrases maximum
- Alternance fréquente (pas de monologue)
- Questions de Vale pour relancer l'attention
"""

DIALOGUE_USER_PROMPT = """Crée un script de dialogue podcast de {duration} minutes (~{word_count} mots au total).

## SOURCES À COUVRIR :
{sources}

## CONTRAINTES :
1. Format STRICT : Chaque réplique commence par [VOICE_A] ou [VOICE_B]
2. Durée : ~{word_count} mots total (tolérance ±15%)
3. Style : Factuel, analytique, ZÉRO superlatif
4. Phonétique TTS pour tous les anglicismes
5. Alternance fréquente entre les voix

## STRUCTURE :
- Breeze ([VOICE_A]) : Faits, contexte, chiffres
- Vale ([VOICE_B]) : Questions, limites, implications concrètes

Script (commence directement par une réplique) :"""


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
    
    try:
        log.info("Generating dialogue script", num_sources=len(sources), target_duration=target_duration)
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": DIALOGUE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )
        
        script = response.choices[0].message.content
        word_count = len(script.split())
        
        # Validate script has voice tags
        if VOICE_TAG_A not in script or VOICE_TAG_B not in script:
            log.warning("Script missing voice tags, regenerating...")
            # Try once more with explicit instruction
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": DIALOGUE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt + "\n\nATTENTION: Chaque réplique DOIT commencer par [VOICE_A] ou [VOICE_B] !"}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            script = response.choices[0].message.content
        
        log.info("Dialogue script generated", 
                word_count=word_count, 
                est_duration_min=round(word_count/150, 1),
                voice_a_count=script.count(VOICE_TAG_A),
                voice_b_count=script.count(VOICE_TAG_B))
        
        return script
    
    except Exception as e:
        log.error("Failed to generate dialogue script", error=str(e))
        return None


# ============================================
# SCRIPT PARSING
# ============================================

def parse_dialogue_script(script: str) -> list[dict]:
    """
    Parse a dialogue script into voice segments.
    
    Returns list of {"voice": "A"|"B", "text": "..."}
    """
    segments = []
    
    # Split by voice tags
    pattern = r'\[VOICE_([AB])\]'
    parts = re.split(pattern, script)
    
    # parts[0] is before first tag (usually empty)
    # Then alternates: voice_letter, text, voice_letter, text...
    
    i = 1
    while i < len(parts):
        voice = parts[i]  # "A" or "B"
        
        if i + 1 < len(parts):
            text = parts[i + 1].strip()
            if text:
                segments.append({
                    "voice": voice,
                    "text": text
                })
        i += 2
    
    log.info("Parsed dialogue", segments=len(segments))
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
        log.error("No segments parsed from script")
        return None
    
    # Generate audio for each segment
    audio_files = []
    
    for i, segment in enumerate(segments):
        voice = VOICE_BREEZE if segment["voice"] == "A" else VOICE_VALE
        text = segment["text"]
        
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
                        model="tts-1-hd",  # Higher quality for dialogue
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
                segments=len(audio_files))
        
        return output_path
        
    except Exception as e:
        log.error("Failed to combine dialogue audio", error=str(e))
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
    
    # Check if this is a dialogue script
    if VOICE_TAG_A in script or VOICE_TAG_B in script:
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
