"""
Worker module for processing content queue and generating episodes.
"""
import os
import tempfile
from datetime import datetime
import structlog
from dotenv import load_dotenv

from db import (
    get_pending_content,
    get_user_settings,
    update_content_status,
    create_episode,
    upload_audio_file,
    supabase,
)
from extractor import extract_content
from generator import (
    generate_podcast_script,
    generate_audio,
    generate_episode_title,
    get_audio_duration,
    build_sources_data,
)

load_dotenv()
log = structlog.get_logger()


def process_user_queue(user_id: str) -> dict | None:
    """
    Process all pending content for a user and generate an episode.
    
    Returns the created episode or None if failed.
    """
    log.info("Processing user queue", user_id=user_id)
    
    # Get pending content
    pending = get_pending_content(user_id)
    
    if not pending:
        log.warning("No pending content", user_id=user_id)
        return None
    
    # Get user settings
    settings = get_user_settings(user_id)
    target_duration = settings.get("default_duration", 15) if settings else 15
    voice_id = settings.get("voice_id", "alloy") if settings else "alloy"
    
    log.info("User settings", target_duration=target_duration, voice_id=voice_id)
    
    # Extract content from each item
    sources = []
    processed_ids = []
    
    for item in pending:
        log.info("Processing content item", item_id=item["id"], url=item["url"])
        
        # Update status to processing
        update_content_status(item["id"], "processing")
        
        try:
            result = extract_content(item["url"])
            
            if result:
                source_type, title, content = result
                sources.append({
                    "url": item["url"],
                    "title": title,
                    "content": content,
                    "source_type": source_type,
                })
                
                # Update with processed content
                update_content_status(
                    item["id"], 
                    "processed",
                    processed_content=content[:5000]  # Store truncated version
                )
                processed_ids.append(item["id"])
                
                log.info("Content extracted", item_id=item["id"], title=title)
            else:
                update_content_status(
                    item["id"],
                    "failed",
                    error_message="Failed to extract content"
                )
                log.warning("Failed to extract content", item_id=item["id"])
        
        except Exception as e:
            update_content_status(
                item["id"],
                "failed",
                error_message=str(e)[:500]
            )
            log.error("Error processing item", item_id=item["id"], error=str(e))
    
    if not sources:
        log.error("No content could be extracted", user_id=user_id)
        return None
    
    log.info("Content extraction complete", sources_count=len(sources))
    
    # Generate podcast script
    script = generate_podcast_script(sources, target_duration)
    
    if not script:
        log.error("Failed to generate script", user_id=user_id)
        return None
    
    log.info("Script generated", script_length=len(script))
    
    # Generate audio
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_audio_path = os.path.join(tempfile.gettempdir(), f"episode_{user_id}_{timestamp}.mp3")
    
    audio_path = generate_audio(script, voice_id, temp_audio_path)
    
    if not audio_path:
        log.error("Failed to generate audio", user_id=user_id)
        return None
    
    # Get audio duration
    audio_duration = get_audio_duration(audio_path)
    log.info("Audio generated", duration=audio_duration)
    
    # Upload to Supabase Storage
    filename = f"episode_{timestamp}.mp3"
    audio_url = upload_audio_file(user_id, audio_path, filename)
    
    if not audio_url:
        log.error("Failed to upload audio", user_id=user_id)
        return None
    
    log.info("Audio uploaded", audio_url=audio_url)
    
    # Clean up temp file
    try:
        os.remove(audio_path)
    except:
        pass
    
    # Generate episode title
    title = generate_episode_title(sources, script)
    
    # Build sources data for Show Notes
    sources_data = build_sources_data(sources)
    
    # Create episode record
    episode = create_episode(
        user_id=user_id,
        title=title,
        summary_text=script[:1000] + "..." if len(script) > 1000 else script,
        audio_url=audio_url,
        audio_duration=audio_duration,
        sources_data=sources_data
    )
    
    if episode:
        log.info("Episode created", episode_id=episode["id"], title=title)
        return episode
    else:
        log.error("Failed to create episode record", user_id=user_id)
        return None


def process_all_pending():
    """
    Process pending content for all users.
    This can be run as a scheduled job.
    """
    log.info("Starting batch processing")
    
    # Get all unique users with pending content
    result = supabase.table("content_queue").select("user_id").eq("status", "pending").execute()
    
    if not result.data:
        log.info("No pending content to process")
        return
    
    # Get unique user IDs
    user_ids = list(set(item["user_id"] for item in result.data))
    log.info("Users with pending content", count=len(user_ids))
    
    # Process each user
    for user_id in user_ids:
        try:
            episode = process_user_queue(user_id)
            if episode:
                log.info("Episode generated for user", user_id=user_id, episode_id=episode["id"])
            else:
                log.warning("Failed to generate episode for user", user_id=user_id)
        except Exception as e:
            log.error("Error processing user", user_id=user_id, error=str(e))
    
    log.info("Batch processing complete")


if __name__ == "__main__":
    # Run batch processing when executed directly
    process_all_pending()
