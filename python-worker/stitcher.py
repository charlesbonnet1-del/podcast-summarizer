"""
Keernel Stitcher V4 - Captivating Dialogue Podcast

CHANGEMENTS MAJEURS V4:
1. Intro avec OpenAI TTS (Breeze) - plus de Azure
2. Prompts captivants - style podcast engageant
3. Sélection intelligente des angles intéressants
4. Dialogue naturel avec vraie alternance Breeze/Vale
5. Vitesse de diction optimisée

RÈGLES DE FER:
- ZÉRO liste de courses
- ZÉRO méta-discours
- Angle UNIQUE et CAPTIVANT par sujet
- TENSION narrative entre les deux hôtes
"""
import os
import re
import tempfile
import subprocess
from datetime import datetime, date
from urllib.parse import urlparse
import unicodedata
from typing import Optional

import structlog
from dotenv import load_dotenv

from db import supabase
from extractor import extract_content

load_dotenv()
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
# VOICE CONFIGURATION
# ============================================

# Breeze: Expert - voix claire et posée
VOICE_BREEZE = "nova"

# Vale: Challenger - voix plus grave et directe  
VOICE_VALE = "onyx"

VOICE_TAG_A = "[VOICE_A]"  # Breeze
VOICE_TAG_B = "[VOICE_B]"  # Vale

# ============================================
# CONSTANTS
# ============================================

WORDS_PER_MINUTE = 160  # Légèrement plus rapide pour dynamisme

VERTICALS = {
    "ai_tech": {"name": "IA & Tech"},
    "politics": {"name": "Politique & Monde"},
    "finance": {"name": "Finance & Marchés"},
    "science": {"name": "Science & Santé"},
    "culture": {"name": "Culture & Divertissement"}
}

# ============================================
# PROMPTS CAPTIVANTS V4
# ============================================

SYSTEM_PROMPT_DIALOGUE = """Tu es le duo de podcasters le plus écouté de France. Ton secret : transformer n'importe quelle actu en conversation CAPTIVANTE.

## TES DEUX PERSONNALITÉS

**BREEZE** ([VOICE_A]) - Le vulgarisateur brillant
- Trouve toujours L'ANGLE qui rend le sujet fascinant
- Utilise des ANALOGIES percutantes ("C'est comme si...")  
- Donne des CHIFFRES qui claquent, pas des listes
- Ton: Passionné mais jamais exalté

**VALE** ([VOICE_B]) - L'avocat du diable bienveillant
- Pose LA question que tout le monde pense tout bas
- Joue le sceptique: "Attends, mais concrètement..."
- Cherche l'impact HUMAIN: "Et pour les gens normaux?"
- Ton: Curieux, légèrement provocateur

## RÈGLES D'OR ABSOLUES

### ❌ INTERDIT - Le style "liste de courses"
JAMAIS: "Cette semaine, on a X, Y et Z. Commençons par X."
JAMAIS: "Premier point... Deuxième point..."
JAMAIS: énumérer les infos sans fil conducteur

### ✅ OBLIGATOIRE - Le style "accroche narrative"
TOUJOURS: Commencer par un FAIT ÉTONNANT ou une QUESTION PROVOCANTE
TOUJOURS: Créer une TENSION (problème/solution, avant/après, pour/contre)
TOUJOURS: Un seul ANGLE par sujet, mais traité en profondeur

### Format dialogue STRICT
Chaque réplique commence par [VOICE_A] ou [VOICE_B] SEUL sur sa ligne.
Alternance OBLIGATOIRE. Jamais deux [VOICE_A] ou [VOICE_B] consécutifs.

### Style oral naturel
- Phrases courtes (max 20 mots)
- Contractions: "C'est" pas "Cela est"
- Interjections: "Bon,", "Alors,", "Écoute,"
- Questions rhétoriques pour relancer

### Phonétique TTS
Écris phonétiquement: "LLM" → "elle-elle-aime", "GPU" → "jé-pé-u", "AI" → "A-I"
"""

PROMPT_SEGMENT_CAPTIVANT = """SUJET: {title}
SOURCE: {source_name}
CONTENU BRUT:
{content}

---

Ta mission: Transformer ça en 2-3 minutes de CONVERSATION CAPTIVANTE.

ÉTAPE 1 - Trouve L'ANGLE
Parmi tout ce contenu, quel est LE détail le plus surprenant/important/controversé?
Ne fais PAS un résumé. Choisis UN angle et creuse-le.

ÉTAPE 2 - Crée la TENSION  
- Quel est le PROBLÈME ou l'ENJEU caché?
- Qui GAGNE et qui PERD?
- Qu'est-ce qui pourrait MAL TOURNER?

ÉTAPE 3 - Écris le DIALOGUE ({target_words} mots)

FORMAT STRICT:
[VOICE_A]
Breeze lance avec un fait percutant ou une question.

[VOICE_B]
Vale réagit, challenge, demande "concrètement".

[VOICE_A]
Breeze développe, donne un exemple parlant.

[VOICE_B]
Vale pousse plus loin ou nuance.

[VOICE_A]
Breeze conclut avec une perspective.

RAPPELS:
- Cite "{source_name}" naturellement UNE fois
- Minimum 5 répliques alternées
- ZÉRO superlatif, ZÉRO "révolutionnaire"
- Pas de "merci d'avoir écouté"

GÉNÈRE UNIQUEMENT LE SCRIPT:"""

PROMPT_EPHEMERIDE_CAPTIVANT = """Date: {formatted_date}

Fait historique (vérifié): En {fact_year}, {fact_text}

---

Crée un DIALOGUE de 60 mots entre Breeze et Vale.

L'objectif: Faire le PONT entre ce fait historique et l'actualité d'aujourd'hui.
Trouve une connexion SURPRENANTE avec la tech, l'IA, ou un sujet actuel.

FORMAT:
[VOICE_A]
Breeze mentionne la date et le fait historique avec un twist.

[VOICE_B]  
Vale fait le lien avec aujourd'hui ("Tiens, ça me rappelle...")

[VOICE_A]
Breeze rebondit et lance vers les actus.

Style: Complice, cultivé, jamais pédant.

GÉNÈRE UNIQUEMENT LE SCRIPT:"""

PROMPT_INTRO_DYNAMIQUE = """Génère une phrase d'intro personnalisée et dynamique pour {name}.

EXEMPLES DE TON:
- "{name}, installez-vous, on a du lourd aujourd'hui."
- "Salut {name}! Prêt pour votre dose d'actus?"  
- "{name}, c'est parti pour votre Keernel du jour."

CONTRAINTES:
- Maximum 12 mots
- Ton chaleureux mais pas mielleux
- Pas de "Bonjour" classique, sois créatif
- Une seule phrase

Génère UNIQUEMENT la phrase:"""


# ============================================
# AUDIO GENERATION (OpenAI TTS only)
# ============================================

def generate_tts_audio(text: str, voice: str, output_path: str, speed: float = 1.0) -> str | None:
    """Generate audio using OpenAI TTS."""
    if not openai_client:
        log.error("OpenAI client not initialized")
        return None
    
    try:
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
            speed=speed  # 1.0 = normal, 1.1 = légèrement plus rapide
        )
        response.stream_to_file(output_path)
        return output_path
    except Exception as e:
        log.error("TTS generation failed", error=str(e))
        return None


def get_audio_duration(file_path: str) -> int:
    """Get duration of audio file in seconds."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(file_path)
        return len(audio) // 1000
    except:
        return 0


# ============================================
# SCRIPT PARSING
# ============================================

def normalize_voice_tags(script: str) -> str:
    """Normalize various voice tag formats."""
    patterns = [
        (r'\[VOICE[\s_-]*A\]', '[VOICE_A]'),
        (r'\[VOICE[\s_-]*B\]', '[VOICE_B]'),
        (r'\[voice[\s_-]*a\]', '[VOICE_A]'),
        (r'\[voice[\s_-]*b\]', '[VOICE_B]'),
        (r'VOICE_A\s*:', '[VOICE_A]\n'),
        (r'VOICE_B\s*:', '[VOICE_B]\n'),
        (r'\*\*\[VOICE_A\]\*\*', '[VOICE_A]'),
        (r'\*\*\[VOICE_B\]\*\*', '[VOICE_B]'),
        (r'Breeze\s*:', '[VOICE_A]\n'),
        (r'Vale\s*:', '[VOICE_B]\n'),
        (r'\[Breeze\]', '[VOICE_A]'),
        (r'\[Vale\]', '[VOICE_B]'),
    ]
    
    result = script
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def parse_dialogue_script(script: str) -> list[dict]:
    """Parse script into voice segments."""
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
    
    voice_a = sum(1 for s in segments if s["voice"] == "A")
    voice_b = sum(1 for s in segments if s["voice"] == "B")
    log.info("Parsed dialogue", total=len(segments), voice_a=voice_a, voice_b=voice_b)
    
    return segments


def generate_dialogue_audio(script: str, output_path: str) -> str | None:
    """Generate audio with two alternating voices."""
    segments = parse_dialogue_script(script)
    
    if not segments:
        log.error("No segments parsed")
        return None
    
    audio_files = []
    
    for i, segment in enumerate(segments):
        voice = VOICE_BREEZE if segment["voice"] == "A" else VOICE_VALE
        text = segment["text"]
        
        log.info(f"Generating segment {i+1}/{len(segments)}", voice=voice)
        
        segment_path = output_path.replace(".mp3", f"_seg{i:03d}.mp3")
        
        # Vitesse légèrement plus rapide pour dynamisme (1.05)
        if generate_tts_audio(text, voice, segment_path, speed=1.05):
            audio_files.append(segment_path)
        else:
            log.warning(f"Failed segment {i}")
    
    if not audio_files:
        return None
    
    # Combine with pauses
    try:
        from pydub import AudioSegment
        pause = AudioSegment.silent(duration=250)  # 250ms entre les répliques
        combined = AudioSegment.empty()
        
        for i, path in enumerate(audio_files):
            audio = AudioSegment.from_mp3(path)
            combined += audio
            if i < len(audio_files) - 1:
                combined += pause
        
        combined.export(output_path, format="mp3", bitrate="192k")
        
        # Cleanup
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
# UTILITY FUNCTIONS
# ============================================

def normalize_first_name(name: str) -> str:
    if not name:
        return "ami"
    name = name.lower().strip()
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', name) or "ami"


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace('www.', '')
    except:
        return "source"


def upload_to_storage(local_path: str, remote_path: str) -> str | None:
    try:
        with open(local_path, 'rb') as f:
            audio_data = f.read()
        supabase.storage.from_("audio").upload(
            remote_path, audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        return supabase.storage.from_("audio").get_public_url(remote_path)
    except Exception as e:
        log.warning("Upload failed", error=str(e))
        return None


# ============================================
# INTRO (OpenAI TTS - Breeze voice)
# ============================================

def get_or_create_intro(first_name: str) -> dict | None:
    """Generate personalized intro with Breeze voice (OpenAI)."""
    normalized = normalize_first_name(first_name)
    display_name = first_name.strip().title() if first_name else "Ami"
    
    # Force regeneration - no cache for now to ensure OpenAI voice
    log.info("Generating intro with OpenAI", first_name=normalized)
    
    # Generate dynamic intro text
    if groq_client:
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "user", "content": PROMPT_INTRO_DYNAMIQUE.format(name=display_name)}
                ],
                temperature=0.8,
                max_tokens=50
            )
            intro_text = response.choices[0].message.content.strip().strip('"')
        except:
            intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    else:
        intro_text = f"{display_name}, c'est parti pour votre Keernel!"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"intro_{normalized}_{timestamp}.mp3")
    
    # Use Breeze voice (nova) with OpenAI
    audio_path = generate_tts_audio(intro_text, VOICE_BREEZE, temp_path, speed=1.0)
    
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    return {
        "local_path": audio_path,
        "duration": duration,
        "text": intro_text
    }


# ============================================
# EPHEMERIDE (Dialogue format)
# ============================================

def get_or_create_ephemeride(target_date: date = None) -> dict | None:
    """Generate ephemeride as dialogue."""
    if target_date is None:
        target_date = date.today()
    
    date_str = target_date.isoformat()
    
    if not groq_client:
        return None
    
    # Format date
    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    except:
        pass
    formatted_date = target_date.strftime("%A %d %B").capitalize()
    
    # Get historical fact
    try:
        from sourcing import get_best_ephemeride_fact
        fact = get_best_ephemeride_fact(target_date.month, target_date.day)
    except:
        fact = None
    
    if fact:
        prompt = PROMPT_EPHEMERIDE_CAPTIVANT.format(
            formatted_date=formatted_date,
            fact_year=fact["year"],
            fact_text=fact["text"]
        )
    else:
        prompt = f"""Date: {formatted_date}

Crée un dialogue court (50 mots) entre Breeze et Vale pour lancer le podcast.

[VOICE_A]
Breeze mentionne la date avec énergie.

[VOICE_B]
Vale enchaîne vers les actus du jour.

GÉNÈRE LE SCRIPT:"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_DIALOGUE},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        script = response.choices[0].message.content.strip()
    except Exception as e:
        log.error("Ephemeride generation failed", error=str(e))
        return None
    
    # Validate dialogue
    if VOICE_TAG_A not in script or VOICE_TAG_B not in script:
        log.warning("Ephemeride missing voice tags")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"ephemeride_{timestamp}.mp3")
    
    audio_path = generate_dialogue_audio(script, temp_path)
    if not audio_path:
        return None
    
    return {
        "local_path": audio_path,
        "duration": get_audio_duration(audio_path),
        "script": script
    }


# ============================================
# SEGMENT GENERATION (Captivating dialogue)
# ============================================

def generate_captivating_segment(
    url: str,
    title: str,
    content: str,
    target_words: int
) -> dict | None:
    """Generate a captivating dialogue segment."""
    
    if not groq_client:
        return None
    
    source_name = get_domain(url)
    
    prompt = PROMPT_SEGMENT_CAPTIVANT.format(
        title=title,
        source_name=source_name,
        content=content[:6000],
        target_words=target_words
    )
    
    max_attempts = 2
    
    for attempt in range(max_attempts):
        try:
            extra = "" if attempt == 0 else "\n\nATTENTION: Assure-toi d'alterner [VOICE_A] et [VOICE_B]!"
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_DIALOGUE},
                    {"role": "user", "content": prompt + extra}
                ],
                temperature=0.7,
                max_tokens=target_words * 3
            )
            
            script = response.choices[0].message.content.strip()
            script = normalize_voice_tags(script)
            
            # Validate
            voice_a = script.count(VOICE_TAG_A)
            voice_b = script.count(VOICE_TAG_B)
            
            log.info("Script generated", voice_a=voice_a, voice_b=voice_b, attempt=attempt+1)
            
            if voice_a >= 2 and voice_b >= 2:
                return {"script": script, "title": title}
            
        except Exception as e:
            log.error("Generation failed", error=str(e))
    
    return None


def get_or_create_segment(url: str, target_words: int = 250) -> dict | None:
    """Create a captivating dialogue segment from URL."""
    
    log.info("Processing URL", url=url[:60])
    
    # Extract content
    extraction = extract_content(url)
    if not extraction:
        log.warning("Extraction failed", url=url[:60])
        return None
    
    source_type, title, content = extraction
    
    # Generate captivating script
    result = generate_captivating_segment(url, title, content, target_words)
    if not result:
        return None
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title[:20])
    temp_path = os.path.join(tempfile.gettempdir(), f"seg_{safe_title}_{timestamp}.mp3")
    
    audio_path = generate_dialogue_audio(result["script"], temp_path)
    if not audio_path:
        return None
    
    return {
        "local_path": audio_path,
        "duration": get_audio_duration(audio_path),
        "title": title,
        "script": result["script"]
    }


# ============================================
# MAIN ASSEMBLY
# ============================================

def stitch_audio_segments(segment_paths: list[str], output_path: str) -> bool:
    """Concatenate audio files."""
    if not segment_paths:
        return False
    
    try:
        from pydub import AudioSegment
        combined = AudioSegment.empty()
        
        for path in segment_paths:
            audio = AudioSegment.from_mp3(path)
            combined += audio
        
        combined.export(output_path, format="mp3", bitrate="192k")
        return True
    except Exception as e:
        log.error("Stitch failed", error=str(e))
        return False


def assemble_podcast(
    user_id: str,
    first_name: str,
    urls: list[str],
    target_duration: int = 15
) -> dict | None:
    """Assemble the full podcast."""
    
    log.info("Assembling podcast", user=user_id[:8], urls=len(urls), target_min=target_duration)
    
    segments = []
    sources_data = []
    temp_files = []
    total_duration = 0
    target_seconds = target_duration * 60
    
    try:
        # 1. INTRO (Breeze voice - OpenAI)
        intro = get_or_create_intro(first_name)
        if intro:
            segments.append(intro["local_path"])
            temp_files.append(intro["local_path"])
            total_duration += intro["duration"]
            log.info("Intro added", duration=intro["duration"])
        
        # 2. EPHEMERIDE (Dialogue)
        ephemeride = get_or_create_ephemeride()
        if ephemeride:
            segments.append(ephemeride["local_path"])
            temp_files.append(ephemeride["local_path"])
            total_duration += ephemeride["duration"]
            log.info("Ephemeride added", duration=ephemeride["duration"])
        
        # 3. CONTENT SEGMENTS
        remaining = target_seconds - total_duration
        words_per_segment = max(200, min(400, remaining // max(1, len(urls)) * WORDS_PER_MINUTE // 60))
        
        for url in urls:
            if total_duration >= target_seconds * 0.95:
                break
            
            segment = get_or_create_segment(url, words_per_segment)
            if segment:
                segments.append(segment["local_path"])
                temp_files.append(segment["local_path"])
                total_duration += segment["duration"]
                sources_data.append({
                    "title": segment["title"],
                    "url": url,
                    "domain": get_domain(url)
                })
                log.info("Segment added", title=segment["title"][:40], duration=segment["duration"])
        
        if len(segments) < 2:
            log.error("Not enough segments")
            return None
        
        # 4. STITCH
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"podcast_{user_id[:8]}_{timestamp}.mp3")
        
        if not stitch_audio_segments(segments, output_path):
            return None
        
        final_duration = get_audio_duration(output_path)
        
        # 5. UPLOAD
        remote_path = f"{user_id}/keernel_{timestamp}.mp3"
        audio_url = upload_to_storage(output_path, remote_path)
        
        # Cleanup
        os.remove(output_path)
        for f in temp_files:
            try:
                os.remove(f)
            except:
                pass
        
        log.info("Podcast assembled", duration=final_duration, segments=len(sources_data))
        
        return {
            "audio_url": audio_url,
            "duration": final_duration,
            "sources_data": sources_data
        }
        
    except Exception as e:
        log.error("Assembly failed", error=str(e))
        return None


# ============================================
# ENTRY POINT
# ============================================

def generate_podcast_for_user(user_id: str) -> dict | None:
    """Main entry point."""
    log.info("Starting podcast generation", user=user_id[:8])
    
    # Get user info
    try:
        user = supabase.table("users").select("first_name, target_duration").eq("id", user_id).single().execute()
        first_name = user.data.get("first_name") or "Ami"
        target_duration = user.data.get("target_duration") or 15
    except:
        first_name = "Ami"
        target_duration = 15
    
    # Get content queue
    try:
        queue = supabase.table("content_queue").select("url").eq("user_id", user_id).eq("status", "pending").execute()
        urls = [item["url"] for item in queue.data] if queue.data else []
    except:
        urls = []
    
    if not urls:
        log.warning("No content in queue")
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
        
        return episode.data[0] if episode.data else None
        
    except Exception as e:
        log.error("Episode creation failed", error=str(e))
        return None
