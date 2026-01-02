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
from cluster_pipeline import (
    embed_articles,
    get_embeddings_batch,
    EMBEDDING_MODEL
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
    Fetch articles from content_queue (DB) - NOT from RSS directly.
    
    The content_queue should be filled by the Fill Queue cron job.
    This ensures we use high-quality, pre-fetched articles instead of
    falling back to Bing backup.
    
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
        "queue_articles": 0,
        "total_articles": 0,
        "source": "content_queue"
    }
    
    try:
        # Determine which topics to fetch
        topics_enabled = params.get("topics_enabled", DEFAULT_PARAMS["topics_enabled"])
        
        if topics:
            # Use provided list, but filter by enabled
            fetch_topics = [t for t in topics if topics_enabled.get(t, False)]
        else:
            # All enabled topics
            fetch_topics = [t for t, enabled in topics_enabled.items() if enabled]
        
        stats["topics_requested"] = len(fetch_topics)
        
        # ========== READ FROM CONTENT_QUEUE ==========
        # Get articles from the last N days
        content_queue_days = params.get("content_queue_days", 3)
        cutoff_date = (datetime.now() - timedelta(days=content_queue_days)).isoformat()
        
        # Query content_queue for pending articles
        result = supabase.table("content_queue") \
            .select("*") \
            .eq("status", "pending") \
            .gte("created_at", cutoff_date) \
            .execute()
        
        queue_articles = result.data or []
        log.info(f"📦 Found {len(queue_articles)} articles in content_queue")
        
        # Track articles per topic
        articles_by_topic = {t: [] for t in fetch_topics}
        
        for art in queue_articles:
            topic = art.get("keyword", art.get("topic", "general")).lower()
            
            # Skip if topic not in our fetch list
            if topic not in fetch_topics:
                exclusions.append({
                    "type": "topic_not_enabled",
                    "title": art.get("title", "")[:50],
                    "topic": topic,
                    "reason": f"Topic '{topic}' not in enabled topics"
                })
                continue
            
            article = {
                "id": art.get("id"),
                "url": art.get("url", ""),
                "title": art.get("title", ""),
                "source_type": art.get("source_type", "queue"),
                "source_name": art.get("source_name", art.get("source", "Unknown")),
                "source_country": art.get("source_country", "FR"),
                "topic": topic,
                "keyword": topic,
                "description": art.get("description", ""),
                "content": art.get("processed_content", art.get("content", "")),
                "published": art.get("published_at", art.get("created_at", "")),
                "fetched_at": art.get("created_at", datetime.now().isoformat()),
                "source_score": art.get("source_score", 50)
            }
            articles.append(article)
            articles_by_topic[topic].append(article)
            stats["queue_articles"] += 1
        
        # Count topics that got articles
        stats["topics_fetched"] = sum(1 for t in fetch_topics if articles_by_topic.get(t))
        stats["total_articles"] = len(articles)
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        
        # Add per-topic stats
        stats["by_topic"] = {
            topic: len(arts) for topic, arts in articles_by_topic.items()
        }
        
        # Warn if queue is empty
        if len(articles) == 0:
            log.warning("⚠️ content_queue is empty! Run 'Fill Queue' first.")
            exclusions.append({
                "type": "empty_queue",
                "reason": "No articles in content_queue. Click 'Fill Queue' button to fetch articles from RSS sources."
            })
        
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
    Cluster articles using OpenAI embeddings + DBSCAN.
    
    Uses the same embedding approach as production (cluster_pipeline.py)
    for high-quality semantic clustering.
    
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
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import normalize
    import numpy as np
    
    start_time = datetime.now()
    clusters = []
    exclusions = []
    stats = {
        "input_articles": len(articles),
        "clusters_formed": 0,
        "articles_clustered": 0,
        "articles_excluded": 0,
        "embedding_model": EMBEDDING_MODEL,
        "method": "OpenAI embeddings + DBSCAN"
    }
    
    min_cluster_size = params.get("min_cluster_size", 3)
    
    try:
        if len(articles) < min_cluster_size:
            log.warning(f"⚠️ Too few articles ({len(articles)}) for clustering")
            for art in articles:
                exclusions.append({
                    "type": "insufficient_articles",
                    "article": art.get("title", "")[:50],
                    "reason": f"Only {len(articles)} article(s), need at least {min_cluster_size}"
                })
            stats["articles_excluded"] = len(articles)
            stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
            return {"clusters": [], "exclusions": exclusions, "stats": stats}
        
        # ========== STEP 1: EMBED ARTICLES ==========
        log.info(f"📊 Embedding {len(articles)} articles with OpenAI...")
        
        # Build text for embedding: description + content (NO title, NO source name)
        texts = []
        for article in articles:
            description = article.get("description", "")
            content = article.get("content", article.get("processed_content", ""))
            # Use description + content, limited to 1000 chars
            text = f"{description} {content}".strip()[:1000]
            if not text:
                # Fallback to title if no content
                text = article.get("title", "No content")
            texts.append(text)
        
        embeddings = get_embeddings_batch(texts)
        
        # Attach embeddings to articles
        for article, embedding in zip(articles, embeddings):
            article["embedding"] = embedding
        
        stats["embeddings_generated"] = len(embeddings)
        log.info(f"✅ Generated {len(embeddings)} embeddings")
        
        # ========== STEP 2: CLUSTER WITH DBSCAN ==========
        log.info(f"🔬 Clustering with DBSCAN (min_cluster_size={min_cluster_size})...")
        
        embeddings_array = np.array(embeddings)
        embeddings_normalized = normalize(embeddings_array)
        
        # ========== DIAGNOSTIC: Similarity distribution ==========
        from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
        
        # Calculate pairwise similarities (only upper triangle to save memory)
        n_articles = len(embeddings_normalized)
        similarities = []
        top_pairs = []  # Store top similar pairs for inspection
        
        for i in range(n_articles):
            for j in range(i + 1, n_articles):
                sim = float(np.dot(embeddings_normalized[i], embeddings_normalized[j]))
                similarities.append(sim)
                if sim > 0.5:  # Track high similarity pairs
                    top_pairs.append({
                        "similarity": round(sim, 3),
                        "article_1": articles[i].get("title", "")[:50],
                        "article_2": articles[j].get("title", "")[:50]
                    })
        
        # Log distribution stats
        similarities_arr = np.array(similarities)
        log.info(f"📊 SIMILARITY DISTRIBUTION ({len(similarities)} pairs):")
        log.info(f"   Min: {similarities_arr.min():.3f}")
        log.info(f"   Max: {similarities_arr.max():.3f}")
        log.info(f"   Mean: {similarities_arr.mean():.3f}")
        log.info(f"   Median: {np.median(similarities_arr):.3f}")
        log.info(f"   Std: {similarities_arr.std():.3f}")
        
        # Count pairs above different thresholds
        thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        for thresh in thresholds:
            count = np.sum(similarities_arr >= thresh)
            pct = 100 * count / len(similarities_arr)
            log.info(f"   Pairs with similarity >= {thresh}: {count} ({pct:.1f}%)")
        
        # Log top similar pairs
        top_pairs.sort(key=lambda x: x["similarity"], reverse=True)
        if top_pairs:
            log.info(f"🔝 TOP {min(5, len(top_pairs))} SIMILAR PAIRS:")
            for pair in top_pairs[:5]:
                log.info(f"   {pair['similarity']}: '{pair['article_1']}' <-> '{pair['article_2']}'")
        else:
            log.info("⚠️ NO PAIRS with similarity > 0.5 found!")
        
        # Store in stats for frontend display
        stats["similarity_distribution"] = {
            "min": round(float(similarities_arr.min()), 3),
            "max": round(float(similarities_arr.max()), 3),
            "mean": round(float(similarities_arr.mean()), 3),
            "median": round(float(np.median(similarities_arr)), 3),
            "std": round(float(similarities_arr.std()), 3),
            "pairs_above_0.5": int(np.sum(similarities_arr >= 0.5)),
            "pairs_above_0.6": int(np.sum(similarities_arr >= 0.6)),
            "pairs_above_0.7": int(np.sum(similarities_arr >= 0.7)),
            "total_pairs": len(similarities)
        }
        stats["top_similar_pairs"] = top_pairs[:10]
        # ========== END DIAGNOSTIC ==========
        
        # DBSCAN clustering
        # eps=0.5 means distance < 0.5, i.e. cosine similarity > 0.75 on normalized vectors
        # Note: euclidean distance on normalized vectors: d = sqrt(2 - 2*cos_sim)
        # So eps=0.5 -> cos_sim > 1 - 0.5²/2 = 0.875 (very strict!)
        # eps=0.7 -> cos_sim > 1 - 0.7²/2 = 0.755
        # eps=1.0 -> cos_sim > 1 - 1.0²/2 = 0.5
        clusterer = DBSCAN(
            eps=0.5,
            min_samples=min_cluster_size,
            metric='euclidean',
            n_jobs=-1
        )
        
        labels = clusterer.fit_predict(embeddings_normalized)
        
        # ========== STEP 3: GROUP BY CLUSTER ==========
        cluster_groups = {}
        noise_articles = []
        
        for idx, label in enumerate(labels):
            if label == -1:
                noise_articles.append(articles[idx])
            else:
                if label not in cluster_groups:
                    cluster_groups[label] = []
                cluster_groups[label].append(articles[idx])
        
        # Build cluster objects
        for label, cluster_articles in cluster_groups.items():
            # Determine dominant topic
            topic_counts = {}
            for art in cluster_articles:
                topic = art.get("topic", art.get("keyword", "unknown"))
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
            dominant_topic = max(topic_counts, key=topic_counts.get) if topic_counts else "unknown"
            
            # Get unique sources
            sources = list(set(a.get("source_name", "Unknown") for a in cluster_articles))
            
            clusters.append({
                "topic": dominant_topic,
                "cluster_id": f"cluster_{label}",
                "size": len(cluster_articles),
                "articles": cluster_articles,
                "representative_title": cluster_articles[0].get("title", ""),
                "sources": sources,
                "source_diversity": len(sources)
            })
            stats["clusters_formed"] += 1
            stats["articles_clustered"] += len(cluster_articles)
        
        # Handle noise articles
        for art in noise_articles:
            exclusions.append({
                "type": "no_cluster",
                "article": art.get("title", "")[:50],
                "topic": art.get("topic", "unknown"),
                "reason": "Article did not fit any cluster (too unique or isolated)"
            })
            stats["articles_excluded"] += 1
        
        # Sort clusters by size (largest first)
        clusters.sort(key=lambda c: c["size"], reverse=True)
        
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        stats["noise_articles"] = len(noise_articles)
        
        log.info(f"✅ Clustering complete: {len(clusters)} clusters, {len(noise_articles)} noise articles")
        
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
