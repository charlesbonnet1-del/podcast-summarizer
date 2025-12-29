"""
Keernel Playlist Selector - "14+1" Algorithm

Selects 15 segments from a daily pool of 30 based on user signal weights.
Includes a "wildcard" segment from ignored topics to break filter bubbles.

Scoring Formula: Final_Score = (Relevance * Weight) * (1 / (1 + Age_in_days))
- Ensures fresh content beats stale content at equal relevance
- Respects user topic preferences
- Maintains content quality standards
"""

import random
from typing import Optional
from datetime import date, datetime, timedelta

import structlog
from db import supabase
from content_scorer import (
    calculate_final_score,
    calculate_age_decay,
    filter_expired_content,
    MAX_CACHE_AGE_DAYS
)

log = structlog.get_logger()

# Updated topic list with Influence vertical
DEFAULT_TOPICS = [
    # Tech
    "ia", "quantum", "robotics",
    # Monde
    "asia", "regulation", "resources",
    # Économie
    "crypto", "macro", "deals",
    # Science
    "energy", "health", "space",
    # Influence (replaces Culture)
    "info", "attention", "persuasion"
]


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
    return {t: 50 for t in DEFAULT_TOPICS}


def get_daily_segment_pool(
    target_date: date,
    include_cache: bool = True,
    max_cache_age: int = MAX_CACHE_AGE_DAYS
) -> list[dict]:
    """
    Retrieve all available segments for a given date.
    
    If include_cache=True, also fetches valid cached segments from previous
    days (up to max_cache_age) for topics that have no fresh content.
    
    Each segment has: id, topic_id, audio_url, duration, relevance_score, created_at.
    """
    try:
        # Get segments for target date
        result = supabase.table("segment_cache") \
            .select("id, content_hash, topic_slug, audio_url, audio_duration, relevance_score, source_title, created_at") \
            .eq("target_date", target_date.isoformat()) \
            .execute()
        
        segments = []
        topics_with_content = set()
        
        for row in result.data or []:
            segments.append({
                "id": row["id"],
                "content_hash": row["content_hash"],
                "topic_id": row["topic_slug"],
                "audio_url": row["audio_url"],
                "duration": row["audio_duration"] or 60,
                "relevance_score": row.get("relevance_score", 0.5),
                "title": row.get("source_title", ""),
                "created_at": row.get("created_at", datetime.now().isoformat())
            })
            topics_with_content.add(row["topic_slug"])
        
        log.info(f"📦 Fresh segments: {len(segments)} for {target_date}")
        
        # If include_cache, fetch cached content for topics without fresh content
        if include_cache:
            missing_topics = set(DEFAULT_TOPICS) - topics_with_content
            
            if missing_topics:
                log.info(f"🔍 Topics without fresh content: {missing_topics}")
                
                cutoff_date = (target_date - timedelta(days=max_cache_age)).isoformat()
                
                for topic in missing_topics:
                    cached_result = supabase.table("segment_cache") \
                        .select("id, content_hash, topic_slug, audio_url, audio_duration, relevance_score, source_title, created_at") \
                        .eq("topic_slug", topic) \
                        .gte("created_at", cutoff_date) \
                        .lt("target_date", target_date.isoformat()) \
                        .order("relevance_score", desc=True) \
                        .limit(3) \
                        .execute()
                    
                    for row in cached_result.data or []:
                        segments.append({
                            "id": row["id"],
                            "content_hash": row["content_hash"],
                            "topic_id": row["topic_slug"],
                            "audio_url": row["audio_url"],
                            "duration": row["audio_duration"] or 60,
                            "relevance_score": row.get("relevance_score", 0.5),
                            "title": row.get("source_title", ""),
                            "created_at": row.get("created_at"),
                            "is_cached": True  # Flag for debugging
                        })
                    
                    if cached_result.data:
                        log.info(f"📦 Added {len(cached_result.data)} cached segments for '{topic}'")
        
        # Filter out expired content
        segments = filter_expired_content(segments, max_cache_age)
        
        log.info(f"📦 Total segment pool: {len(segments)} segments")
        return segments
        
    except Exception as e:
        log.error(f"Failed to fetch segment pool: {e}")
        return []


def calculate_weighted_score(
    segment: dict,
    user_weights: dict[str, int],
    reference_date: Optional[date] = None
) -> float:
    """
    Calculate final score for a segment with age decay.
    
    Formula: Final_Score = (Relevance * Weight/100) * (1 / (1 + Age_in_days))
    
    This ensures:
    - A news from today at 80% beats a 3-day-old news at 80%
    - User preferences are respected
    - Content quality matters
    """
    if reference_date is None:
        reference_date = date.today()
    
    topic_id = segment["topic_id"]
    user_weight = user_weights.get(topic_id, 50)
    relevance = segment.get("relevance_score", 0.5)
    created_at = segment.get("created_at", datetime.now().isoformat())
    
    # Parse created_at if string
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except:
            created_at = datetime.now()
    
    return calculate_final_score(
        relevance_score=relevance,
        user_weight=user_weight,
        created_at=created_at,
        reference_date=reference_date
    )


def select_wildcard(segments: list[dict], user_weights: dict[str, int]) -> Optional[dict]:
    """
    Select a wildcard segment from topics the user has set to 0 (ignored).
    Returns the segment with the highest raw relevance_score among ignored topics.
    
    Wildcard = "Surprise" segment to break filter bubble.
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
    
    # Select the one with highest raw relevance (freshness matters less for surprise)
    wildcard = max(wildcard_candidates, key=lambda s: s.get("relevance_score", 0))
    log.info(f"🎲 Wildcard selected: {wildcard['title'][:50]} (topic: {wildcard['topic_id']}, relevance: {wildcard['relevance_score']:.2f})")
    
    return wildcard


def get_daily_playlist(
    user_id: str,
    target_date: Optional[date] = None,
    target_count: int = 15
) -> list[dict]:
    """
    Main algorithm: Select optimal playlist using "14+1" logic with age decay.
    
    1. Fetch segments (fresh + valid cache)
    2. Calculate weighted scores with age decay
    3. Select top 14 by weighted score
    4. Add wildcard from ignored topics (if any)
    5. Insert wildcard at random position (5-12)
    6. Return ordered list of 15 segments
    
    Age Decay Formula: Final_Score = (Relevance * Weight) * (1 / (1 + Age_days))
    - Today's news (age=0): 100% score
    - Yesterday (age=1): 50% score
    - 3 days ago: 25% score
    - 7 days ago: 12.5% score (then expires)
    
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
    
    # 1. Get user weights and segment pool (including cache)
    user_weights = get_user_signal_weights(user_id)
    segments = get_daily_segment_pool(target_date, include_cache=True)
    
    if not segments:
        log.warning("❌ No segments available in pool")
        return []
    
    # Handle case where user has all weights at 0 (fallback to top by relevance)
    all_zero = all(w == 0 for w in user_weights.values())
    if all_zero:
        log.warning("⚠️ All weights are 0, falling back to top by relevance")
        segments.sort(key=lambda s: s.get("relevance_score", 0), reverse=True)
        return segments[:target_count]
    
    # 2. Calculate weighted scores WITH AGE DECAY
    for segment in segments:
        segment["final_score"] = calculate_weighted_score(segment, user_weights, target_date)
        
        # Log score breakdown for debugging
        age_decay = calculate_age_decay(
            segment.get("created_at", datetime.now().isoformat()),
            target_date
        )
        log.debug(
            f"Score: {segment['title'][:30]} = "
            f"{segment.get('relevance_score', 0.5):.2f} * "
            f"{user_weights.get(segment['topic_id'], 50)/100:.2f} * "
            f"{age_decay:.2f} = {segment['final_score']:.3f}"
        )
    
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
    cached_count = 0
    for s in playlist:
        topic = s["topic_id"]
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        if s.get("is_cached"):
            cached_count += 1
    
    log.info(f"📊 Topic distribution: {dict(sorted(topic_counts.items(), key=lambda x: -x[1]))}")
    if cached_count > 0:
        log.info(f"📦 Includes {cached_count} segments from cache")
    
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
