"""
Keernel Playlist Selector - "14+1" Algorithm

Selects 15 segments from a daily pool of 30 based on user signal weights.
Includes a "wildcard" segment from ignored topics to break filter bubbles.
"""

import random
from typing import Optional
from datetime import date

import structlog
from db import supabase

log = structlog.get_logger()


def get_user_signal_weights(user_id: str) -> dict[str, int]:
    """
    Retrieve user's signal weights from database.
    Returns dict of {topic_id: weight (0-100)}.
    Default is 50 for all topics if not set.
    """
    try:
        result = supabase.table("user_signal_weights") \
            .select("weights") \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        
        if result.data and result.data.get("weights"):
            return result.data["weights"]
    except Exception as e:
        log.warning(f"Could not fetch user weights: {e}")
    
    # Default weights
    default_topics = [
        "ia", "quantum", "robotics",
        "asia", "regulation", "resources",
        "crypto", "macro", "stocks",
        "energy", "health", "space",
        "cinema", "gaming", "lifestyle"
    ]
    return {t: 50 for t in default_topics}


def get_daily_segment_pool(target_date: date) -> list[dict]:
    """
    Retrieve all available segments for a given date.
    Each segment has: id, topic_id, audio_url, duration, relevance_score.
    """
    try:
        result = supabase.table("segment_cache") \
            .select("id, content_hash, topic_slug, audio_url, audio_duration, relevance_score, source_title") \
            .eq("target_date", target_date.isoformat()) \
            .execute()
        
        segments = []
        for row in result.data or []:
            segments.append({
                "id": row["id"],
                "content_hash": row["content_hash"],
                "topic_id": row["topic_slug"],
                "audio_url": row["audio_url"],
                "duration": row["audio_duration"] or 60,
                "relevance_score": row.get("relevance_score", 0.5),
                "title": row.get("source_title", "")
            })
        
        log.info(f"📦 Segment pool: {len(segments)} segments for {target_date}")
        return segments
        
    except Exception as e:
        log.error(f"Failed to fetch segment pool: {e}")
        return []


def calculate_weighted_score(segment: dict, user_weights: dict[str, int]) -> float:
    """
    Calculate final score for a segment based on user weights.
    Formula: final_score = relevance_score * (user_weight / 100)
    """
    topic_id = segment["topic_id"]
    user_weight = user_weights.get(topic_id, 50)  # Default to 50 if not set
    relevance = segment.get("relevance_score", 0.5)
    
    return relevance * (user_weight / 100)


def select_wildcard(segments: list[dict], user_weights: dict[str, int]) -> Optional[dict]:
    """
    Select a wildcard segment from topics the user has set to 0 (ignored).
    Returns the segment with the highest raw relevance_score among ignored topics.
    """
    # Find topics with weight = 0
    ignored_topics = {topic for topic, weight in user_weights.items() if weight == 0}
    
    if not ignored_topics:
        log.info("🎲 No ignored topics, no wildcard")
        return None
    
    # Filter segments from ignored topics
    wildcard_candidates = [
        s for s in segments 
        if s["topic_id"] in ignored_topics
    ]
    
    if not wildcard_candidates:
        log.info("🎲 No segments available from ignored topics")
        return None
    
    # Select the one with highest raw relevance
    wildcard = max(wildcard_candidates, key=lambda s: s.get("relevance_score", 0))
    log.info(f"🎲 Wildcard selected: {wildcard['title'][:50]} (topic: {wildcard['topic_id']}, relevance: {wildcard['relevance_score']:.2f})")
    
    return wildcard


def get_daily_playlist(
    user_id: str,
    target_date: Optional[date] = None,
    target_count: int = 15
) -> list[dict]:
    """
    Main algorithm: Select optimal playlist using "14+1" logic.
    
    1. Calculate weighted scores for all segments
    2. Select top 14 by weighted score
    3. Add wildcard from ignored topics (if any)
    4. Insert wildcard at random position (5-12)
    5. Return ordered list of 15 segments
    
    Args:
        user_id: User's ID for weight lookup
        target_date: Date to fetch segments for (default: today)
        target_count: Target number of segments (default: 15)
    
    Returns:
        List of segment dicts ordered for playback
    """
    if target_date is None:
        target_date = date.today()
    
    log.info(f"🎯 Generating playlist for user {user_id[:8]}... ({target_date})")
    
    # 1. Get user weights and segment pool
    user_weights = get_user_signal_weights(user_id)
    segments = get_daily_segment_pool(target_date)
    
    if not segments:
        log.warning("❌ No segments available in pool")
        return []
    
    # Handle case where user has all weights at 0 (fallback to top by relevance)
    all_zero = all(w == 0 for w in user_weights.values())
    if all_zero:
        log.warning("⚠️ All weights are 0, falling back to top by relevance")
        segments.sort(key=lambda s: s.get("relevance_score", 0), reverse=True)
        return segments[:target_count]
    
    # 2. Calculate weighted scores
    for segment in segments:
        segment["final_score"] = calculate_weighted_score(segment, user_weights)
    
    # 3. Sort by final_score (descending)
    segments.sort(key=lambda s: s["final_score"], reverse=True)
    
    # 4. Select top 14 (or target_count - 1 if wildcard)
    main_selection_count = target_count - 1
    main_selection = segments[:main_selection_count]
    
    # Track selected IDs to avoid duplicate wildcard
    selected_ids = {s["id"] for s in main_selection}
    
    # 5. Select wildcard from remaining segments
    remaining_segments = [s for s in segments if s["id"] not in selected_ids]
    wildcard = select_wildcard(remaining_segments, user_weights)
    
    # 6. Build final playlist
    playlist = main_selection.copy()
    
    if wildcard:
        # Insert wildcard at random position between 5 and 12 (0-indexed: 4-11)
        insert_position = random.randint(4, min(11, len(playlist)))
        playlist.insert(insert_position, wildcard)
        log.info(f"🎲 Wildcard inserted at position {insert_position + 1}")
    else:
        # No wildcard, add one more from main pool
        if len(segments) > main_selection_count:
            playlist.append(segments[main_selection_count])
    
    # 7. Log summary
    log.info(f"✅ Playlist generated: {len(playlist)} segments")
    
    # Log topic distribution
    topic_counts = {}
    for s in playlist:
        topic = s["topic_id"]
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    log.info(f"📊 Topic distribution: {dict(sorted(topic_counts.items(), key=lambda x: -x[1]))}")
    
    return playlist


def get_playlist_segment_ids(user_id: str, target_date: Optional[date] = None) -> list[str]:
    """
    Convenience function that returns just the segment IDs for a playlist.
    """
    playlist = get_daily_playlist(user_id, target_date)
    return [s["id"] for s in playlist]


# ============================================
# INTEGRATION WITH STITCHER
# ============================================

def should_include_segment(
    segment_topic: str,
    user_weights: dict[str, int],
    already_selected: list[str],
    current_count: int,
    target_count: int = 15
) -> tuple[bool, float]:
    """
    Helper function for stitcher integration.
    Determines if a segment should be included based on weights.
    
    Returns:
        (should_include, priority_score)
    """
    weight = user_weights.get(segment_topic, 50)
    
    # If weight is 0, mark for potential wildcard
    if weight == 0:
        return (False, 0.0)
    
    # Calculate priority based on weight
    priority = weight / 100
    
    return (True, priority)
