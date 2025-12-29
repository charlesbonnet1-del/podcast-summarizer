"""
Keernel Phonetic Sanitizer

Cleans text before sending to TTS (Cartesia) to ensure proper pronunciation.
Loads phonetic replacements from a Google Sheet lexicon.

Spreadsheet ID: 1CUkHEKITHUF2qYe7tHZXsPZbHj-rHSBwCJi1f8-6NZ4
Structure: 
  - Column A: terme (original term)
  - Column B: traduction (phonetic replacement)
  - Row 1: Headers
  - Data starts at Row 2
"""

import os
import re
import time
from typing import Optional
from functools import lru_cache

import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

PHONETIC_LEXICON_SPREADSHEET_ID = "1CUkHEKITHUF2qYe7tHZXsPZbHj-rHSBwCJi1f8-6NZ4"
PHONETIC_LEXICON_WORKSHEET_GID = 0  # First sheet

# Cache duration (seconds) - refresh lexicon every 10 minutes
LEXICON_CACHE_TTL = 600

# Module-level cache
_lexicon_cache: dict = {}
_lexicon_cache_time: float = 0


# ============================================
# GOOGLE SHEETS CONNECTION
# ============================================

def _get_gsheet_client():
    """Initialize Google Sheets client using shared credentials from sourcing.py."""
    try:
        # Import from sourcing to reuse credentials logic
        from sourcing import get_gsheet_client
        return get_gsheet_client()
    except ImportError:
        log.warning("Could not import get_gsheet_client from sourcing")
        return None
    except Exception as e:
        log.error("Failed to get GSheet client", error=str(e))
        return None


def get_phonetic_lexicon() -> dict:
    """
    Fetch phonetic lexicon from Google Sheet.
    
    Returns:
        Dict mapping terms to their phonetic replacements.
        Example: {"GPT": "Gé Pé Té", "NVIDIA": "Envidia", "CEO": "cé-i-o"}
    """
    global _lexicon_cache, _lexicon_cache_time
    
    # Check cache validity
    current_time = time.time()
    if _lexicon_cache and (current_time - _lexicon_cache_time) < LEXICON_CACHE_TTL:
        log.debug("Using cached phonetic lexicon", entries=len(_lexicon_cache))
        return _lexicon_cache
    
    log.info("🔤 Loading phonetic lexicon from GSheet...")
    
    try:
        client = _get_gsheet_client()
        if not client:
            log.warning("GSheet client not available, using empty lexicon")
            return _lexicon_cache or {}
        
        # Open the phonetic lexicon spreadsheet
        spreadsheet = client.open_by_key(PHONETIC_LEXICON_SPREADSHEET_ID)
        worksheet = spreadsheet.get_worksheet(PHONETIC_LEXICON_WORKSHEET_GID)
        
        # Read all data from A2:B (skip header row)
        # Column A = terme, Column B = traduction
        all_values = worksheet.get("A2:B")
        
        if not all_values:
            log.warning("Phonetic lexicon is empty")
            return {}
        
        # Build lexicon dict
        lexicon = {}
        for row in all_values:
            if len(row) >= 2:
                terme = row[0].strip() if row[0] else ""
                traduction = row[1].strip() if row[1] else ""
                
                if terme and traduction:
                    lexicon[terme] = traduction
        
        # Update cache
        _lexicon_cache = lexicon
        _lexicon_cache_time = current_time
        
        log.info("✅ Phonetic lexicon loaded", entries=len(lexicon))
        
        # Log sample entries for debugging
        if lexicon:
            sample = list(lexicon.items())[:5]
            log.debug("Sample entries", sample=sample)
        
        return lexicon
        
    except Exception as e:
        log.error("Failed to load phonetic lexicon", error=str(e))
        # Return cached version if available
        return _lexicon_cache or {}


def refresh_lexicon():
    """Force refresh of the phonetic lexicon cache."""
    global _lexicon_cache_time
    _lexicon_cache_time = 0
    return get_phonetic_lexicon()


# ============================================
# TEXT SANITIZATION
# ============================================

def sanitize_for_tts(text: str) -> str:
    """
    Sanitize text for TTS by applying phonetic replacements.
    
    Uses word boundaries (\\b) to avoid partial matches.
    Example: "CEO" becomes "cé-i-o" but "CEOship" is left alone.
    
    V13: Also triples question marks (? → ???) for proper interrogative intonation.
    
    Args:
        text: Raw text to sanitize
        
    Returns:
        Sanitized text ready for TTS API
    """
    if not text:
        return text
    
    # Get lexicon (uses cache)
    lexicon = get_phonetic_lexicon()
    
    if not lexicon:
        log.debug("No phonetic lexicon available, returning original text")
        return text
    
    sanitized = text
    replacements_made = 0
    
    # Sort terms by length (longest first) to avoid partial replacement issues
    # e.g., "OpenAI" should be replaced before "AI"
    sorted_terms = sorted(lexicon.keys(), key=len, reverse=True)
    
    for terme in sorted_terms:
        traduction = lexicon[terme]
        
        # Build regex pattern with word boundaries
        # Use re.IGNORECASE for case-insensitive matching
        # Escape special regex characters in the term
        escaped_terme = re.escape(terme)
        
        # Pattern: word boundary + term + word boundary
        # Handle special cases like "GPT-4" where hyphen is part of the term
        pattern = rf'\b{escaped_terme}\b'
        
        # Count matches before replacement
        matches = len(re.findall(pattern, sanitized, flags=re.IGNORECASE))
        
        if matches > 0:
            # Replace with phonetic version
            # Preserve case of first letter if the replacement starts with a letter
            def replace_fn(match):
                original = match.group(0)
                # If original is all caps and replacement isn't, keep it natural
                if original.isupper() and not traduction.isupper():
                    return traduction
                # If original starts with uppercase, capitalize replacement
                if original[0].isupper() and traduction[0].islower():
                    return traduction[0].upper() + traduction[1:]
                return traduction
            
            sanitized = re.sub(pattern, replace_fn, sanitized, flags=re.IGNORECASE)
            replacements_made += matches
    
    # V13: Triple question marks for proper TTS interrogation
    # Replace single ? with ??? (but avoid creating more than 3)
    # First normalize any existing multiple ? to single
    sanitized = re.sub(r'\?+', '?', sanitized)
    # Then triple them
    question_count = sanitized.count('?')
    sanitized = sanitized.replace('?', '???')
    
    if replacements_made > 0 or question_count > 0:
        log.debug("TTS sanitization complete", 
                  phonetic_replacements=replacements_made,
                  questions_tripled=question_count,
                  original_length=len(text),
                  sanitized_length=len(sanitized))
    
    return sanitized


def sanitize_dialogue_script(script: str) -> str:
    """
    Sanitize a full dialogue script for TTS.
    
    Handles [A] and [B] speaker tags without modifying them.
    Applies phonetic replacements to dialogue content only.
    
    Args:
        script: Full dialogue script with [A]/[B] tags
        
    Returns:
        Sanitized script ready for TTS
    """
    if not script:
        return script
    
    # Split by lines to preserve structure
    lines = script.split('\n')
    sanitized_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Don't modify speaker tags
        if stripped in ['[A]', '[B]']:
            sanitized_lines.append(line)
        else:
            # Sanitize dialogue content
            sanitized_lines.append(sanitize_for_tts(line))
    
    return '\n'.join(sanitized_lines)


# ============================================
# COMMON PHONETIC PATTERNS (Fallback)
# ============================================

# These are applied if the GSheet is unavailable
FALLBACK_PHONETICS = {
    # Tech terms
    "AI": "A.I.",
    "API": "A.P.I.",
    "GPU": "G.P.U.",
    "CPU": "C.P.U.",
    "LLM": "L.L.M.",
    "AGI": "A.G.I.",
    "CEO": "C.E.O.",
    "CTO": "C.T.O.",
    "CFO": "C.F.O.",
    
    # Companies (common mispronunciations)
    "OpenAI": "Open A.I.",
    "NVIDIA": "Envidia",
    "Anthropic": "An-tro-pic",
    
    # French-specific
    "€": "euros",
    "$": "dollars",
    "%": "pourcent",
}


def apply_fallback_phonetics(text: str) -> str:
    """Apply basic fallback phonetic replacements if GSheet is unavailable."""
    if not text:
        return text
    
    sanitized = text
    for terme, traduction in FALLBACK_PHONETICS.items():
        pattern = rf'\b{re.escape(terme)}\b'
        sanitized = re.sub(pattern, traduction, sanitized, flags=re.IGNORECASE)
    
    return sanitized


# ============================================
# INITIALIZATION
# ============================================

def init_phonetic_sanitizer():
    """Initialize the phonetic sanitizer by preloading the lexicon."""
    log.info("🔤 Initializing phonetic sanitizer...")
    lexicon = get_phonetic_lexicon()
    log.info(f"✅ Phonetic sanitizer ready with {len(lexicon)} entries")
    return len(lexicon) > 0


# ============================================
# CLI TESTING
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phonetic Sanitizer for TTS")
    parser.add_argument("--test", type=str, help="Text to sanitize")
    parser.add_argument("--refresh", action="store_true", help="Force refresh lexicon")
    parser.add_argument("--list", action="store_true", help="List lexicon entries")
    
    args = parser.parse_args()
    
    if args.refresh:
        lexicon = refresh_lexicon()
        print(f"Lexicon refreshed: {len(lexicon)} entries")
    
    if args.list:
        lexicon = get_phonetic_lexicon()
        print(f"\n📚 Phonetic Lexicon ({len(lexicon)} entries):")
        print("-" * 40)
        for terme, traduction in sorted(lexicon.items()):
            print(f"  {terme:20} → {traduction}")
    
    if args.test:
        print(f"\nOriginal: {args.test}")
        sanitized = sanitize_for_tts(args.test)
        print(f"Sanitized: {sanitized}")
