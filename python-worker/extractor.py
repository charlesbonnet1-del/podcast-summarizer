"""
Content extraction utilities for YouTube, articles, and podcasts.
"""
import re
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from trafilatura import fetch_url, extract
import structlog

log = structlog.get_logger()


def detect_source_type(url: str) -> str:
    """Detect the type of content from URL."""
    url_lower = url.lower()
    
    # YouTube patterns
    youtube_patterns = [
        r'youtube\.com/watch',
        r'youtu\.be/',
        r'youtube\.com/shorts',
        r'm\.youtube\.com'
    ]
    if any(re.search(pattern, url_lower) for pattern in youtube_patterns):
        return "youtube"
    
    # Podcast patterns (common podcast hosts)
    podcast_patterns = [
        r'podcasts\.apple\.com',
        r'spotify\.com/episode',
        r'anchor\.fm',
        r'podbean\.com',
        r'buzzsprout\.com',
        r'transistor\.fm'
    ]
    if any(re.search(pattern, url_lower) for pattern in podcast_patterns):
        return "podcast"
    
    # Default to article
    return "article"


def extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/v/)([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_youtube_transcript(url: str) -> tuple[str, str] | None:
    """
    Get transcript from a YouTube video.
    Returns (title, transcript_text) or None if failed.
    """
    video_id = extract_youtube_id(url)
    if not video_id:
        log.warning("Could not extract YouTube video ID", url=url)
        return None
    
    try:
        # Try to get transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try English first, then auto-generated, then any available
        transcript = None
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
            except:
                # Get first available transcript
                for t in transcript_list:
                    transcript = t
                    break
        
        if transcript:
            # Fetch the transcript
            transcript_data = transcript.fetch()
            
            # Combine all text segments
            full_text = " ".join([segment['text'] for segment in transcript_data])
            
            # Get video title via oEmbed
            title = get_youtube_title(url) or f"YouTube Video {video_id}"
            
            log.info("Extracted YouTube transcript", video_id=video_id, length=len(full_text))
            return (title, full_text)
    
    except Exception as e:
        log.error("Failed to get YouTube transcript", video_id=video_id, error=str(e))
    
    return None


def get_youtube_title(url: str) -> str | None:
    """Get YouTube video title via oEmbed API."""
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        response = httpx.get(oembed_url, timeout=10)
        if response.status_code == 200:
            return response.json().get("title")
    except:
        pass
    return None


def extract_article_content(url: str) -> tuple[str, str] | None:
    """
    Extract content from an article URL using trafilatura.
    Returns (title, content) or None if failed.
    """
    try:
        # First try with Jina Reader API for better extraction
        jina_result = extract_with_jina(url)
        if jina_result:
            return jina_result
        
        # Fallback to trafilatura
        downloaded = fetch_url(url)
        if downloaded:
            # Extract main content
            content = extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                favor_precision=True
            )
            
            if content and len(content) > 100:
                # Try to extract title
                title = extract(downloaded, output_format='json')
                title = get_page_title(url) or "Article"
                
                log.info("Extracted article content", url=url, length=len(content))
                return (title, content)
    
    except Exception as e:
        log.error("Failed to extract article", url=url, error=str(e))
    
    return None


def extract_with_jina(url: str) -> tuple[str, str] | None:
    """
    Extract content using Jina Reader API (better for complex sites).
    """
    import os
    jina_api_key = os.getenv("JINA_API_KEY")
    
    try:
        headers = {}
        if jina_api_key:
            headers["Authorization"] = f"Bearer {jina_api_key}"
        
        # Jina Reader API
        reader_url = f"https://r.jina.ai/{url}"
        response = httpx.get(reader_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            content = response.text
            
            # Extract title from the first line (Jina usually puts title first)
            lines = content.strip().split('\n')
            title = lines[0].strip('# ') if lines else "Article"
            text = '\n'.join(lines[1:]) if len(lines) > 1 else content
            
            if len(text) > 100:
                log.info("Extracted with Jina Reader", url=url, length=len(text))
                return (title, text)
    
    except Exception as e:
        log.warning("Jina Reader failed, falling back", url=url, error=str(e))
    
    return None


def get_page_title(url: str) -> str | None:
    """Get page title from HTML."""
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        if response.status_code == 200:
            # Simple regex to extract title
            match = re.search(r'<title[^>]*>([^<]+)</title>', response.text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    except:
        pass
    return None


def extract_content(url: str, source_type: str = None) -> tuple[str, str, str] | None:
    """
    Main extraction function that detects source type and extracts content.
    
    Args:
        url: The URL to extract content from
        source_type: Optional hint for source type (ignored, auto-detected)
        
    Returns (source_type, title, content) or None if failed.
    """
    # Auto-detect source type (ignore hint for consistency)
    detected_type = detect_source_type(url)
    log.info("Extracting content", url=url, source_type=detected_type)
    
    result = None
    
    if detected_type == "youtube":
        result = get_youtube_transcript(url)
    elif detected_type == "article":
        result = extract_article_content(url)
    elif detected_type == "podcast":
        # For podcasts, we'd need additional processing (audio download + Whisper)
        # For MVP, treat as article and try to get show notes
        result = extract_article_content(url)
        if not result:
            log.warning("Podcast extraction not fully supported yet", url=url)
    
    if result:
        title, content = result
        return (detected_type, title, content)
    
    return None
