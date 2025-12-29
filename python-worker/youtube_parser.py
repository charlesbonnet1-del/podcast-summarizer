"""
Keernel YouTube Parser Module
==============================

Extracts and processes YouTube video transcripts with strict legal compliance.

Legal Requirements:
- NEVER use "article" for YouTube sources → always "vidéo"
- Mandatory attribution prefix: "[Author] dit dans sa vidéo que..."
- Original URL must be preserved and displayed

Technical Flow:
1. Extract video_id from URL
2. Try youtube-transcript-api (manual > auto subtitles)
3. Clean transcript with Groq LLM (punctuation, proper nouns)
4. Fallback: yt-dlp + Whisper if transcripts unavailable
"""

import os
import re
import json
import tempfile
import subprocess
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs
from datetime import datetime

import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Proper noun corrections (technical terms often misspelled in transcripts)
PROPER_NOUN_CORRECTIONS = {
    # People - Tech
    "andreesen": "Andreessen",
    "andreessen": "Andreessen",
    "marc andreesen": "Marc Andreessen",
    "elon musk": "Elon Musk",
    "sam altman": "Sam Altman",
    "satya nadella": "Satya Nadella",
    "sundar pichai": "Sundar Pichai",
    "jensen huang": "Jensen Huang",
    "dario amodei": "Dario Amodei",
    "demis hassabis": "Demis Hassabis",
    
    # Companies
    "openai": "OpenAI",
    "open ai": "OpenAI",
    "anthropic": "Anthropic",
    "deepmind": "DeepMind",
    "deep mind": "DeepMind",
    "nvidia": "NVIDIA",
    "meta": "Meta",
    "google": "Google",
    "microsoft": "Microsoft",
    "tesla": "Tesla",
    "spacex": "SpaceX",
    "space x": "SpaceX",
    "huggingface": "Hugging Face",
    "hugging face": "Hugging Face",
    
    # AI Models
    "llama": "LLaMA",
    "lama": "LLaMA",
    "gpt": "GPT",
    "gpt4": "GPT-4",
    "gpt 4": "GPT-4",
    "gpt-4": "GPT-4",
    "claude": "Claude",
    "gemini": "Gemini",
    "mistral": "Mistral",
    "chatgpt": "ChatGPT",
    "chat gpt": "ChatGPT",
    "midjourney": "Midjourney",
    "mid journey": "Midjourney",
    "dall-e": "DALL-E",
    "dalle": "DALL-E",
    "sora": "Sora",
    "copilot": "Copilot",
    
    # Tech Terms
    "ai": "IA",
    "api": "API",
    "gpu": "GPU",
    "cpu": "CPU",
    "llm": "LLM",
    "rag": "RAG",
    "transformer": "Transformer",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    
    # French corrections
    "etats unis": "États-Unis",
    "etats-unis": "États-Unis",
}

# ============================================
# EXCEPTIONS
# ============================================

class YouTubeParserError(Exception):
    """Base exception for YouTube parser errors."""
    pass

class TranscriptUnavailable(YouTubeParserError):
    """Raised when transcript cannot be retrieved via API."""
    pass

class VideoNotFound(YouTubeParserError):
    """Raised when video doesn't exist or is private."""
    pass

class AudioExtractionFailed(YouTubeParserError):
    """Raised when yt-dlp fails to extract audio."""
    pass


# ============================================
# YOUTUBE PARSER CLASS
# ============================================

class YouTubeParser:
    """
    Parse YouTube videos with legal compliance for citation.
    
    Usage:
        parser = YouTubeParser()
        result = parser.process("https://www.youtube.com/watch?v=abc123")
        
        # result = {
        #     "source_type": "youtube_video",
        #     "attribution_prefix": "Lex Fridman explique dans sa vidéo que",
        #     "cleaned_text": "...",
        #     "original_url": "https://www.youtube.com/watch?v=abc123",
        #     "channel_name": "Lex Fridman",
        #     "video_title": "...",
        #     "duration_seconds": 3600,
        #     "status": "processed"
        # }
    """
    
    def __init__(self):
        """Initialize the YouTube parser."""
        self.groq_client = None
        
        if GROQ_API_KEY:
            from groq import Groq
            self.groq_client = Groq(api_key=GROQ_API_KEY)
    
    # ==========================================
    # STEP 1: URL PARSING & VIDEO DETECTION
    # ==========================================
    
    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """Check if URL is a valid YouTube video URL."""
        if not url:
            return False
        
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
            r'(?:https?://)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
        ]
        
        return any(re.match(pattern, url) for pattern in youtube_patterns)
    
    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats."""
        if not url:
            return None
        
        # youtu.be/VIDEO_ID
        if 'youtu.be/' in url:
            match = re.search(r'youtu\.be/([\w-]+)', url)
            if match:
                return match.group(1)
        
        # youtube.com/watch?v=VIDEO_ID
        if 'youtube.com' in url:
            parsed = urlparse(url)
            
            # /watch?v=VIDEO_ID
            if parsed.path == '/watch':
                params = parse_qs(parsed.query)
                if 'v' in params:
                    return params['v'][0]
            
            # /v/VIDEO_ID or /embed/VIDEO_ID or /shorts/VIDEO_ID
            match = re.search(r'/(v|embed|shorts)/([\w-]+)', parsed.path)
            if match:
                return match.group(2)
        
        return None
    
    def get_video_metadata(self, video_id: str) -> dict:
        """Get video metadata (title, channel, duration) via yt-dlp."""
        try:
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-download',
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                log.warning(f"⚠️ yt-dlp metadata failed: {result.stderr[:200]}")
                return {}
            
            data = json.loads(result.stdout)
            
            return {
                "video_title": data.get("title", ""),
                "channel_name": data.get("channel", data.get("uploader", "")),
                "duration_seconds": data.get("duration", 0),
                "upload_date": data.get("upload_date", ""),
                "view_count": data.get("view_count", 0),
                "description": data.get("description", "")[:500]
            }
            
        except subprocess.TimeoutExpired:
            log.warning("⚠️ yt-dlp metadata timeout")
            return {}
        except json.JSONDecodeError:
            log.warning("⚠️ yt-dlp returned invalid JSON")
            return {}
        except Exception as e:
            log.warning(f"⚠️ Metadata extraction failed: {e}")
            return {}
    
    # ==========================================
    # STEP 2: TRANSCRIPT EXTRACTION
    # ==========================================
    
    def get_transcript(self, video_id: str, languages: list = None) -> Tuple[str, str]:
        """
        Get transcript using youtube-transcript-api.
        Priority: Manual subtitles > Auto-generated
        
        Returns:
            Tuple of (transcript_text, transcript_type)
            transcript_type: "manual" or "auto"
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api._errors import (
                TranscriptsDisabled,
                NoTranscriptFound,
                VideoUnavailable
            )
        except ImportError:
            raise YouTubeParserError("youtube-transcript-api not installed")
        
        if not languages:
            languages = ['fr', 'en', 'fr-FR', 'en-US', 'en-GB']
        
        try:
            # List available transcripts
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try manual transcripts first (higher quality)
            transcript = None
            transcript_type = "auto"
            
            try:
                # Priority 1: Manual transcript in preferred language
                transcript = transcript_list.find_manually_created_transcript(languages)
                transcript_type = "manual"
                log.info(f"✅ Found manual transcript ({transcript.language_code})")
            except NoTranscriptFound:
                try:
                    # Priority 2: Auto-generated transcript
                    transcript = transcript_list.find_generated_transcript(languages)
                    transcript_type = "auto"
                    log.info(f"✅ Found auto transcript ({transcript.language_code})")
                except NoTranscriptFound:
                    # Priority 3: Any available transcript, translated
                    for t in transcript_list:
                        try:
                            transcript = t.translate('fr')
                            transcript_type = "translated"
                            log.info(f"✅ Using translated transcript from {t.language_code}")
                            break
                        except:
                            continue
            
            if not transcript:
                raise TranscriptUnavailable(f"No transcript available for video {video_id}")
            
            # Fetch and combine transcript segments
            segments = transcript.fetch()
            
            # Combine all text segments
            full_text = ' '.join(segment['text'] for segment in segments)
            
            # Basic cleanup (remove [Music], [Applause], etc.)
            full_text = re.sub(r'\[.*?\]', '', full_text)
            full_text = re.sub(r'\s+', ' ', full_text).strip()
            
            return full_text, transcript_type
            
        except TranscriptsDisabled:
            raise TranscriptUnavailable(f"Transcripts disabled for video {video_id}")
        except VideoUnavailable:
            raise VideoNotFound(f"Video {video_id} is unavailable or private")
        except NoTranscriptFound:
            raise TranscriptUnavailable(f"No transcript found for video {video_id}")
        except Exception as e:
            raise TranscriptUnavailable(f"Transcript extraction failed: {e}")
    
    # ==========================================
    # STEP 3: FALLBACK - AUDIO EXTRACTION + WHISPER
    # ==========================================
    
    def extract_audio_and_transcribe(self, video_id: str) -> str:
        """
        Fallback: Download audio with yt-dlp and transcribe with Whisper.
        Used when youtube-transcript-api fails.
        """
        log.info(f"🎵 Fallback: Extracting audio for video {video_id}...")
        
        if not self.groq_client:
            raise YouTubeParserError("Groq client not available for Whisper transcription")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, f"{video_id}.mp3")
            
            # Download audio with yt-dlp
            cmd = [
                'yt-dlp',
                '-x',  # Extract audio
                '--audio-format', 'mp3',
                '--audio-quality', '128K',
                '-o', audio_path,
                '--max-filesize', '25M',  # Whisper limit
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 min timeout
                )
                
                if result.returncode != 0:
                    raise AudioExtractionFailed(f"yt-dlp failed: {result.stderr[:200]}")
                
                # Check if file exists and has content
                if not os.path.exists(audio_path):
                    # yt-dlp might add extension
                    audio_path = audio_path.replace('.mp3', '.mp3.mp3')
                    if not os.path.exists(audio_path):
                        raise AudioExtractionFailed("Audio file not created")
                
                file_size = os.path.getsize(audio_path)
                if file_size > 25 * 1024 * 1024:  # 25MB limit
                    raise AudioExtractionFailed(f"Audio file too large: {file_size / 1024 / 1024:.1f}MB")
                
                log.info(f"✅ Audio extracted: {file_size / 1024 / 1024:.1f}MB")
                
                # Transcribe with Groq Whisper
                with open(audio_path, 'rb') as audio_file:
                    transcription = self.groq_client.audio.transcriptions.create(
                        model="whisper-large-v3",
                        file=audio_file,
                        language="fr",  # Hint for better accuracy
                        response_format="text"
                    )
                
                log.info(f"✅ Whisper transcription complete: {len(transcription)} chars")
                return transcription
                
            except subprocess.TimeoutExpired:
                raise AudioExtractionFailed("Audio extraction timeout (>5min)")
            except Exception as e:
                raise AudioExtractionFailed(f"Audio extraction failed: {e}")
    
    # ==========================================
    # STEP 4: TRANSCRIPT CLEANING (Groq LLM)
    # ==========================================
    
    def clean_transcript(self, raw_text: str, channel_name: str = "") -> str:
        """
        Clean raw transcript using Groq LLM.
        - Add punctuation and capitalization
        - Fix proper noun spelling
        - Preserve oral tone
        """
        if not self.groq_client:
            log.warning("⚠️ Groq not available, using basic cleaning")
            return self._basic_clean(raw_text)
        
        # First pass: LLM cleaning
        prompt = f"""Tu es un correcteur de transcription. Ton travail est de mettre en forme ce transcript brut de vidéo YouTube.

RÈGLES STRICTES:
1. Ajoute la ponctuation (points, virgules, points d'interrogation)
2. Ajoute les majuscules en début de phrase et pour les noms propres
3. NE CHANGE AUCUN MOT - garde exactement le vocabulaire original
4. MAINTIENS LE TON ORAL - ne transforme pas en texte écrit formel
5. Découpe en paragraphes logiques (1 paragraphe = 1 idée)

Chaîne YouTube: {channel_name}

TRANSCRIPT BRUT:
{raw_text[:8000]}

TRANSCRIPT CORRIGÉ:"""

        try:
            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000
            )
            
            cleaned = response.choices[0].message.content.strip()
            
            # Second pass: Proper noun corrections
            cleaned = self._fix_proper_nouns(cleaned)
            
            log.info(f"✅ Transcript cleaned: {len(raw_text)} → {len(cleaned)} chars")
            return cleaned
            
        except Exception as e:
            log.warning(f"⚠️ LLM cleaning failed: {e}, using basic cleaning")
            return self._basic_clean(raw_text)
    
    def _basic_clean(self, text: str) -> str:
        """Basic cleaning without LLM."""
        # Fix obvious proper nouns
        text = self._fix_proper_nouns(text)
        
        # Basic sentence capitalization
        sentences = re.split(r'([.!?]+)', text)
        result = []
        for i, part in enumerate(sentences):
            if i % 2 == 0 and part:  # Text part
                part = part.strip()
                if part:
                    part = part[0].upper() + part[1:]
            result.append(part)
        
        return ''.join(result)
    
    def _fix_proper_nouns(self, text: str) -> str:
        """Fix common proper noun misspellings."""
        # Case-insensitive replacement
        for wrong, correct in PROPER_NOUN_CORRECTIONS.items():
            # Word boundary matching
            pattern = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE)
            text = pattern.sub(correct, text)
        
        return text
    
    # ==========================================
    # STEP 5: LEGAL ATTRIBUTION
    # ==========================================
    
    def generate_attribution(self, channel_name: str, video_title: str = "") -> dict:
        """
        Generate legally compliant attribution for citation.
        
        LEGAL REQUIREMENT: Never use "article" for YouTube sources.
        Always use "vidéo" and include channel name.
        """
        if not channel_name:
            channel_name = "l'auteur"
        
        # Clean channel name (remove "- Topic" suffixes, etc.)
        channel_name = re.sub(r'\s*-\s*Topic$', '', channel_name)
        channel_name = channel_name.strip()
        
        # Generate multiple attribution formats for variety
        attributions = [
            f"{channel_name} explique dans sa vidéo que",
            f"Selon la vidéo de {channel_name},",
            f"Dans sa dernière vidéo, {channel_name} affirme que",
            f"{channel_name} dit dans sa vidéo que",
            f"D'après la vidéo de {channel_name},",
        ]
        
        # Pick based on hash of channel name for consistency
        idx = hash(channel_name) % len(attributions)
        
        return {
            "attribution_prefix": attributions[idx],
            "channel_name": channel_name,
            "source_label": f"Vidéo de {channel_name}",  # For UI display
            "citation_format": f"Source : Vidéo YouTube - {channel_name}"
        }
    
    # ==========================================
    # MAIN PROCESSING METHOD
    # ==========================================
    
    def process(self, url: str) -> dict:
        """
        Process a YouTube video URL and return structured data.
        
        Returns:
            dict with source_type, attribution_prefix, cleaned_text, etc.
        
        Raises:
            YouTubeParserError on failure
        """
        log.info(f"🎬 Processing YouTube URL: {url}")
        
        # Validate URL
        if not self.is_youtube_url(url):
            raise YouTubeParserError(f"Invalid YouTube URL: {url}")
        
        # Extract video ID
        video_id = self.extract_video_id(url)
        if not video_id:
            raise YouTubeParserError(f"Could not extract video ID from: {url}")
        
        log.info(f"📹 Video ID: {video_id}")
        
        # Get metadata
        metadata = self.get_video_metadata(video_id)
        channel_name = metadata.get("channel_name", "")
        video_title = metadata.get("video_title", "")
        
        # Try transcript extraction
        transcript_text = None
        transcript_type = None
        
        try:
            transcript_text, transcript_type = self.get_transcript(video_id)
            log.info(f"✅ Transcript retrieved ({transcript_type}): {len(transcript_text)} chars")
            
        except TranscriptUnavailable as e:
            log.warning(f"⚠️ Transcript unavailable: {e}")
            log.info("🔄 Attempting fallback: audio extraction + Whisper...")
            
            try:
                transcript_text = self.extract_audio_and_transcribe(video_id)
                transcript_type = "whisper"
            except AudioExtractionFailed as e:
                raise YouTubeParserError(f"All transcript methods failed: {e}")
        
        # Clean transcript
        cleaned_text = self.clean_transcript(transcript_text, channel_name)
        
        # Generate attribution
        attribution = self.generate_attribution(channel_name, video_title)
        
        # Build canonical URL
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Build result
        result = {
            # LEGAL: Source type is explicitly "youtube_video" (never "article")
            "source_type": "youtube_video",
            
            # LEGAL: Attribution prefix for Alice & Bob
            "attribution_prefix": attribution["attribution_prefix"],
            "source_label": attribution["source_label"],
            "citation_format": attribution["citation_format"],
            
            # Content
            "cleaned_text": cleaned_text,
            "raw_text_length": len(transcript_text),
            "cleaned_text_length": len(cleaned_text),
            
            # Metadata
            "video_id": video_id,
            "original_url": canonical_url,
            "channel_name": channel_name,
            "video_title": video_title,
            "duration_seconds": metadata.get("duration_seconds", 0),
            "upload_date": metadata.get("upload_date", ""),
            
            # Technical
            "transcript_type": transcript_type,
            "processed_at": datetime.now().isoformat(),
            "status": "processed"
        }
        
        log.info(f"✅ YouTube processing complete: {channel_name} - {video_title[:50]}...")
        
        return result


# ============================================
# INTEGRATION WITH CONTENT QUEUE
# ============================================

def process_youtube_for_queue(url: str, user_id: str = None) -> Optional[dict]:
    """
    Process YouTube URL and format for content_queue insertion.
    
    Returns dict ready for Supabase insertion.
    """
    try:
        parser = YouTubeParser()
        result = parser.process(url)
        
        # Format for content_queue
        queue_entry = {
            "user_id": user_id,
            "url": result["original_url"],
            "title": result["video_title"],
            "source_type": "youtube_video",  # LEGAL: Never "article"
            "source_name": result["channel_name"],
            "source": "youtube",
            "processed_content": result["cleaned_text"][:10000],  # Limit size
            "status": "pending",
            "priority": "normal",
            "metadata": {
                "attribution_prefix": result["attribution_prefix"],
                "source_label": result["source_label"],
                "citation_format": result["citation_format"],
                "video_id": result["video_id"],
                "duration_seconds": result["duration_seconds"],
                "transcript_type": result["transcript_type"]
            }
        }
        
        return queue_entry
        
    except YouTubeParserError as e:
        log.error(f"❌ YouTube processing failed: {e}")
        return None
    except Exception as e:
        log.error(f"❌ Unexpected error processing YouTube: {e}")
        return None


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser_args = argparse.ArgumentParser(description="Keernel YouTube Parser")
    parser_args.add_argument("url", type=str, help="YouTube URL to process")
    parser_args.add_argument("--raw", action="store_true", help="Output raw JSON")
    
    args = parser_args.parse_args()
    
    parser = YouTubeParser()
    
    try:
        result = parser.process(args.url)
        
        if args.raw:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"\n{'='*60}")
            print(f"🎬 {result['video_title']}")
            print(f"📺 {result['channel_name']}")
            print(f"⏱️  {result['duration_seconds'] // 60} minutes")
            print(f"{'='*60}")
            print(f"\n📝 Attribution: {result['attribution_prefix']}")
            print(f"\n📄 Transcript ({result['transcript_type']}):")
            print(f"{result['cleaned_text'][:1000]}...")
            print(f"\n🔗 URL: {result['original_url']}")
            
    except YouTubeParserError as e:
        print(f"❌ Error: {e}")
        exit(1)
