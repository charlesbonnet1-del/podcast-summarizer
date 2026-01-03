"""
Keernel Pipeline V2 - B2B Intelligence Platform

Main pipeline orchestrating:
1. FETCH - Get articles from all sources
2. CLASSIFY - LLM classification for generalist sources
3. CLUSTER - Group similar articles (embeddings + DBSCAN)
4. SCORE - Radar + Loupe scoring
5. SELECT - Apply selection rules
6. STORE - Save to database

Run modes:
- full: Complete pipeline
- fetch_only: Just fetch and store raw articles
- cluster_only: Cluster existing articles
- score_only: Score existing clusters
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Optional

import structlog
from dotenv import load_dotenv

# Local imports
from sourcing_v2 import (
    SourceLibrary, 
    fetch_all_sources,
    MVP_TOPICS,
    TIER_AUTHORITY,
    TIER_GENERALIST,
    TIER_CORPORATE,
)
from classifier import (
    classify_articles_batch,
    filter_classified_articles,
)
from scoring import (
    score_articles,
    score_clusters,
    select_valid_clusters,
    select_best_articles_per_topic,
    get_scoring_summary,
)

load_dotenv()
log = structlog.get_logger()


# ============================================
# CONFIGURATION
# ============================================

# Pipeline settings
MAX_ARTICLES_PER_SOURCE = 10
MAX_CLUSTERS_PER_TOPIC = 5
MAX_ARTICLES_PER_CLUSTER = 3

# Embedding settings
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Clustering settings (DBSCAN)
DBSCAN_EPS = 0.65  # Cosine similarity > 0.35 to cluster
DBSCAN_MIN_SAMPLES = 2


# ============================================
# DATABASE HELPERS
# ============================================

def get_supabase_client():
    """Initialize Supabase client."""
    try:
        from supabase import create_client
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            log.warning("Supabase credentials not set")
            return None
        
        return create_client(url, key)
    except Exception as e:
        log.error("Failed to init Supabase", error=str(e))
        return None


def store_articles(articles: list[dict], table: str = "articles") -> int:
    """
    Store articles in Supabase.
    
    Returns number of articles stored.
    """
    client = get_supabase_client()
    if not client:
        return 0
    
    stored = 0
    
    for article in articles:
        try:
            # Prepare record
            record = {
                "url": article["url"],
                "title": article["title"],
                "description": article.get("description", ""),
                "source_name": article.get("source_name", "unknown"),
                "source_tier": article.get("source_tier", "generalist"),
                "topic": article.get("topic") or article.get("classified_topic", "unknown"),
                "classified_topic": article.get("classified_topic"),
                "relevance_score": article.get("relevance_score", 0),
                "published_at": article.get("published_at"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "language": article.get("language", "en"),
                "cluster_id": article.get("cluster_id"),
                "embedding": article.get("embedding"),
            }
            
            # Upsert by URL
            client.table(table).upsert(
                record,
                on_conflict="url"
            ).execute()
            
            stored += 1
            
        except Exception as e:
            log.warning("Failed to store article", url=article.get("url", "")[:50], error=str(e))
    
    log.info(f"💾 Stored {stored}/{len(articles)} articles")
    return stored


def get_recent_articles(
    topics: list[str] = None,
    hours: int = 72,
    table: str = "articles"
) -> list[dict]:
    """Get recent articles from database."""
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        query = client.table(table).select("*")
        
        # Filter by time
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = query.gte("fetched_at", cutoff.isoformat())
        
        # Filter by topics
        if topics:
            query = query.in_("topic", topics)
        
        result = query.order("fetched_at", desc=True).limit(1000).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        log.error("Failed to get articles", error=str(e))
        return []


# ============================================
# EMBEDDING HELPERS
# ============================================

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Get embeddings for texts using OpenAI.
    
    Returns list of embedding vectors.
    """
    import httpx
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY not set")
        return []
    
    try:
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": texts,
                "dimensions": EMBEDDING_DIMENSIONS
            },
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        embeddings = [item["embedding"] for item in result["data"]]
        
        return embeddings
        
    except Exception as e:
        log.error("Embedding request failed", error=str(e))
        return []


def add_embeddings_to_articles(articles: list[dict]) -> list[dict]:
    """Add embeddings to articles."""
    # Prepare texts for embedding
    texts = []
    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}"
        texts.append(text[:1000])  # Limit length
    
    if not texts:
        return articles
    
    # Batch embeddings (max 100 at a time)
    all_embeddings = []
    batch_size = 100
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        embeddings = get_embeddings(batch)
        all_embeddings.extend(embeddings)
        time.sleep(0.1)  # Rate limiting
    
    # Add to articles
    for i, article in enumerate(articles):
        if i < len(all_embeddings):
            article["embedding"] = all_embeddings[i]
    
    log.info(f"🧠 Added embeddings to {len(all_embeddings)} articles")
    
    return articles


# ============================================
# CLUSTERING
# ============================================

def cluster_articles(articles: list[dict]) -> dict[int, list[dict]]:
    """
    Cluster articles using DBSCAN on embeddings.
    
    Returns dict mapping cluster_id to list of articles.
    Cluster -1 is noise (unclustered).
    """
    import numpy as np
    from sklearn.cluster import DBSCAN
    from sklearn.metrics.pairwise import cosine_distances
    
    # Filter articles with embeddings
    with_embeddings = [a for a in articles if a.get("embedding")]
    
    if len(with_embeddings) < 2:
        log.warning("Not enough articles with embeddings for clustering")
        return {-1: articles}
    
    # Build embedding matrix
    embeddings = np.array([a["embedding"] for a in with_embeddings])
    
    # Compute cosine distance matrix
    distances = cosine_distances(embeddings)
    
    # Run DBSCAN
    clustering = DBSCAN(
        eps=DBSCAN_EPS,
        min_samples=DBSCAN_MIN_SAMPLES,
        metric="precomputed"
    ).fit(distances)
    
    # Group by cluster
    clusters = {}
    for i, label in enumerate(clustering.labels_):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(with_embeddings[i])
        with_embeddings[i]["cluster_id"] = int(label)
    
    # Add articles without embeddings to noise
    without_embeddings = [a for a in articles if not a.get("embedding")]
    if without_embeddings:
        if -1 not in clusters:
            clusters[-1] = []
        clusters[-1].extend(without_embeddings)
    
    # Log stats
    n_clusters = len([k for k in clusters.keys() if k != -1])
    n_noise = len(clusters.get(-1, []))
    
    log.info(f"🔗 Clustering: {n_clusters} clusters, {n_noise} noise articles")
    
    return clusters


# ============================================
# MAIN PIPELINE
# ============================================

def run_pipeline(
    topics: list[str] = None,
    mvp_only: bool = True,
    do_fetch: bool = True,
    do_classify: bool = True,
    do_cluster: bool = True,
    do_score: bool = True,
    do_store: bool = True,
) -> dict:
    """
    Run the full pipeline.
    
    Args:
        topics: Topics to process (default: MVP_TOPICS)
        mvp_only: Only use priority=1 sources
        do_fetch: Fetch new articles
        do_classify: Run LLM classification
        do_cluster: Run clustering
        do_score: Run scoring
        do_store: Store to database
    
    Returns:
        Pipeline results dict
    """
    topics = topics or MVP_TOPICS
    
    log.info(f"🚀 Starting pipeline for topics: {topics}")
    start_time = time.time()
    
    results = {
        "topics": topics,
        "articles_fetched": 0,
        "articles_classified": 0,
        "articles_clustered": 0,
        "articles_selected": 0,
        "clusters_valid": 0,
        "duration_seconds": 0,
    }
    
    # 1. FETCH
    articles = []
    if do_fetch:
        log.info("📥 Step 1: FETCH")
        library = SourceLibrary()
        articles = fetch_all_sources(
            library,
            topics=topics,
            mvp_only=mvp_only,
            max_articles_per_source=MAX_ARTICLES_PER_SOURCE
        )
        results["articles_fetched"] = len(articles)
    
    if not articles:
        log.warning("No articles fetched, pipeline stopped")
        return results
    
    # 2. CLASSIFY
    if do_classify:
        log.info("🏷️ Step 2: CLASSIFY")
        articles = classify_articles_batch(articles, topics)
        articles = filter_classified_articles(articles, include_discarded=False)
        results["articles_classified"] = len(articles)
    
    if not articles:
        log.warning("No articles after classification")
        return results
    
    # 3. CLUSTER
    clusters = {}
    if do_cluster:
        log.info("🔗 Step 3: CLUSTER")
        articles = add_embeddings_to_articles(articles)
        clusters = cluster_articles(articles)
        results["articles_clustered"] = sum(len(c) for c in clusters.values())
    
    # 4. SCORE
    selected_articles = []
    if do_score:
        log.info("📊 Step 4: SCORE")
        
        if clusters:
            # Score clusters
            valid_clusters = select_valid_clusters(clusters, max_clusters=MAX_CLUSTERS_PER_TOPIC * len(topics))
            results["clusters_valid"] = len(valid_clusters)
            
            # Get best articles from each valid cluster
            for cluster_id, cluster_articles, cs in valid_clusters:
                # Score articles within cluster
                scored = score_articles(cluster_articles)
                # Take top N per cluster
                selected_articles.extend(scored[:MAX_ARTICLES_PER_CLUSTER])
        else:
            # No clustering - score and select directly
            scored = score_articles(articles)
            by_topic = select_best_articles_per_topic(scored, topics, max_per_topic=5)
            for topic_articles in by_topic.values():
                selected_articles.extend(topic_articles)
        
        results["articles_selected"] = len(selected_articles)
    
    # 5. STORE
    if do_store and selected_articles:
        log.info("💾 Step 5: STORE")
        stored = store_articles(selected_articles)
        results["articles_stored"] = stored
    
    # Summary
    duration = time.time() - start_time
    results["duration_seconds"] = round(duration, 2)
    
    log.info(f"✅ Pipeline complete in {duration:.1f}s")
    log.info(f"   Fetched: {results['articles_fetched']}")
    log.info(f"   Classified: {results['articles_classified']}")
    log.info(f"   Clusters: {results['clusters_valid']}")
    log.info(f"   Selected: {results['articles_selected']}")
    
    return results


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Keernel Pipeline V2")
    parser.add_argument("--topics", nargs="+", default=MVP_TOPICS, help="Topics to process")
    parser.add_argument("--no-fetch", action="store_true", help="Skip fetch step")
    parser.add_argument("--no-classify", action="store_true", help="Skip classification")
    parser.add_argument("--no-cluster", action="store_true", help="Skip clustering")
    parser.add_argument("--no-score", action="store_true", help="Skip scoring")
    parser.add_argument("--no-store", action="store_true", help="Skip database storage")
    parser.add_argument("--dry-run", action="store_true", help="Don't store to database")
    
    args = parser.parse_args()
    
    results = run_pipeline(
        topics=args.topics,
        do_fetch=not args.no_fetch,
        do_classify=not args.no_classify,
        do_cluster=not args.no_cluster,
        do_score=not args.no_score,
        do_store=not args.no_store and not args.dry_run,
    )
    
    print("\n=== PIPELINE RESULTS ===")
    print(json.dumps(results, indent=2))
