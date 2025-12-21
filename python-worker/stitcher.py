"""
Keernel Stitcher - Audio Assembly Engine v2

RÈGLES DE FER POUR LES SCRIPTS RADIO:
1. ZÉRO MÉTA-DISCOURS - Jamais "Voici le script...", "Passons à..."
2. L'OREILLE AVANT TOUT - Phrases courtes (Sujet-Verbe-Complément)
3. ACCROCHES JOURNALISTIQUES - Entrer directement dans l'info
4. CITATIONS NATURELLES - "D'après TechCrunch...", "Selon le Figaro..."
5. TOUJOURS EN FRANÇAIS - Quelle que soit la langue source
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
from generator import generate_audio, groq_client, get_audio_duration
from extractor import extract_content

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONSTANTS
# ============================================

WORDS_PER_MINUTE = 150
INTRO_DURATION_SEC = 5
EPHEMERIDE_DURATION_SEC = 45

# Vertical definitions with keywords
VERTICALS = {
    "ai_tech": {
        "name": "IA & Tech",
        "keywords_fr": ["intelligence artificielle", "LLM", "robotique", "startup tech", "OpenAI"],
        "keywords_en": ["artificial intelligence", "LLM", "robotics", "tech startup", "OpenAI", "GPU"]
    },
    "politics": {
        "name": "Politique & Monde",
        "keywords_fr": ["politique France", "élections", "diplomatie", "géopolitique"],
        "keywords_en": ["US politics", "elections", "diplomacy", "geopolitics"]
    },
    "finance": {
        "name": "Finance & Marchés",
        "keywords_fr": ["bourse Paris", "CAC 40", "crypto", "économie"],
        "keywords_en": ["stock market", "Wall Street", "crypto", "Fed"]
    },
    "science": {
        "name": "Science & Santé",
        "keywords_fr": ["espace NASA", "biotech", "énergie climat"],
        "keywords_en": ["space NASA SpaceX", "biotech", "energy climate"]
    },
    "culture": {
        "name": "Culture & Divertissement",
        "keywords_fr": ["cinéma séries", "jeux vidéo gaming", "streaming"],
        "keywords_en": ["movies Netflix", "gaming", "streaming YouTube"]
    }
}

# ============================================
# SYSTEM PROMPTS - RÈGLES DE FER
# ============================================

SYSTEM_PROMPT_RADIO = """Tu es un journaliste radio français de premier plan. Tu écris des scripts audio PERCUTANTS.

## RÈGLES DE FER ABSOLUES

### 1. ZÉRO MÉTA-DISCOURS
INTERDIT de commencer par :
- "Voici le script..."
- "Passons à..."  
- "Le sujet suivant est..."
- "Dans cette rubrique..."
- "Nous allons parler de..."

### 2. ACCROCHES DIRECTES
Commence TOUJOURS par l'information elle-même :
✅ "C'est un record qui vient de tomber à Wall Street..."
✅ "Dans les couloirs d'OpenAI, la tension monte..."
✅ "Surprise à l'Élysée ce matin..."
✅ "Apple vient de frapper un grand coup..."

### 3. STYLE ORAL
- Phrases COURTES (Sujet-Verbe-Complément)
- Rythme SOUTENU
- PAS de listes à puces
- PAS de parenthèses
- JAMAIS de markdown

### 4. CITATIONS NATURELLES
Cite la source naturellement :
✅ "D'après TechCrunch..."
✅ "Comme le révèle le Financial Times..."
✅ "Selon les informations du Figaro..."

### 5. TOUJOURS EN FRANÇAIS
Quelle que soit la langue de la source (anglais, allemand, espagnol...), 
le script doit être rédigé en FRANÇAIS fluide et naturel.

### 6. STRUCTURE
- Accroche percutante (1-2 phrases)
- Développement des faits (corps)
- Chute ou perspective (1 phrase)

Tu génères UNIQUEMENT le script, prêt à être lu à voix haute."""


SYSTEM_PROMPT_EPHEMERIDE = """Tu es un animateur radio français cultivé et dynamique.

Tu génères une éphéméride qui :
1. Commence DIRECTEMENT par la date joliment formulée
2. Mentionne le saint du jour
3. Trouve UN fait historique MARQUANT pour cette date
4. Fait un LIEN (même ténu) avec l'actualité tech ou une tendance du moment
5. Termine par une transition naturelle vers les actualités

STYLE :
- Phrases courtes et percutantes
- Présent de narration
- Ton complice et enthousiaste
- Environ 60-80 mots

INTERDIT :
- "Aujourd'hui nous célébrons..."
- "Pour cette éphéméride..."
- Toute forme de méta-discours

Génère UNIQUEMENT le texte, prêt à être lu."""


# ============================================
# UTILITY FUNCTIONS
# ============================================

def normalize_first_name(name: str) -> str:
    """Normalize first name for cache key."""
    if not name:
        return "ami"
    name = name.lower().strip()
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    name = re.sub(r'[^a-z0-9]', '', name)
    return name or "ami"


def extract_source_identity(url: str) -> tuple[str, str]:
    """
    Extract source identity from URL.
    Returns (source_identity, source_type)
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        
        # YouTube
        if 'youtube.com' in domain or 'youtu.be' in domain:
            # Try to extract channel handle from URL
            if '@' in url:
                match = re.search(r'@[\w-]+', url)
                if match:
                    return match.group(), 'youtube'
            # Extract video ID for now, we'll get channel later
            return domain, 'youtube'
        
        # Twitter/X
        if 'twitter.com' in domain or 'x.com' in domain:
            match = re.search(r'(?:twitter\.com|x\.com)/(\w+)', url)
            if match:
                return f"@{match.group(1)}", 'twitter'
        
        # Podcast platforms
        if any(p in domain for p in ['spotify.com', 'podcasts.apple.com', 'podcasts.google.com']):
            return domain, 'podcast'
        
        # Default: use domain
        return domain, 'web'
        
    except:
        return "unknown", 'web'


def get_domain(url: str) -> str:
    """Extract domain name from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        return domain
    except:
        return "source"


def estimate_words_for_duration(target_seconds: int) -> int:
    """Estimate word count needed for target duration."""
    minutes = target_seconds / 60
    return int(minutes * WORDS_PER_MINUTE)


def upload_to_storage(local_path: str, remote_path: str) -> str | None:
    """Try to upload file to Supabase Storage."""
    try:
        with open(local_path, 'rb') as f:
            audio_data = f.read()
        
        supabase.storage.from_("audio").upload(
            remote_path,
            audio_data,
            {"content-type": "audio/mpeg", "upsert": "true"}
        )
        
        return supabase.storage.from_("audio").get_public_url(remote_path)
    except Exception as e:
        log.warning("Storage upload failed", error=str(e))
        return None


def update_source_score(user_id: str, url: str):
    """Update reliability score for a source."""
    try:
        source_identity, source_type = extract_source_identity(url)
        
        # Call the Supabase function
        supabase.rpc('increment_source_score', {
            'p_user_id': user_id,
            'p_source_identity': source_identity,
            'p_source_type': source_type,
            'p_display_name': get_domain(url)
        }).execute()
        
        log.info("Source score updated", source=source_identity, type=source_type)
    except Exception as e:
        log.warning("Failed to update source score", error=str(e))


# ============================================
# SEGMENT A: PERSONALIZED INTRO
# ============================================

def get_or_create_intro(first_name: str) -> dict | None:
    """Get cached intro or create new one."""
    normalized = normalize_first_name(first_name)
    
    # Check DB cache
    try:
        result = supabase.table("cached_intros") \
            .select("*") \
            .eq("first_name_normalized", normalized) \
            .single() \
            .execute()
        
        if result.data and result.data.get("audio_url"):
            log.info("Using cached intro", first_name=normalized)
            import httpx
            temp_path = os.path.join(tempfile.gettempdir(), f"intro_{normalized}.mp3")
            try:
                response = httpx.get(result.data["audio_url"], timeout=30, follow_redirects=True)
                response.raise_for_status()
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                return {
                    "local_path": temp_path,
                    "audio_url": result.data["audio_url"],
                    "duration": result.data["audio_duration"]
                }
            except:
                pass
    except:
        pass
    
    # Generate new intro
    log.info("Generating new intro", first_name=normalized)
    
    display_name = first_name.strip().title() if first_name else "Ami"
    intro_script = f"Bonjour {display_name}, bienvenue dans votre Keernel du jour."
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"intro_{normalized}_{timestamp}.mp3")
    
    audio_path = generate_audio(intro_script, voice="alloy", output_path=temp_path)
    
    if not audio_path:
        log.error("Failed to generate intro audio")
        return None
    
    duration = get_audio_duration(audio_path)
    
    # Upload and cache
    remote_path = f"intros/welcome_{normalized}.mp3"
    audio_url = upload_to_storage(audio_path, remote_path)
    
    if audio_url:
        try:
            supabase.table("cached_intros").upsert({
                "first_name_normalized": normalized,
                "audio_url": audio_url,
                "audio_duration": duration
            }).execute()
        except:
            pass
    
    return {
        "local_path": audio_path,
        "audio_url": audio_url,
        "duration": duration
    }


# ============================================
# SEGMENT B: ÉCHO DU TEMPS (Enhanced Ephemeride)
# ============================================

def get_or_create_ephemeride(target_date: date = None) -> dict | None:
    """
    Generate ephemeride with VERIFIED historical fact from Wikimedia API.
    No more LLM hallucinations on historical dates.
    """
    if target_date is None:
        target_date = date.today()
    
    date_str = target_date.isoformat()
    
    # Check cache
    try:
        result = supabase.table("daily_ephemeride") \
            .select("*") \
            .eq("date", date_str) \
            .single() \
            .execute()
        
        if result.data and result.data.get("audio_url"):
            log.info("Using cached ephemeride", date=date_str)
            import httpx
            temp_path = os.path.join(tempfile.gettempdir(), f"ephemeride_{date_str}.mp3")
            try:
                response = httpx.get(result.data["audio_url"], timeout=30, follow_redirects=True)
                response.raise_for_status()
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                return {
                    "local_path": temp_path,
                    "audio_url": result.data["audio_url"],
                    "duration": result.data["audio_duration"],
                    "script": result.data["script"]
                }
            except:
                pass
    except:
        pass
    
    log.info("Generating ephemeride", date=date_str)
    
    if not groq_client:
        return None
    
    # Format date in French
    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    except:
        pass
    
    formatted_date = target_date.strftime("%A %d %B %Y").capitalize()
    
    # ============================================
    # FETCH VERIFIED FACT FROM WIKIMEDIA API
    # ============================================
    from sourcing import get_best_ephemeride_fact
    
    wikimedia_fact = get_best_ephemeride_fact(
        month=target_date.month, 
        day=target_date.day
    )
    
    if wikimedia_fact:
        fact_year = wikimedia_fact["year"]
        fact_text = wikimedia_fact["text"]
        is_tech = wikimedia_fact.get("is_tech_relevant", False)
        
        log.info("Using Wikimedia fact", year=fact_year, tech_relevant=is_tech)
        
        prompt = f"""Génère l'Écho du Temps pour le {formatted_date}.

FAIT HISTORIQUE VÉRIFIÉ (SOURCE: WIKIMEDIA) :
En {fact_year} : {fact_text}

Ta mission :
1. Commence par "Nous sommes le {formatted_date}..."
2. Mentionne un saint du jour plausible
3. Reformule le fait historique de manière percutante
4. {"Souligne le lien avec la tech actuelle (IA, espace, énergie...)" if is_tech else "Trouve un angle moderne ou une résonance avec l'actualité"}
5. Termine par une transition vers les actualités

IMPORTANT : Utilise UNIQUEMENT le fait fourni ci-dessus, ne l'invente pas.
Environ 70-90 mots. Ton dynamique et cultivé."""

    else:
        # Fallback: demander au LLM mais avec avertissement
        log.warning("No Wikimedia fact available, using LLM generation")
        prompt = f"""Génère l'Écho du Temps pour le {formatted_date}.

Note : Pas de fait historique disponible, génère une éphéméride générique.
Mentionne la date et un saint du jour plausible.
Fais une transition vers les actualités.

Environ 60 mots. Ton dynamique."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_EPHEMERIDE},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,  # Lower temp for more factual
            max_tokens=250
        )
        
        script = response.choices[0].message.content.strip()
        log.info("Ephemeride generated", words=len(script.split()))
        
    except Exception as e:
        log.error("Failed to generate ephemeride", error=str(e))
        return None
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"ephemeride_{date_str}_{timestamp}.mp3")
    
    audio_path = generate_audio(script, voice="alloy", output_path=temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    # Upload and cache
    remote_path = f"ephemerides/echo_{date_str}.mp3"
    audio_url = upload_to_storage(audio_path, remote_path)
    
    if audio_url:
        try:
            supabase.table("daily_ephemeride").upsert({
                "date": date_str,
                "script": script,
                "audio_url": audio_url,
                "audio_duration": duration
            }).execute()
        except:
            pass
    
    return {
        "local_path": audio_path,
        "audio_url": audio_url,
        "duration": duration,
        "script": script
    }


# ============================================
# SEGMENT GENERATION - DEEP DIVE & FLASH
# ============================================

def generate_segment_script(
    url: str,
    title: str,
    content: str,
    segment_type: str,
    target_words: int,
    vertical: str = None
) -> str | None:
    """Generate script with iron rules applied."""
    
    source_name = get_domain(url)
    
    if segment_type == "deep_dive":
        user_prompt = f"""SOURCE : {source_name}
TITRE : {title}
CONTENU : {content[:5000]}

Écris un script DEEP DIVE d'environ {target_words} mots.

STRUCTURE :
1. Accroche percutante (entre direct dans le sujet)
2. Les faits clés développés
3. L'analyse ou la perspective
4. Chute mémorable

Cite la source naturellement : "D'après {source_name}..."

GÉNÈRE UNIQUEMENT LE SCRIPT."""

    else:  # flash_news
        user_prompt = f"""SOURCE : {source_name}
TITRE : {title}
CONTENU : {content[:3000]}

Écris un FLASH INFO d'environ {target_words} mots.

STRUCTURE :
1. Accroche directe (l'info principale)
2. Les faits essentiels
3. Une phrase de conclusion

Cite la source : "Selon {source_name}..."

GÉNÈRE UNIQUEMENT LE SCRIPT."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_RADIO},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=target_words * 2
        )
        
        script = response.choices[0].message.content.strip()
        
        # Verify no meta-discourse slipped through
        forbidden_starts = [
            "voici", "passons", "dans cette", "nous allons",
            "le sujet", "cette rubrique", "pour ce"
        ]
        first_words = script.lower()[:50]
        for forbidden in forbidden_starts:
            if first_words.startswith(forbidden):
                log.warning("Meta-discourse detected, regenerating...")
                # Try once more
                return generate_segment_script(url, title, content, segment_type, target_words, vertical)
        
        return script
        
    except Exception as e:
        log.error("Failed to generate script", error=str(e))
        return None


def get_or_create_segment(url: str, segment_type: str, target_words: int = 200, vertical: str = None) -> dict | None:
    """Get cached segment or create new one with iron rules."""
    today = date.today().isoformat()
    
    # Check cache
    try:
        result = supabase.table("processed_segments") \
            .select("*") \
            .eq("url", url) \
            .eq("date", today) \
            .single() \
            .execute()
        
        if result.data and result.data.get("audio_url"):
            log.info("Using cached segment", url=url[:50])
            import httpx
            temp_path = os.path.join(tempfile.gettempdir(), f"segment_{result.data['id']}.mp3")
            try:
                response = httpx.get(result.data["audio_url"], timeout=30, follow_redirects=True)
                response.raise_for_status()
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                return {
                    "local_path": temp_path,
                    "audio_url": result.data["audio_url"],
                    "duration": result.data["audio_duration"],
                    "title": result.data["title"],
                    "script": result.data["script"]
                }
            except:
                pass
    except:
        pass
    
    # Extract content
    log.info("Processing content", url=url[:60], type=segment_type)
    
    extraction = extract_content(url)
    if not extraction:
        log.warning("Failed to extract", url=url[:60])
        return None
    
    source_type, title, content = extraction
    
    # Generate script with iron rules
    script = generate_segment_script(url, title, content, segment_type, target_words, vertical)
    if not script:
        return None
    
    log.info("Script generated", words=len(script.split()), type=segment_type)
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title[:30])
    temp_path = os.path.join(tempfile.gettempdir(), f"segment_{safe_title}_{timestamp}.mp3")
    
    audio_path = generate_audio(script, voice="alloy", output_path=temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    # Upload
    remote_path = f"segments/{today}/{segment_type}_{timestamp}.mp3"
    audio_url = upload_to_storage(audio_path, remote_path)
    
    # Cache in DB
    source_identity, _ = extract_source_identity(url)
    try:
        supabase.table("processed_segments").upsert({
            "url": url,
            "date": today,
            "segment_type": segment_type,
            "title": title,
            "script": script,
            "audio_url": audio_url,
            "audio_duration": duration,
            "word_count": len(script.split()),
            "source_name": get_domain(url),
            "source_identity": source_identity,
            "language": "fr"
        }, on_conflict="url,date").execute()
    except Exception as e:
        log.warning("Cache failed", error=str(e))
    
    return {
        "local_path": audio_path,
        "audio_url": audio_url,
        "duration": duration,
        "title": title,
        "script": script
    }


# ============================================
# FILLER SEGMENT - Analysis when content is short
# ============================================

def generate_filler_analysis(vertical: str, target_words: int) -> dict | None:
    """Generate an analysis segment when content is insufficient."""
    
    vertical_info = VERTICALS.get(vertical, VERTICALS["ai_tech"])
    
    prompt = f"""Génère une analyse de fond sur la verticale "{vertical_info['name']}".

Choisis UN sujet d'actualité récent dans ce domaine et développe :
1. Le contexte
2. Les enjeux
3. Les perspectives

Environ {target_words} mots. Style radio, dynamique.

Commence DIRECTEMENT par l'analyse, sans introduction méta."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_RADIO},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=target_words * 2
        )
        
        script = response.choices[0].message.content.strip()
        log.info("Filler analysis generated", vertical=vertical, words=len(script.split()))
        
    except Exception as e:
        log.error("Failed to generate filler", error=str(e))
        return None
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(tempfile.gettempdir(), f"filler_{vertical}_{timestamp}.mp3")
    
    audio_path = generate_audio(script, voice="alloy", output_path=temp_path)
    if not audio_path:
        return None
    
    duration = get_audio_duration(audio_path)
    
    return {
        "local_path": audio_path,
        "duration": duration,
        "title": f"Analyse {vertical_info['name']}",
        "script": script
    }


# ============================================
# FFMPEG STITCHER
# ============================================

def stitch_audio_segments(segment_paths: list[str], output_path: str) -> bool:
    """Concatenate MP3 files using FFmpeg."""
    if not segment_paths:
        return False
    
    concat_file = os.path.join(tempfile.gettempdir(), f"concat_{datetime.now().strftime('%H%M%S')}.txt")
    
    try:
        with open(concat_file, 'w') as f:
            for path in segment_paths:
                escaped = path.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            log.error("FFmpeg failed", stderr=result.stderr[:500])
            return False
        
        return True
        
    except Exception as e:
        log.error("Stitch failed", error=str(e))
        return False
    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


# ============================================
# MAIN ASSEMBLY
# ============================================

def assemble_podcast(
    user_id: str,
    first_name: str,
    manual_urls: list[str],
    auto_urls: list[str],
    target_duration: int = 20,
    selected_verticals: dict = None
) -> dict | None:
    """Assemble podcast with priority: Intro > Ephemeride > Deep Dives > Flash News."""
    
    log.info("Assembling Keernel", 
             user_id=user_id[:8], 
             target_min=target_duration,
             manual=len(manual_urls),
             auto=len(auto_urls))
    
    target_seconds = target_duration * 60
    segments = []
    sources_data = []
    total_duration = 0
    temp_files = []
    
    try:
        # =====================
        # SEGMENT A: INTRO
        # =====================
        intro = get_or_create_intro(first_name)
        if intro and intro.get("local_path"):
            segments.append({"type": "intro", "path": intro["local_path"], "duration": intro["duration"]})
            temp_files.append(intro["local_path"])
            total_duration += intro["duration"]
        
        # =====================
        # SEGMENT B: ÉCHO DU TEMPS
        # =====================
        ephemeride = get_or_create_ephemeride()
        if ephemeride and ephemeride.get("local_path"):
            segments.append({"type": "ephemeride", "path": ephemeride["local_path"], "duration": ephemeride["duration"]})
            temp_files.append(ephemeride["local_path"])
            total_duration += ephemeride["duration"]
        
        remaining_seconds = target_seconds - total_duration
        
        # =====================
        # PRIORITY 1: DEEP DIVES (60% of remaining)
        # =====================
        deep_dive_budget = int(remaining_seconds * 0.6)
        deep_dive_used = 0
        
        for url in manual_urls:
            if deep_dive_used >= deep_dive_budget:
                break
            
            remaining = deep_dive_budget - deep_dive_used
            target_words = estimate_words_for_duration(min(remaining, 180))
            target_words = max(250, min(target_words, 500))
            
            segment = get_or_create_segment(url, "deep_dive", target_words)
            if segment and segment.get("local_path"):
                segments.append({"type": "deep_dive", "path": segment["local_path"], "duration": segment["duration"]})
                temp_files.append(segment["local_path"])
                deep_dive_used += segment["duration"]
                total_duration += segment["duration"]
                
                sources_data.append({
                    "title": segment["title"],
                    "url": url,
                    "domain": get_domain(url),
                    "type": "deep_dive"
                })
                
                # Update source score
                update_source_score(user_id, url)
        
        # =====================
        # PRIORITY 2: FLASH NEWS FROM VERTICALS
        # =====================
        flash_budget = target_seconds - total_duration
        flash_used = 0
        
        for url in auto_urls:
            if flash_used >= flash_budget or total_duration >= target_seconds:
                break
            
            remaining = flash_budget - flash_used
            target_words = estimate_words_for_duration(min(remaining, 90))
            target_words = max(100, min(target_words, 180))
            
            segment = get_or_create_segment(url, "flash_news", target_words)
            if segment and segment.get("local_path"):
                segments.append({"type": "flash_news", "path": segment["local_path"], "duration": segment["duration"]})
                temp_files.append(segment["local_path"])
                flash_used += segment["duration"]
                total_duration += segment["duration"]
                
                sources_data.append({
                    "title": segment["title"],
                    "url": url,
                    "domain": get_domain(url),
                    "type": "flash_news"
                })
        
        # =====================
        # FILLER IF NEEDED (-15% threshold)
        # =====================
        min_threshold = target_seconds * 0.85
        if total_duration < min_threshold and selected_verticals:
            # Find an enabled vertical
            for v_id, enabled in selected_verticals.items():
                if enabled and v_id in VERTICALS:
                    remaining_words = estimate_words_for_duration(int(min_threshold - total_duration))
                    filler = generate_filler_analysis(v_id, remaining_words)
                    if filler and filler.get("local_path"):
                        segments.append({"type": "analysis", "path": filler["local_path"], "duration": filler["duration"]})
                        temp_files.append(filler["local_path"])
                        total_duration += filler["duration"]
                        log.info("Filler added", vertical=v_id, duration=filler["duration"])
                    break
        
        # =====================
        # STITCH
        # =====================
        if len(segments) < 2:
            log.warning("Not enough segments", count=len(segments))
            return None
        
        ordered_paths = [s["path"] for s in segments]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"keernel_{user_id[:8]}_{timestamp}.mp3")
        
        if not stitch_audio_segments(ordered_paths, output_path):
            return None
        
        final_duration = get_audio_duration(output_path)
        
        # Upload
        filename = f"{user_id}/keernel_{timestamp}.mp3"
        audio_url = upload_to_storage(output_path, filename)
        
        if not audio_url:
            log.error("Upload failed")
            if os.path.exists(output_path):
                os.remove(output_path)
            return None
        
        if os.path.exists(output_path):
            os.remove(output_path)
        
        log.info("Keernel assembled", duration=final_duration, segments=len(segments))
        
        return {
            "audio_url": audio_url,
            "duration": final_duration,
            "segments": [{"type": s["type"], "duration": s["duration"]} for s in segments],
            "sources_data": sources_data
        }
        
    except Exception as e:
        log.error("Assembly failed", error=str(e))
        return None
    
    finally:
        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass


# ============================================
# ENTRY POINT
# ============================================

def generate_podcast_for_user(user_id: str) -> dict | None:
    """Main entry point for podcast generation."""
    log.info("Starting Keernel generation", user_id=user_id[:8])
    
    # Get user info
    try:
        user_result = supabase.table("users") \
            .select("first_name, target_duration, selected_verticals") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if not user_result.data:
            log.error("User not found")
            return None
        
        first_name = user_result.data.get("first_name") or "Ami"
        target_duration = user_result.data.get("target_duration") or 20
        selected_verticals = user_result.data.get("selected_verticals") or {
            "ai_tech": True, "politics": True, "finance": True, "science": True, "culture": True
        }
        
    except Exception as e:
        log.error("Failed to get user", error=str(e))
        return None
    
    # Get content queue
    try:
        queue_result = supabase.table("content_queue") \
            .select("url, priority, source, vertical_id") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .order("priority", desc=True) \
            .order("created_at") \
            .execute()
        
        if not queue_result.data:
            log.warning("No pending content")
            return None
        
        manual_urls = [item["url"] for item in queue_result.data 
                      if item.get("priority") == "high" or item.get("source") == "manual"]
        auto_urls = [item["url"] for item in queue_result.data 
                    if item.get("priority") != "high" and item.get("source") != "manual"]
        
    except Exception as e:
        log.error("Failed to get queue", error=str(e))
        return None
    
    # Assemble
    result = assemble_podcast(
        user_id=user_id,
        first_name=first_name,
        manual_urls=manual_urls,
        auto_urls=auto_urls,
        target_duration=target_duration,
        selected_verticals=selected_verticals
    )
    
    if not result:
        supabase.table("content_queue") \
            .update({"status": "failed"}) \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        return None
    
    # Create episode
    try:
        today = date.today()
        title = f"Keernel de {first_name} - {today.strftime('%d %B %Y')}"
        
        episode = supabase.table("episodes").insert({
            "user_id": user_id,
            "title": title,
            "audio_url": result["audio_url"],
            "audio_duration": result["duration"],
            "sources_data": result["sources_data"],
            "summary_text": f"Keernel avec {len(result['sources_data'])} sources"
        }).execute()
        
        supabase.table("content_queue") \
            .update({"status": "processed"}) \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        
        log.info("Episode created", episode_id=episode.data[0]["id"] if episode.data else None)
        
        return episode.data[0] if episode.data else None
        
    except Exception as e:
        log.error("Failed to create episode", error=str(e))
        return None
