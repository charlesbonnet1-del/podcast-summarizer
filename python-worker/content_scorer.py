"""
Keernel Content Scorer - Quality & Freshness Scoring System

Evaluates content relevance using:
1. Recency Score: Is it tied to recent events (< 7 days)?
2. Connectivity Score: Does it link ideas to actions?
3. Age Decay: Fresh content beats stale content

Formula: Final_Score = (Relevance * Weight) * (1 / (1 + Age_in_days))
"""

import structlog
from datetime import datetime, date, timedelta
from typing import Optional
from openai import OpenAI
import os

log = structlog.get_logger()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Constants
MAX_CACHE_AGE_DAYS = 7  # Maximum days to keep content in cache
RECENCY_WINDOW_DAYS = 7  # Window for "recent event" evaluation


def calculate_age_decay(created_at: datetime, reference_date: Optional[date] = None) -> float:
    """
    Calculate age decay multiplier.
    
    Formula: decay = 1 / (1 + age_in_days)
    
    Examples:
        - Today (0 days): 1.0
        - Yesterday (1 day): 0.5
        - 2 days ago: 0.33
        - 3 days ago: 0.25
        - 7 days ago: 0.125
    
    This ensures fresh news always beats stale news at equal relevance.
    """
    if reference_date is None:
        reference_date = date.today()
    
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    
    age_days = (reference_date - created_at.date()).days
    age_days = max(0, age_days)  # No negative ages
    
    decay = 1 / (1 + age_days)
    
    log.debug(f"Age decay: {age_days} days old → {decay:.3f} multiplier")
    return decay


def is_content_expired(created_at: datetime, max_age_days: int = MAX_CACHE_AGE_DAYS) -> bool:
    """
    Check if content has exceeded maximum cache age.
    Content older than max_age_days should be purged.
    """
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    
    age_days = (date.today() - created_at.date()).days
    return age_days > max_age_days


def evaluate_content_quality(
    title: str,
    summary: str,
    topic: str,
    source_date: Optional[str] = None
) -> dict:
    """
    Use AI to evaluate content quality based on:
    
    1. Recency Score (0-1): Is it tied to a recent event?
       Question: "En quoi cette réflexion éclaire-t-elle un événement des 7 derniers jours?"
    
    2. Connectivity Score (0-1): Does it link ideas to actions?
       Question: "L'article fait-il un lien entre une idée et une action concrète?"
    
    Returns:
        {
            "recency_score": float,
            "connectivity_score": float,
            "quality_score": float,  # Combined score
            "reasoning": str
        }
    """
    
    prompt = f"""Tu es un éditeur de podcast d'actualité tech/business. Évalue cet article.

ARTICLE:
Titre: {title}
Résumé: {summary}
Topic: {topic}
Date source: {source_date or "Non spécifiée"}

CRITÈRES D'ÉVALUATION:

1. RÉCENCE (0-100): L'info est-elle liée à un fait des 7 derniers jours?
   - 80-100: Annonce majeure, événement breaking
   - 50-79: Développement récent d'une tendance
   - 20-49: Contexte utile mais pas d'actualité chaude
   - 0-19: Article "froid", réflexion intemporelle

2. CONNECTIVITÉ (0-100): L'article relie-t-il une idée à une action concrète?
   - 80-100: Lien clair idée → impact marché/régulation/innovation
   - 50-79: Implications évoquées mais pas détaillées
   - 20-49: Principalement théorique/conceptuel
   - 0-19: Aucun lien avec l'actualité ou l'action

Réponds UNIQUEMENT en JSON:
{{
  "recency_score": <0-100>,
  "connectivity_score": <0-100>,
  "reasoning": "<1 phrase justifiant les scores>"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        
        recency = result.get("recency_score", 50) / 100
        connectivity = result.get("connectivity_score", 50) / 100
        
        # Combined quality score (weighted average)
        quality = (recency * 0.6) + (connectivity * 0.4)
        
        log.info(f"📊 Content scored: recency={recency:.2f}, connectivity={connectivity:.2f}, quality={quality:.2f}")
        
        return {
            "recency_score": recency,
            "connectivity_score": connectivity,
            "quality_score": quality,
            "reasoning": result.get("reasoning", "")
        }
        
    except Exception as e:
        log.error(f"Content quality evaluation failed: {e}")
        # Default to medium scores on failure
        return {
            "recency_score": 0.5,
            "connectivity_score": 0.5,
            "quality_score": 0.5,
            "reasoning": "Evaluation failed, using defaults"
        }


def calculate_final_score(
    relevance_score: float,
    user_weight: int,
    created_at: datetime,
    reference_date: Optional[date] = None
) -> float:
    """
    Calculate final score with age decay.
    
    Formula: Final_Score = (Relevance * Weight/100) * Age_Decay
    
    Where Age_Decay = 1 / (1 + age_in_days)
    
    This ensures:
    - User preferences (weight) are respected
    - Content quality (relevance) matters
    - Fresh content beats stale content at equal scores
    
    Example:
        - News from today at 80% relevance, 80% weight:
          (0.8 * 0.8) * 1.0 = 0.64
        
        - News from 3 days ago at 80% relevance, 80% weight:
          (0.8 * 0.8) * 0.25 = 0.16
        
        Result: Today's news wins!
    """
    age_decay = calculate_age_decay(created_at, reference_date)
    base_score = relevance_score * (user_weight / 100)
    final_score = base_score * age_decay
    
    log.debug(f"Final score: {relevance_score:.2f} * {user_weight/100:.2f} * {age_decay:.2f} = {final_score:.3f}")
    
    return final_score


def filter_expired_content(segments: list[dict], max_age_days: int = MAX_CACHE_AGE_DAYS) -> list[dict]:
    """
    Remove content older than max_age_days from segment list.
    Returns filtered list and logs expired items.
    """
    valid_segments = []
    expired_count = 0
    
    for segment in segments:
        created_at = segment.get("created_at")
        if created_at and is_content_expired(created_at, max_age_days):
            expired_count += 1
            log.debug(f"Expired content removed: {segment.get('title', 'Unknown')[:40]}")
        else:
            valid_segments.append(segment)
    
    if expired_count > 0:
        log.info(f"🗑️ Removed {expired_count} expired segments (>{max_age_days} days old)")
    
    return valid_segments


def score_segment_pool(
    segments: list[dict],
    user_weights: dict[str, int],
    reference_date: Optional[date] = None
) -> list[dict]:
    """
    Score all segments in a pool with age decay applied.
    
    Each segment gets a final_score that accounts for:
    - Base relevance (content quality)
    - User weight (topic preference)
    - Age decay (freshness bonus)
    
    Returns segments sorted by final_score (descending).
    """
    if reference_date is None:
        reference_date = date.today()
    
    # First, filter out expired content
    valid_segments = filter_expired_content(segments)
    
    # Calculate final scores
    for segment in valid_segments:
        topic_id = segment.get("topic_id") or segment.get("topic_slug", "")
        user_weight = user_weights.get(topic_id, 50)
        relevance = segment.get("relevance_score", 0.5)
        created_at = segment.get("created_at", datetime.now())
        
        segment["final_score"] = calculate_final_score(
            relevance_score=relevance,
            user_weight=user_weight,
            created_at=created_at,
            reference_date=reference_date
        )
        
        # Store components for debugging
        segment["score_components"] = {
            "relevance": relevance,
            "weight": user_weight,
            "age_decay": calculate_age_decay(created_at, reference_date)
        }
    
    # Sort by final score
    valid_segments.sort(key=lambda s: s.get("final_score", 0), reverse=True)
    
    log.info(f"✅ Scored {len(valid_segments)} segments with age decay")
    
    return valid_segments


# ============================================
# CACHE MANAGEMENT
# ============================================

def get_cached_segments_by_topic(
    topic_id: str,
    max_age_days: int = MAX_CACHE_AGE_DAYS
) -> list[dict]:
    """
    Retrieve cached segments for a specific topic within validity window.
    Used when a topic hasn't generated content for a while.
    """
    from db import supabase
    
    cutoff_date = (date.today() - timedelta(days=max_age_days)).isoformat()
    
    try:
        result = supabase.table("segment_cache") \
            .select("*") \
            .eq("topic_slug", topic_id) \
            .gte("created_at", cutoff_date) \
            .order("relevance_score", desc=True) \
            .execute()
        
        segments = result.data or []
        log.info(f"📦 Found {len(segments)} cached segments for topic '{topic_id}' (max {max_age_days} days old)")
        return segments
        
    except Exception as e:
        log.error(f"Failed to fetch cached segments: {e}")
        return []


def cleanup_expired_cache(max_age_days: int = MAX_CACHE_AGE_DAYS) -> int:
    """
    Remove expired content from segment cache.
    Should be run daily as part of maintenance.
    
    Returns number of deleted rows.
    """
    from db import supabase
    
    cutoff_date = (date.today() - timedelta(days=max_age_days)).isoformat()
    
    try:
        result = supabase.table("segment_cache") \
            .delete() \
            .lt("created_at", cutoff_date) \
            .execute()
        
        deleted_count = len(result.data) if result.data else 0
        log.info(f"🧹 Cache cleanup: removed {deleted_count} expired segments")
        return deleted_count
        
    except Exception as e:
        log.error(f"Cache cleanup failed: {e}")
        return 0
