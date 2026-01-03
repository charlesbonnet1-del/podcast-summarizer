"""
Keernel Daily CRON

Runs every morning at 6h Paris time:
1. Fetch articles from all MVP sources
2. Classify generalist articles
3. Cluster similar articles
4. Score clusters (Radar + Loupe)
5. Generate structured summaries for valid clusters
6. Store everything in database
7. (Optional) Generate podcast episode

Can be triggered via:
- Render Cron Job
- Manual HTTP call to /cron/daily
"""
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()

# Local imports
from pipeline_v2 import (
    run_pipeline,
    cluster_articles,
    add_embeddings_to_articles,
    store_articles,
    get_supabase_client,
)
from sourcing_v2 import (
    SourceLibrary,
    fetch_all_sources,
    MVP_TOPICS,
)
from classifier import (
    classify_articles_batch,
    filter_classified_articles,
)
from scoring import (
    score_articles,
    score_clusters,
    select_valid_clusters,
)
from summary_generator import (
    generate_cluster_summary,
    store_summaries,
)


# ============================================
# CONFIGURATION
# ============================================

MAX_ARTICLES_PER_SOURCE = 10
MAX_CLUSTERS_PER_TOPIC = 5


# ============================================
# MAIN DAILY CRON
# ============================================

def run_daily_cron(
    topics: list[str] = None,
    generate_podcast: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Run the complete daily pipeline.
    
    Args:
        topics: Topics to process (default: MVP_TOPICS)
        generate_podcast: Whether to also generate podcast
        dry_run: Don't store anything to database
    
    Returns:
        Results dict with stats
    """
    topics = topics or MVP_TOPICS
    start_time = time.time()
    
    log.info(f"🌅 Daily CRON started", topics=topics, dry_run=dry_run)
    
    results = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "topics": topics,
        "articles_fetched": 0,
        "articles_classified": 0,
        "clusters_found": 0,
        "clusters_valid": 0,
        "summaries_generated": 0,
        "dry_run": dry_run,
        "errors": [],
    }
    
    try:
        # ========================================
        # STEP 1: FETCH
        # ========================================
        log.info("📥 Step 1/6: FETCH")
        library = SourceLibrary()
        articles = fetch_all_sources(
            library,
            topics=topics,
            mvp_only=True,
            max_articles_per_source=MAX_ARTICLES_PER_SOURCE
        )
        results["articles_fetched"] = len(articles)
        
        if not articles:
            results["errors"].append("No articles fetched")
            return results
        
        # ========================================
        # STEP 2: CLASSIFY
        # ========================================
        log.info("🏷️ Step 2/6: CLASSIFY")
        articles = classify_articles_batch(articles, topics)
        articles = filter_classified_articles(articles, include_discarded=False)
        results["articles_classified"] = len(articles)
        
        if not articles:
            results["errors"].append("No articles after classification")
            return results
        
        # ========================================
        # STEP 3: EMBED
        # ========================================
        log.info("🧠 Step 3/6: EMBED")
        articles = add_embeddings_to_articles(articles)
        
        # ========================================
        # STEP 4: CLUSTER
        # ========================================
        log.info("🔗 Step 4/6: CLUSTER")
        clusters = cluster_articles(articles)
        results["clusters_found"] = len([k for k in clusters.keys() if k != -1])
        
        # ========================================
        # STEP 5: SCORE & SELECT
        # ========================================
        log.info("📊 Step 5/6: SCORE")
        valid_clusters = select_valid_clusters(
            clusters, 
            max_clusters=MAX_CLUSTERS_PER_TOPIC * len(topics)
        )
        results["clusters_valid"] = len(valid_clusters)
        
        if not valid_clusters:
            results["errors"].append("No valid clusters found")
            log.warning("No valid clusters, skipping summary generation")
            return results
        
        # ========================================
        # STEP 6: GENERATE SUMMARIES
        # ========================================
        log.info("📝 Step 6/6: GENERATE SUMMARIES")
        summaries = []
        
        for cluster_id, cluster_articles_list, cs in valid_clusters:
            # Determine topic from articles
            topic = cluster_articles_list[0].get("topic") or cluster_articles_list[0].get("classified_topic", "unknown")
            
            log.info(f"  Generating summary for cluster {cluster_id} ({topic})")
            
            summary = generate_cluster_summary(
                cluster_articles_list,
                topic=topic,
                enrich=True  # Use Perplexity
            )
            
            if summary:
                summary["cluster_id"] = cluster_id
                summaries.append(summary)
            
            # Rate limiting
            time.sleep(0.5)
        
        results["summaries_generated"] = len(summaries)
        
        # ========================================
        # STORE TO DATABASE
        # ========================================
        if not dry_run:
            log.info("💾 Storing to database...")
            
            # Store articles
            all_articles = []
            for cluster_id, cluster_articles_list, cs in valid_clusters:
                for article in cluster_articles_list:
                    article["cluster_id"] = cluster_id
                all_articles.extend(cluster_articles_list)
            
            stored_articles = store_articles(all_articles)
            results["articles_stored"] = stored_articles
            
            # Store clusters
            stored_clusters = store_clusters_to_db(valid_clusters)
            results["clusters_stored"] = stored_clusters
            
            # Store summaries
            stored_summaries = store_summaries_to_db(summaries)
            results["summaries_stored"] = stored_summaries
            
            # Create daily briefing record
            briefing_id = create_daily_briefing(topics, summaries)
            results["briefing_id"] = briefing_id
        
        # ========================================
        # OPTIONAL: GENERATE PODCAST
        # ========================================
        if generate_podcast and not dry_run:
            log.info("🎙️ Generating podcast...")
            # TODO: Integrate with existing podcast generation
            pass
        
    except Exception as e:
        log.error("Daily CRON failed", error=str(e))
        results["errors"].append(str(e))
        import traceback
        results["traceback"] = traceback.format_exc()
    
    # Summary
    duration = time.time() - start_time
    results["duration_seconds"] = round(duration, 2)
    
    log.info(f"✅ Daily CRON complete in {duration:.1f}s")
    log.info(f"   Fetched: {results['articles_fetched']}")
    log.info(f"   Classified: {results['articles_classified']}")
    log.info(f"   Valid clusters: {results['clusters_valid']}")
    log.info(f"   Summaries: {results['summaries_generated']}")
    
    return results


# ============================================
# DATABASE HELPERS
# ============================================

def store_clusters_to_db(valid_clusters: list) -> int:
    """Store clusters to database."""
    client = get_supabase_client()
    if not client:
        return 0
    
    stored = 0
    for cluster_id, articles, cs in valid_clusters:
        try:
            # Determine topic
            topic = articles[0].get("topic") or articles[0].get("classified_topic", "unknown")
            
            record = {
                "id": cluster_id,
                "topic": topic,
                "total_score": cs.total_score,
                "authority_count": cs.authority_count,
                "generalist_count": cs.generalist_count,
                "corporate_count": cs.corporate_count,
                "source_count": cs.source_count,
                "is_valid": cs.is_valid,
                "validation_reason": cs.reason,
            }
            
            client.table("clusters").upsert(record, on_conflict="id").execute()
            stored += 1
            
        except Exception as e:
            log.warning("Failed to store cluster", cluster_id=cluster_id, error=str(e))
    
    return stored


def store_summaries_to_db(summaries: list[dict]) -> int:
    """Store summaries to database."""
    client = get_supabase_client()
    if not client:
        return 0
    
    stored = 0
    today = datetime.now(timezone.utc).date().isoformat()
    
    for s in summaries:
        try:
            record = {
                "cluster_id": s["cluster_id"],
                "topic": s["topic"],
                "title": s["title"],
                "summary_markdown": s["summary_markdown"],
                "key_points": s.get("key_points", []),
                "why_it_matters": s.get("why_it_matters", ""),
                "sources": s.get("sources", []),
                "article_count": s.get("article_count", 0),
                "perplexity_context": s.get("perplexity_context"),
                "generated_at": s["generated_at"],
                "date": today,
            }
            
            client.table("cluster_summaries").upsert(
                record, 
                on_conflict="cluster_id,date"
            ).execute()
            stored += 1
            
        except Exception as e:
            log.warning("Failed to store summary", error=str(e))
    
    return stored


def create_daily_briefing(topics: list[str], summaries: list[dict]) -> str:
    """Create daily briefing record."""
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        cluster_ids = [s["cluster_id"] for s in summaries]
        
        # Combine all summaries into one markdown
        combined = f"# Daily Intelligence Briefing - {today}\n\n"
        for s in summaries:
            combined += f"---\n\n"
            combined += s["summary_markdown"]
            combined += "\n\n"
        
        record = {
            "date": today,
            "topics": topics,
            "summary_count": len(summaries),
            "cluster_ids": cluster_ids,
            "combined_markdown": combined,
            "status": "ready",
        }
        
        result = client.table("daily_briefings").upsert(
            record,
            on_conflict="date"
        ).execute()
        
        return result.data[0]["id"] if result.data else None
        
    except Exception as e:
        log.warning("Failed to create daily briefing", error=str(e))
        return None


# ============================================
# RETRIEVAL FUNCTIONS (for frontend)
# ============================================

def get_todays_summaries(topics: list[str] = None) -> list[dict]:
    """Get today's summaries for display."""
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        
        query = client.table("cluster_summaries") \
            .select("*") \
            .eq("date", today)
        
        if topics:
            query = query.in_("topic", topics)
        
        result = query.order("generated_at", desc=True).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        log.error("Failed to get summaries", error=str(e))
        return []


def get_summaries_by_date(date: str, topics: list[str] = None) -> list[dict]:
    """Get summaries for a specific date."""
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        query = client.table("cluster_summaries") \
            .select("*") \
            .eq("date", date)
        
        if topics:
            query = query.in_("topic", topics)
        
        result = query.order("generated_at", desc=True).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        log.error("Failed to get summaries", error=str(e))
        return []


def get_archive_dates(limit: int = 30) -> list[str]:
    """Get list of dates with available summaries."""
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        result = client.table("daily_briefings") \
            .select("date, summary_count, topics") \
            .eq("status", "ready") \
            .order("date", desc=True) \
            .limit(limit) \
            .execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        log.error("Failed to get archive dates", error=str(e))
        return []


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Keernel Daily CRON")
    parser.add_argument("--topics", nargs="+", default=MVP_TOPICS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--with-podcast", action="store_true")
    
    args = parser.parse_args()
    
    results = run_daily_cron(
        topics=args.topics,
        generate_podcast=args.with_podcast,
        dry_run=args.dry_run
    )
    
    import json
    print("\n=== CRON RESULTS ===")
    print(json.dumps(results, indent=2, default=str))
