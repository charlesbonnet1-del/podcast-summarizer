"""
AI generation utilities for creating podcast scripts and audio.
Stack: Groq (Llama 3) for LLM + Azure TTS (with OpenAI fallback)
"""
import os
import tempfile
from datetime import datetime
from urllib.parse import urlparse
import structlog

log = structlog.get_logger()

# ============================================
# CLIENTS INITIALIZATION
# ============================================

# Groq for LLM (fast & cheap)
from groq import Groq
groq_client = None
if os.getenv("GROQ_API_KEY"):
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# OpenAI for fallback TTS
from openai import OpenAI
openai_client = None
if os.getenv("OPENAI_API_KEY"):
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Azure Speech SDK for high-quality TTS
azure_speech_key = os.getenv("AZURE_SPEECH_KEY")
azure_speech_region = os.getenv("AZURE_SPEECH_REGION", "westeurope")


# ============================================
# PROMPTS
# ============================================

SCRIPT_SYSTEM_PROMPT = """Tu es un journaliste radio expert en synthèse d'informations. Tu crées des scripts audio engageants et informatifs à partir de contenus variés.

RÈGLES DE STYLE :
- Ton : Conversationnel, dynamique et professionnel. Comme un flash info moderne.
- Structure : Accroche → Points clés → Conclusion avec perspective.
- Langage : Simple et accessible. Évite le jargon technique.
- Rythme : Phrases courtes et percutantes. Questions rhétoriques pour maintenir l'attention.

RÈGLES DE FORMAT :
- N'utilise JAMAIS de markdown, d'astérisques, de tirets ou de listes à puces.
- Écris en paragraphes fluides, comme un vrai script radio.
- Transitions naturelles : "Passons à...", "Ce qui est intéressant...", "Et maintenant..."
- Conclus par un insight ou une perspective d'avenir.

RÈGLES DE CONTENU :
- Sois factuel. Si une information est incertaine, dis-le.
- Cite tes sources naturellement : "Selon cet article...", "Cette vidéo explique..."
- Adapte la langue au contenu source (français si sources françaises).
"""

USER_PROMPT_TEMPLATE = """Crée un script de podcast de {duration} minutes basé sur ces contenus.

SOURCES :
{sources}

CONSIGNES :
- Durée : {duration} min (~{word_count} mots)
- Commence directement, pas de "Bienvenue..."
- Synthétise les infos clés de manière engageante
- Trouve les connexions entre les sources
- Termine par un insight pratique

Script :"""


# ============================================
# SCRIPT GENERATION (Groq Llama 3)
# ============================================

def generate_podcast_script(
    sources: list[dict],
    target_duration: int = 10,
    language: str = "fr"
) -> str | None:
    """Generate podcast script using Groq Llama 3."""
    
    if not sources:
        log.warning("No sources provided")
        return None
    
    if not groq_client:
        log.error("Groq client not initialized - missing GROQ_API_KEY")
        return None
    
    # ~150 words per minute for speech
    target_word_count = target_duration * 150
    
    # Format sources
    sources_text = ""
    for i, source in enumerate(sources, 1):
        content = source.get("content", "")[:6000]  # Limit content
        sources_text += f"\n---\nSource {i}: {source.get('title', 'Sans titre')}\nURL: {source.get('url', 'N/A')}\n\n{content}\n"
    
    user_prompt = USER_PROMPT_TEMPLATE.format(
        duration=target_duration,
        word_count=target_word_count,
        sources=sources_text
    )
    
    try:
        log.info("Generating script with Groq", num_sources=len(sources), target_duration=target_duration)
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=3000
        )
        
        script = response.choices[0].message.content
        word_count = len(script.split())
        
        log.info("Script generated", word_count=word_count, est_duration_min=round(word_count/150, 1))
        return script
    
    except Exception as e:
        log.error("Failed to generate script", error=str(e))
        return None


# ============================================
# AUDIO GENERATION (Azure TTS + OpenAI Fallback)
# ============================================

# Map OpenAI voices to Azure voices
VOICE_MAP_AZURE = {
    "alloy": "fr-FR-DeniseNeural",
    "echo": "fr-FR-HenriNeural",
    "fable": "fr-FR-DeniseNeural",
    "onyx": "fr-FR-HenriNeural",
    "nova": "fr-FR-DeniseNeural",
    "shimmer": "fr-FR-DeniseNeural",
}

def generate_audio(
    script: str,
    voice: str = "alloy",
    output_path: str = None
) -> str | None:
    """
    Generate audio using Azure TTS (primary) or OpenAI TTS (fallback).
    Voice can be OpenAI voice name (alloy, nova, etc.) - will be mapped to Azure.
    """
    if not script:
        log.warning("No script provided")
        return None
    
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"episode_{timestamp}.mp3")
    
    # Try Azure TTS first
    if azure_speech_key:
        # Map OpenAI voice to Azure voice
        azure_voice = VOICE_MAP_AZURE.get(voice, "fr-FR-DeniseNeural")
        result = generate_audio_azure(script, azure_voice, output_path)
        if result:
            return result
        log.warning("Azure TTS failed, trying OpenAI fallback")
    
    # Fallback to OpenAI TTS
    if openai_client:
        return generate_audio_openai(script, voice, output_path)
    
    log.error("No TTS provider available")
    return None


def generate_audio_azure(script: str, voice: str, output_path: str) -> str | None:
    """Generate audio using Azure Cognitive Services Speech."""
    try:
        import azure.cognitiveservices.speech as speechsdk
        
        log.info("Generating audio with Azure TTS", voice=voice)
        
        # Configure Azure Speech
        speech_config = speechsdk.SpeechConfig(
            subscription=azure_speech_key,
            region=azure_speech_region
        )
        speech_config.speech_synthesis_voice_name = voice
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        
        # Create audio output
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
        
        # Create synthesizer
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        # Synthesize
        result = synthesizer.speak_text_async(script).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            duration = get_audio_duration(output_path)
            log.info("Azure TTS complete", output_path=output_path, duration_sec=duration)
            return output_path
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            log.error("Azure TTS canceled", reason=cancellation.reason, error=cancellation.error_details)
            return None
    
    except Exception as e:
        log.error("Azure TTS failed", error=str(e))
        return None


def generate_audio_openai(script: str, voice: str, output_path: str) -> str | None:
    """Generate audio using OpenAI TTS (fallback)."""
    # Validate OpenAI voice
    valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    if voice not in valid_voices:
        voice = "nova"  # Good default for French
    
    try:
        log.info("Generating audio with OpenAI TTS (fallback)", voice=voice)
        
        # OpenAI TTS limit: 4096 chars per request
        max_chunk = 4000
        
        if len(script) <= max_chunk:
            response = openai_client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=script
            )
            response.stream_to_file(output_path)
        else:
            # Split and combine
            chunks = split_script_for_tts(script, max_chunk)
            audio_files = []
            
            for i, chunk in enumerate(chunks):
                chunk_path = output_path.replace(".mp3", f"_part{i}.mp3")
                response = openai_client.audio.speech.create(
                    model="tts-1",
                    voice=voice,
                    input=chunk
                )
                response.stream_to_file(chunk_path)
                audio_files.append(chunk_path)
            
            combine_audio_files(audio_files, output_path)
            
            for f in audio_files:
                os.remove(f)
        
        duration = get_audio_duration(output_path)
        log.info("OpenAI TTS complete", output_path=output_path, duration_sec=duration)
        return output_path
    
    except Exception as e:
        log.error("OpenAI TTS failed", error=str(e))
        return None


def split_script_for_tts(script: str, max_size: int) -> list[str]:
    """Split script into chunks at sentence boundaries."""
    chunks = []
    current = ""
    
    sentences = script.replace("...", "…").split(". ")
    
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
    
    combined.export(output_path, format="mp3")


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
        return f"Daily Digest - {today}"
    
    try:
        source_titles = [s.get('title', '')[:50] for s in sources[:5]]
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Génère un titre court et accrocheur (max 50 caractères) qui résume ces sujets. Pas de guillemets."},
                {"role": "user", "content": f"Sujets: {', '.join(source_titles)}"}
            ],
            temperature=0.8,
            max_tokens=30
        )
        
        title = response.choices[0].message.content.strip().strip('"\'')
        return f"{today} - {title}"
    except:
        return f"Daily Digest - {today}"


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
