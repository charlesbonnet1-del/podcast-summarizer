"""
Worker module for processing content queue and generating episodes.
Now uses the Stitcher for advanced audio assembly.
"""
import os
import structlog
from dotenv import load_dotenv

# Use new stitcher for podcast generation
from stitcher import generate_podcast_for_user
from db import supabase

load_dotenv()
log = structlog.get_logger()


def process_user_queue(user_id: str) -> dict | None:
    """
    Process all pending content for a user and generate an episode.
    Uses the new Stitcher architecture.
    
    Returns the created episode or None if failed.
    """
    log.info("Processing user queue", user_id=user_id)
    
    # Use the new stitcher
    episode = generate_podcast_for_user(user_id)
    
    if episode:
        log.info("Episode generated", episode_id=episode.get("id"), user_id=user_id[:8])
    else:
        log.warning("Failed to generate episode", user_id=user_id[:8])
    
    return episode


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
                log.info("Episode generated for user", user_id=user_id[:8], episode_id=episode.get("id"))
            else:
                log.warning("Failed to generate episode for user", user_id=user_id[:8])
        except Exception as e:
            log.error("Error processing user", user_id=user_id[:8], error=str(e))
    
    log.info("Batch processing complete")


if __name__ == "__main__":
    # Run batch processing when executed directly
    process_all_pending()
