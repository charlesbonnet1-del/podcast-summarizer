"""
AI generation utilities for creating podcast scripts and audio.
"""
import os
import tempfile
from pathlib import Path
from datetime import datetime
from openai import OpenAI
import structlog

log = structlog.get_logger()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# System prompt for podcast script generation
SCRIPT_SYSTEM_PROMPT = """Tu es un animateur de podcast expert en synthèse d'informations. Tu crées des scripts audio engageants et informatifs à partir de contenu varié (articles, vidéos YouTube, podcasts).

RÈGLES DE STYLE :
- Ton : Conversationnel, enthousiaste mais professionnel. Comme si tu parlais à un ami intelligent.
- Structure : Introduction accrocheuse → Points clés → Conclusion avec takeaway actionnable.
- Langage : Simple et accessible. Évite le jargon technique sauf si nécessaire.
- Rythme : Varie la longueur des phrases. Utilise des questions rhétoriques pour maintenir l'attention.

RÈGLES DE FORMAT :
- N'utilise JAMAIS de markdown, d'astérisques, de tirets ou de listes à puces.
- Écris en paragraphes fluides, comme un vrai script de podcast.
- Ajoute des transitions naturelles entre les sujets : "Passons maintenant à...", "Ce qui est fascinant, c'est que...", "Et voici où ça devient intéressant..."
- Termine toujours par une conclusion qui résume le point principal et donne une perspective ou un conseil pratique.

RÈGLES DE CONTENU :
- Ne mens jamais. Si une information te semble incertaine, dis-le.
- Cite tes sources de manière naturelle : "D'après cet article de...", "Cette vidéo nous explique que..."
- Si le contenu est en anglais, tu peux le résumer en français si l'utilisateur est francophone, sinon reste en anglais.
"""

USER_PROMPT_TEMPLATE = """Crée un script de podcast de {duration} minutes environ basé sur le contenu suivant.

SOURCES À SYNTHÉTISER :
{sources}

INSTRUCTIONS :
- Durée cible : {duration} minutes (environ {word_count} mots)
- Commence directement par le contenu, pas de "Bienvenue dans ce podcast"
- Synthétise les informations clés de manière engageante
- Si plusieurs sources, trouve les connexions entre elles
- Termine par un insight ou conseil pratique

Génère uniquement le script, prêt à être lu."""


def generate_podcast_script(
    sources: list[dict],  # [{"title": str, "content": str, "url": str}, ...]
    target_duration: int = 15,  # minutes
    language: str = "en"
) -> str | None:
    """
    Generate a podcast script from multiple content sources.
    """
    if not sources:
        log.warning("No sources provided for script generation")
        return None
    
    # Estimate word count (average speaking rate: ~150 words/minute)
    target_word_count = target_duration * 150
    
    # Format sources for the prompt
    sources_text = ""
    for i, source in enumerate(sources, 1):
        # Truncate very long content to avoid token limits
        content = source.get("content", "")[:8000]
        sources_text += f"\n---\nSource {i}: {source.get('title', 'Untitled')}\nURL: {source.get('url', 'N/A')}\n\nContenu:\n{content}\n"
    
    user_prompt = USER_PROMPT_TEMPLATE.format(
        duration=target_duration,
        word_count=target_word_count,
        sources=sources_text
    )
    
    try:
        log.info("Generating podcast script", num_sources=len(sources), target_duration=target_duration)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )
        
        script = response.choices[0].message.content
        word_count = len(script.split())
        
        log.info("Script generated", word_count=word_count, estimated_duration=word_count/150)
        return script
    
    except Exception as e:
        log.error("Failed to generate script", error=str(e))
        return None


def generate_audio(
    script: str,
    voice: str = "alloy",
    output_path: str = None
) -> str | None:
    """
    Generate audio from script using OpenAI TTS.
    Returns the path to the generated MP3 file.
    """
    if not script:
        log.warning("No script provided for audio generation")
        return None
    
    # Validate voice
    valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    if voice not in valid_voices:
        voice = "alloy"
    
    # Generate output path if not provided
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"episode_{timestamp}.mp3")
    
    try:
        log.info("Generating audio", voice=voice, script_length=len(script))
        
        # OpenAI TTS has a limit of 4096 characters per request
        # For longer scripts, we need to split and concatenate
        max_chunk_size = 4000
        
        if len(script) <= max_chunk_size:
            # Single request
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=script
            )
            response.stream_to_file(output_path)
        else:
            # Split into chunks and combine
            chunks = split_script_for_tts(script, max_chunk_size)
            audio_files = []
            
            for i, chunk in enumerate(chunks):
                chunk_path = output_path.replace(".mp3", f"_part{i}.mp3")
                response = client.audio.speech.create(
                    model="tts-1",
                    voice=voice,
                    input=chunk
                )
                response.stream_to_file(chunk_path)
                audio_files.append(chunk_path)
            
            # Combine audio files
            combine_audio_files(audio_files, output_path)
            
            # Clean up chunk files
            for f in audio_files:
                os.remove(f)
        
        # Get audio duration
        duration = get_audio_duration(output_path)
        log.info("Audio generated", output_path=output_path, duration_seconds=duration)
        
        return output_path
    
    except Exception as e:
        log.error("Failed to generate audio", error=str(e))
        return None


def split_script_for_tts(script: str, max_size: int) -> list[str]:
    """
    Split a script into chunks suitable for TTS, trying to break at sentence boundaries.
    """
    chunks = []
    current_chunk = ""
    
    # Split by sentences (simple approach)
    sentences = script.replace("...", "…").split(". ")
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Add period back if it was removed
        if not sentence.endswith((".", "!", "?", "…")):
            sentence += "."
        
        if len(current_chunk) + len(sentence) + 1 <= max_size:
            current_chunk += " " + sentence if current_chunk else sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def combine_audio_files(input_files: list[str], output_path: str):
    """
    Combine multiple audio files into one using pydub.
    """
    from pydub import AudioSegment
    
    combined = AudioSegment.empty()
    
    for file_path in input_files:
        audio = AudioSegment.from_mp3(file_path)
        combined += audio
    
    combined.export(output_path, format="mp3")


def get_audio_duration(file_path: str) -> int:
    """Get duration of an audio file in seconds."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(file_path)
        return len(audio) // 1000  # Convert milliseconds to seconds
    except:
        return 0


def generate_episode_title(sources: list[dict], script: str = None) -> str:
    """Generate a title for the episode based on sources."""
    if len(sources) == 1:
        return f"Daily Digest: {sources[0].get('title', 'Your Content')}"
    
    # For multiple sources, generate a title
    try:
        source_titles = [s.get('title', '') for s in sources]
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Generate a short, catchy podcast episode title (max 60 chars) that summarizes these topics. No quotes or special characters."},
                {"role": "user", "content": f"Topics: {', '.join(source_titles)}"}
            ],
            temperature=0.8,
            max_tokens=50
        )
        
        title = response.choices[0].message.content.strip().strip('"\'')
        return f"Daily Digest: {title}"
    except:
        return f"Daily Digest: {datetime.now().strftime('%B %d, %Y')}"
