"""
Pipeline Lab - Sandbox environment for testing the content pipeline.

V17: Allows testing fetcher → clustering → selection with custom parameters
without affecting production data.

Each step returns:
- results: The actual output
- exclusions: Items that were filtered out with reasons
- stats: Metrics about the step
"""

import os
from datetime import datetime, timedelta
from typing import Any
import structlog

from db import supabase
from sourcing import (
    GSheetSourceLibrary,
    fetch_rss_feed,
    fetch_bing_news
)

log = structlog.get_logger()


# ============================================
# DEFAULT PARAMETERS (V17)
# ============================================

DEFAULT_PARAMS = {
    # Segment counts
    "flash_segment_count": 4,
    "digest_segment_count": 8,
    
    # Clustering
    "min_cluster_size": 3,
    "min_articles_fallback": 5,  # If no cluster, need at least this many articles
    
    # Time windows
    "content_queue_days": 3,
    "maturation_window_hours": 72,
    "segment_cache_days": 1,
    
    # Duration targets (seconds)
    "flash_duration_min": 45,
    "flash_duration_max": 60,
    "digest_duration_min": 90,
    "digest_duration_max": 120,
    
    # Topics (all enabled by default)
    "topics_enabled": {
        "asia": True,
        "attention": True,
        "crypto": True,
        "cyber": True,
        "deals": True,
        "deep_tech": True,
        "energy": True,
        "health": True,
        "ia": True,
        "info": True,
        "macro": True,
        "persuasion": True,
        "regulation": True,
        "resources": True,
        "space": True
    },
    
    # Bing backup threshold
    "bing_backup_threshold": 5,  # Topics with < N articles get Bing backup
    
    # RSS limits
    "max_articles_per_rss": 10,
    "rss_timeout_seconds": 10
}


def get_default_params() -> dict:
    """Return default pipeline parameters."""
    return DEFAULT_PARAMS.copy()


# ============================================
# SANDBOX FETCH
# ============================================

def sandbox_fetch(params: dict, topics: list[str] = None) -> dict:
    """
    Fetch articles in sandbox mode (not saved to DB).
    
    Args:
        params: Custom parameters
        topics: List of topics to fetch (None = all enabled)
    
    Returns:
        {
            "articles": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    start_time = datetime.now()
    articles = []
    exclusions = []
    stats = {
        "topics_requested": 0,
        "topics_fetched": 0,
        "gsheet_articles": 0,
        "bing_articles": 0,
        "total_articles": 0,
        "sources_failed": 0
    }
    
    try:
        # Load GSheet sources
        library = GSheetSourceLibrary()
        all_sources = library.get_all_sources()
        
        # Determine which topics to fetch
        topics_enabled = params.get("topics_enabled", DEFAULT_PARAMS["topics_enabled"])
        
        if topics:
            # Use provided list, but filter by enabled
            fetch_topics = [t for t in topics if topics_enabled.get(t, False)]
        else:
            # All enabled topics
            fetch_topics = [t for t, enabled in topics_enabled.items() if enabled]
        
        stats["topics_requested"] = len(fetch_topics)
        
        # Track articles per topic for Bing backup decision
        articles_by_topic = {t: [] for t in fetch_topics}
        
        # ========== LEVEL 1: GSheet RSS ==========
        for source in all_sources:
            topic = source.get("topic", "").lower()
            
            if topic not in fetch_topics:
                continue
            
            rss_url = source.get("rss_url", "")
            if not rss_url:
                continue
            
            try:
                feed_articles = fetch_rss_feed(
                    rss_url,
                    max_items=params.get("max_articles_per_rss", 10),
                    timeout=params.get("rss_timeout_seconds", 10)
                )
                
                for art in feed_articles:
                    article = {
                        "url": art.get("url", art.get("link", "")),
                        "title": art.get("title", ""),
                        "source_type": "gsheet_rss",
                        "source_name": source.get("name", "Unknown"),
                        "source_country": source.get("origin", "FR"),
                        "topic": topic,
                        "published": art.get("published", ""),
                        "fetched_at": datetime.now().isoformat()
                    }
                    articles.append(article)
                    articles_by_topic[topic].append(article)
                    stats["gsheet_articles"] += 1
                    
            except Exception as e:
                stats["sources_failed"] += 1
                exclusions.append({
                    "type": "source_failed",
                    "source": source.get("name", rss_url),
                    "topic": topic,
                    "reason": str(e)
                })
        
        # ========== LEVEL 2: Bing Backup ==========
        bing_threshold = params.get("bing_backup_threshold", 5)
        
        for topic in fetch_topics:
            topic_count = len(articles_by_topic.get(topic, []))
            
            if topic_count < bing_threshold:
                try:
                    # Search Bing for this topic
                    bing_results = fetch_bing_news(
                        query=topic,
                        market="FR",
                        max_items=10
                    )
                    
                    for art in bing_results:
                        article = {
                            "url": art.get("url", ""),
                            "title": art.get("name", art.get("title", "")),
                            "source_type": "bing_news",
                            "source_name": art.get("provider", [{}])[0].get("name", "Bing News") if art.get("provider") else "Bing News",
                            "source_country": "FR",
                            "topic": topic,
                            "published": art.get("datePublished", ""),
                            "fetched_at": datetime.now().isoformat()
                        }
                        articles.append(article)
                        articles_by_topic[topic].append(article)
                        stats["bing_articles"] += 1
                        
                except Exception as e:
                    exclusions.append({
                        "type": "bing_backup_failed",
                        "topic": topic,
                        "reason": str(e)
                    })
        
        # Count topics that got articles
        stats["topics_fetched"] = sum(1 for t in fetch_topics if articles_by_topic.get(t))
        stats["total_articles"] = len(articles)
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        
        # Add per-topic stats
        stats["by_topic"] = {
            topic: len(arts) for topic, arts in articles_by_topic.items()
        }
        
    except Exception as e:
        log.error("Sandbox fetch error", error=str(e))
        exclusions.append({
            "type": "fatal_error",
            "reason": str(e)
        })
    
    return {
        "articles": articles,
        "exclusions": exclusions,
        "stats": stats
    }


# ============================================
# SANDBOX CLUSTER
# ============================================

def sandbox_cluster(articles: list[dict], params: dict) -> dict:
    """
    Cluster articles in sandbox mode.
    
    Args:
        articles: List of articles from fetch step
        params: Custom parameters
    
    Returns:
        {
            "clusters": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    from cluster_pipeline import cluster_articles_by_topic, extract_clusters
    
    start_time = datetime.now()
    clusters = []
    exclusions = []
    stats = {
        "input_articles": len(articles),
        "clusters_formed": 0,
        "articles_clustered": 0,
        "articles_excluded": 0
    }
    
    min_cluster_size = params.get("min_cluster_size", 3)
    
    try:
        # Group articles by topic
        by_topic = {}
        for art in articles:
            topic = art.get("topic", "unknown")
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(art)
        
        # Cluster each topic
        for topic, topic_articles in by_topic.items():
            if len(topic_articles) < 2:
                # Can't cluster single articles
                for art in topic_articles:
                    exclusions.append({
                        "type": "insufficient_for_clustering",
                        "article": art.get("title", "")[:50],
                        "topic": topic,
                        "reason": f"Only {len(topic_articles)} article(s) in topic, need at least 2"
                    })
                stats["articles_excluded"] += len(topic_articles)
                continue
            
            # Use existing clustering logic
            try:
                # Simple clustering by title similarity
                topic_clusters = cluster_by_similarity(topic_articles, min_cluster_size)
                
                for cluster in topic_clusters:
                    if len(cluster["articles"]) >= min_cluster_size:
                        clusters.append({
                            "topic": topic,
                            "cluster_id": f"{topic}_{len(clusters)}",
                            "size": len(cluster["articles"]),
                            "articles": cluster["articles"],
                            "representative_title": cluster["articles"][0].get("title", ""),
                            "sources": list(set(a.get("source_name", "") for a in cluster["articles"]))
                        })
                        stats["clusters_formed"] += 1
                        stats["articles_clustered"] += len(cluster["articles"])
                    else:
                        # Cluster too small
                        for art in cluster["articles"]:
                            exclusions.append({
                                "type": "cluster_too_small",
                                "article": art.get("title", "")[:50],
                                "topic": topic,
                                "reason": f"Cluster has {len(cluster['articles'])} articles, need {min_cluster_size}"
                            })
                        stats["articles_excluded"] += len(cluster["articles"])
                        
            except Exception as e:
                exclusions.append({
                    "type": "clustering_error",
                    "topic": topic,
                    "reason": str(e)
                })
                stats["articles_excluded"] += len(topic_articles)
        
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        
    except Exception as e:
        log.error("Sandbox cluster error", error=str(e))
        exclusions.append({
            "type": "fatal_error",
            "reason": str(e)
        })
    
    return {
        "clusters": clusters,
        "exclusions": exclusions,
        "stats": stats
    }


def cluster_by_similarity(articles: list[dict], min_size: int) -> list[dict]:
    """
    Simple clustering by title word overlap.
    Returns list of {"articles": [...]} dicts.
    """
    if not articles:
        return []
    
    # Simple approach: group by significant word overlap
    import re
    
    def get_words(title: str) -> set:
        # Extract significant words (>3 chars, lowercase)
        words = re.findall(r'\b\w{4,}\b', title.lower())
        # Remove common words
        stopwords = {'dans', 'pour', 'avec', 'cette', 'sont', 'plus', 'leur', 'mais', 'être', 'avoir', 'fait', 'comme', 'tout', 'après', 'entre'}
        return set(w for w in words if w not in stopwords)
    
    # Calculate word sets for each article
    article_words = [(art, get_words(art.get("title", ""))) for art in articles]
    
    # Greedy clustering
    used = set()
    clusters = []
    
    for i, (art, words) in enumerate(article_words):
        if i in used:
            continue
        
        # Start new cluster
        cluster_articles = [art]
        used.add(i)
        
        # Find similar articles
        for j, (other_art, other_words) in enumerate(article_words):
            if j in used:
                continue
            
            # Check overlap
            if words and other_words:
                overlap = len(words & other_words)
                min_len = min(len(words), len(other_words))
                if min_len > 0 and overlap / min_len >= 0.3:  # 30% overlap threshold
                    cluster_articles.append(other_art)
                    used.add(j)
        
        clusters.append({"articles": cluster_articles})
    
    return clusters


# ============================================
# SANDBOX SELECT
# ============================================

def sandbox_select(clusters: list[dict], articles: list[dict], params: dict, format_type: str = "flash") -> dict:
    """
    Select content for podcast in sandbox mode.
    
    Args:
        clusters: List of clusters from clustering step
        articles: Original articles (for fallback if no clusters)
        params: Custom parameters
        format_type: "flash" or "digest"
    
    Returns:
        {
            "segments": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    start_time = datetime.now()
    segments = []
    exclusions = []
    
    # Get format-specific params
    if format_type == "flash":
        target_segments = params.get("flash_segment_count", 4)
        duration_min = params.get("flash_duration_min", 45)
        duration_max = params.get("flash_duration_max", 60)
    else:
        target_segments = params.get("digest_segment_count", 8)
        duration_min = params.get("digest_duration_min", 90)
        duration_max = params.get("digest_duration_max", 120)
    
    min_cluster_size = params.get("min_cluster_size", 3)
    min_articles_fallback = params.get("min_articles_fallback", 5)
    
    stats = {
        "format": format_type,
        "target_segments": target_segments,
        "input_clusters": len(clusters),
        "segments_created": 0,
        "topics_covered": set()
    }
    
    try:
        # Priority 1: Topics with valid clusters
        topics_with_clusters = {}
        for cluster in clusters:
            topic = cluster.get("topic", "unknown")
            if cluster.get("size", 0) >= min_cluster_size:
                if topic not in topics_with_clusters:
                    topics_with_clusters[topic] = []
                topics_with_clusters[topic].append(cluster)
        
        # Priority 2: Topics with enough articles (fallback)
        articles_by_topic = {}
        for art in articles:
            topic = art.get("topic", "unknown")
            if topic not in articles_by_topic:
                articles_by_topic[topic] = []
            articles_by_topic[topic].append(art)
        
        topics_fallback = {
            topic: arts for topic, arts in articles_by_topic.items()
            if topic not in topics_with_clusters and len(arts) >= min_articles_fallback
        }
        
        # Build segments
        selected_topics = []
        
        # First, add topics with clusters
        for topic, topic_clusters in topics_with_clusters.items():
            if len(segments) >= target_segments:
                break
            
            # Take best cluster (largest)
            best_cluster = max(topic_clusters, key=lambda c: c.get("size", 0))
            
            segments.append({
                "topic": topic,
                "type": "cluster",
                "cluster_size": best_cluster.get("size", 0),
                "articles": best_cluster.get("articles", []),
                "representative_title": best_cluster.get("representative_title", ""),
                "duration_target": (duration_min + duration_max) // 2
            })
            stats["segments_created"] += 1
            stats["topics_covered"].add(topic)
            selected_topics.append(topic)
        
        # Then, add fallback topics
        for topic, arts in topics_fallback.items():
            if len(segments) >= target_segments:
                break
            
            if topic in selected_topics:
                continue
            
            segments.append({
                "topic": topic,
                "type": "fallback",
                "cluster_size": 0,
                "articles": arts[:5],  # Max 5 articles for fallback
                "representative_title": arts[0].get("title", "") if arts else "",
                "duration_target": (duration_min + duration_max) // 2
            })
            stats["segments_created"] += 1
            stats["topics_covered"].add(topic)
            selected_topics.append(topic)
        
        # Record exclusions
        for topic, topic_clusters in topics_with_clusters.items():
            if topic not in selected_topics:
                for cluster in topic_clusters:
                    exclusions.append({
                        "type": "segment_limit_reached",
                        "topic": topic,
                        "cluster_size": cluster.get("size", 0),
                        "reason": f"Already have {target_segments} segments"
                    })
        
        for topic, arts in articles_by_topic.items():
            if topic not in selected_topics and topic not in topics_with_clusters:
                if len(arts) < min_articles_fallback:
                    exclusions.append({
                        "type": "insufficient_articles",
                        "topic": topic,
                        "article_count": len(arts),
                        "reason": f"Has {len(arts)} articles, need {min_articles_fallback} for fallback"
                    })
        
        stats["topics_covered"] = list(stats["topics_covered"])
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        
    except Exception as e:
        log.error("Sandbox select error", error=str(e))
        exclusions.append({
            "type": "fatal_error",
            "reason": str(e)
        })
    
    return {
        "segments": segments,
        "exclusions": exclusions,
        "stats": stats
    }


# ============================================
# FULL PIPELINE (convenience)
# ============================================

def sandbox_full_pipeline(params: dict, format_type: str = "flash", topics: list[str] = None) -> dict:
    """
    Run full pipeline in sandbox mode.
    
    Returns:
        {
            "fetch": {...},
            "cluster": {...},
            "select": {...},
            "final_segments": [...],
            "total_duration_seconds": float
        }
    """
    start_time = datetime.now()
    
    # Step 1: Fetch
    fetch_result = sandbox_fetch(params, topics)
    
    # Step 2: Cluster
    cluster_result = sandbox_cluster(fetch_result["articles"], params)
    
    # Step 3: Select
    select_result = sandbox_select(
        cluster_result["clusters"],
        fetch_result["articles"],
        params,
        format_type
    )
    
    return {
        "fetch": fetch_result,
        "cluster": cluster_result,
        "select": select_result,
        "final_segments": select_result["segments"],
        "total_duration_seconds": (datetime.now() - start_time).total_seconds()
    }
