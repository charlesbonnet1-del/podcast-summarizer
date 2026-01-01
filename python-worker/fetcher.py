"""
Keernel Fetcher - Multi-Level News Sourcing

2-Level Hierarchy:
1. GSheet RSS Library + Newsletters - Curated sources
2. Bing News - Backup/fallback

V17: Removed manual URLs (Level 1) - will be a separate podcast category later.

The system prioritizes trusted sources from the GSheet library,
falling back to Bing News only when necessary.
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, unquote, parse_qs, urlparse
import xml.etree.ElementTree as ET
import random

import httpx
import structlog
from dotenv import load_dotenv

from db import add_to_content_queue_auto, supabase

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_DELAY = 1.5

# ============================================
# VERTICAL MAPPING (GSheet → Database)
# ============================================
# GSheet uses: TECH, ECONOMICS, WORLD, SCIENCE, CULTURE
# Database uses: ai_tech, finance, politics, science, culture, world

VERTICAL_MAPPING = {
    "tech": "ai_tech",
    "economics": "finance",
    "world": "world",
    "science": "science",
    "culture": "culture",
    "politics": "politics",
    "finance": "finance",
    "ai_tech": "ai_tech",
}

def map_vertical(gsheet_vertical: str) -> str:
    """Map GSheet vertical name to database vertical_id."""
    if not gsheet_vertical:
        return "ai_tech"  # Default
    key = gsheet_vertical.strip().lower()
    return VERTICAL_MAPPING.get(key, key)

# V17: Removed MAX_ARTICLES_PER_VERTICAL and MAX_ARTICLES_PER_TOPIC
# Segment duration is now controlled at generation time, not fetch time
# This allows clustering to work with full data

# Markets configuration (Bing News - Level 2 backup)
MARKETS = {
    "FR": "https://www.bing.com/news/search?q={query}&format=rss&mkt=fr-FR",
    "US": "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-US",
    "UK": "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-GB",
    "DE": "https://www.bing.com/news/search?q={query}&format=rss&mkt=de-DE",
    "ES": "https://www.bing.com/news/search?q={query}&format=rss&mkt=es-ES",
    "IT": "https://www.bing.com/news/search?q={query}&format=rss&mkt=it-IT",
}

# Official supported topics (must match GSheet column B exactly)
SUPPORTED_TOPICS = [
    'ia', 'quantum', 'robotics',           # Tech
    'France', 'USA',                        # Politics (case-sensitive!)
    'crypto', 'macro', 'deals',            # Finance
    'space', 'health', 'energy',            # Science
    'cinema', 'gaming', 'lifestyle'         # Culture
]

# Topic to Bing search query mapping (for Level 3 backup)
TOPIC_QUERIES = {
    # Tech
    "ia": "intelligence artificielle IA ChatGPT",
    "quantum": "ordinateur quantique quantum computing",
    "robotics": "robotique robots",
    # Politics
    "France": "politique France actualité",
    "france": "politique France actualité",  # lowercase fallback
    "USA": "politique USA États-Unis",
    "usa": "politique USA États-Unis",  # lowercase fallback
    # Finance
    "crypto": "bitcoin crypto ethereum",
    "macro": "économie mondiale macroéconomie",
    "deals": "M&A levée fonds acquisition IPO bourse",
    # Science
    "space": "espace NASA SpaceX",
    "health": "santé médecine",
    "energy": "énergie climat transition",
    # Culture
    "cinema": "cinéma films séries",
    "gaming": "jeux vidéo gaming",
    "lifestyle": "tendances mode lifestyle"
}


# ============================================
# GSHEET SOURCING (Level 2)
# ============================================

def get_gsheet_sources_for_topics(topic_ids: list[str]) -> list[dict]:
    """
    Get articles from GSheet RSS library (Level 1 sourcing).
    
    V17: Fetches ALL sources (FR + INT) - no more international toggle.
    Returns list of articles fetched from trusted RSS sources.
    """
    try:
        from sourcing import GSheetSourceLibrary, fetch_rss_feed
        
        library = GSheetSourceLibrary()
        if not library.sheet:
            log.warning("GSheet not available, skipping Level 1 sourcing")
            return []
        
        articles = []
        seen_urls = set()
        
        # V17: Get ALL sources (FR + INT combined)
        sources_fr = library.get_sources_for_topics(topic_ids, origin="FR")
        sources_int = library.get_sources_for_topics(topic_ids, origin="INT")
        sources = sources_fr + sources_int
        log.info("Found GSheet sources", count_fr=len(sources_fr), count_int=len(sources_int), total=len(sources))
        
        # Fetch from top sources (sorted by score)
        # V17: Increased max_items per feed to 5 (was 2) - no topic limit
        # V17: No limit on number of RSS feeds - process all sources
        for source in sources:
            feed_articles = fetch_rss_feed(source["url"], max_items=5)
            
            if not feed_articles:
                # RSS failed - decrement score
                library.decrement_score(
                    source["row_index"], 
                    amount=5
                )
                log.warning("RSS fetch failed, score decremented", 
                           source=source["name"], 
                           url=source["url"][:50])
                continue
            
            for article in feed_articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    articles.append({
                        "url": article["url"],
                        "title": article["title"],
                        "source": source["name"],
                        "source_type": "gsheet_rss",
                        "score": source["score"],
                        "topic": source["topic"],
                        "vertical_id": map_vertical(source["vertical"])
                    })
            
            time.sleep(0.5)  # Rate limiting
            
            # Stop if we have enough
            if len(articles) >= 50:  # V14: Increased from 20 to 50
                break
        
        log.info("GSheet sourcing complete", articles=len(articles))
        return articles
        
    except ImportError as e:
        log.warning("Sourcing module not available", error=str(e))
        return []
    except Exception as e:
        log.error("GSheet sourcing failed", error=str(e))
        return []


# ============================================
# BING NEWS (Level 3 - Backup)
# ============================================

def fetch_rss(url: str) -> str | None:
    """Fetch RSS feed."""
    try:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, */*"}
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        log.error("RSS fetch failed", url=url[:80], error=str(e))
        return None


def extract_real_url(bing_url: str) -> str | None:
    """Extract real URL from Bing redirect."""
    try:
        parsed = urlparse(bing_url)
        params = parse_qs(parsed.query)
        if 'url' in params:
            return unquote(params['url'][0])
        if not bing_url.startswith('http://www.bing.com'):
            return bing_url
        return None
    except:
        return None


def parse_bing_rss(xml_content: str, max_items: int, market: str) -> list[dict]:
    """Parse Bing News RSS."""
    articles = []
    try:
        root = ET.fromstring(xml_content)
        items = root.findall(".//item")
        
        for item in items[:max_items]:
            title = item.find("title")
            link = item.find("link")
            source = item.find("{https://www.bing.com/news/search}Source")
            
            if title is not None and link is not None:
                real_url = extract_real_url(link.text)
                if real_url:
                    articles.append({
                        "title": title.text or "Untitled",
                        "url": real_url,
                        "source": source.text if source is not None else "Bing News",
                        "source_country": market,
                        "source_type": "bing_news"
                    })
        return articles
    except Exception as e:
        log.error("RSS parse failed", error=str(e))
        return []


def fetch_bing_for_query(query: str, market: str, max_items: int = 3) -> list[dict]:
    """Fetch articles from Bing News for a query."""
    url = MARKETS[market].format(query=quote_plus(query))
    xml = fetch_rss(url)
    if not xml:
        return []
    return parse_bing_rss(xml, max_items, market)


def fetch_bing_for_topics(topic_ids: list[str], max_articles: int = 10) -> list[dict]:
    """
    Fetch articles from Bing News (Level 2 - Backup).
    Used only when GSheet sources don't provide enough content.
    
    V17: Always fetches FR + US markets (no international toggle).
    """
    articles = []
    seen_urls = set()
    
    for topic_id in topic_ids:
        query = TOPIC_QUERIES.get(topic_id, topic_id)
        
        # FR market
        for article in fetch_bing_for_query(query, "FR", 2):
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                article["topic"] = topic_id
                articles.append(article)
        
        time.sleep(REQUEST_DELAY)
        
        # V17: Always include US market (was conditional on include_international)
        for article in fetch_bing_for_query(query, "US", 1):
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                article["topic"] = topic_id
                articles.append(article)
        time.sleep(REQUEST_DELAY)
        
        if len(articles) >= max_articles:
            break
    
    log.info("Bing backup sourcing complete", articles=len(articles))
    return articles


# ============================================
# MAIN FETCHER (V17 - Global Queue)
# ============================================

def get_all_gsheet_topics() -> list[str]:
    """
    Get all unique topics from GSheet RSS library.
    These are the topics we can potentially serve.
    """
    try:
        from sourcing import GSheetSourceLibrary
        library = GSheetSourceLibrary()
        if not library.sources:
            return []
        
        topics = set()
        for source in library.sources:
            topic = source.get("topic", "").strip().lower()
            if topic:
                topics.add(topic)
        
        log.info(f"📋 Found {len(topics)} topics in GSheet: {sorted(topics)}")
        return list(topics)
    except Exception as e:
        log.error(f"Failed to get GSheet topics: {e}")
        return []


def get_demanded_topics() -> set[str]:
    """
    Get topics that at least one user wants (weight > 0).
    Used to filter which segments to generate.
    """
    try:
        # Get all user_interests with their weights
        interests_result = supabase.table("user_interests") \
            .select("keyword") \
            .execute()
        
        # Get all users' topic_weights
        users_result = supabase.table("users") \
            .select("topic_weights") \
            .execute()
        
        demanded = set()
        
        # Add all keywords from user_interests
        for item in (interests_result.data or []):
            keyword = item.get("keyword", "").strip().lower()
            if keyword:
                demanded.add(keyword)
        
        # Add topics with weight > 0 from topic_weights
        for user in (users_result.data or []):
            weights = user.get("topic_weights") or {}
            for topic, weight in weights.items():
                if weight and weight > 0:
                    demanded.add(topic.lower())
        
        log.info(f"📊 Demanded topics (at least 1 user wants): {sorted(demanded)}")
        return demanded
    except Exception as e:
        log.error(f"Failed to get demanded topics: {e}")
        return set()


def run_fetcher(edition: str = "morning"):
    """
    V17: Global fetcher - fetches ALL topics from GSheet into a GLOBAL queue.
    
    No more per-user fetching. The queue is shared, segments are generated
    globally, then distributed to users based on their preferences.
    
    Hierarchy:
    1. GSheet RSS Library - All topics, FR + INT sources
    2. Bing News - Backup for topics with insufficient GSheet content
    """
    log.info("🚀 Starting Keernel V17 Global Fetcher", edition=edition)
    start = datetime.now()
    
    # Get ALL topics from GSheet
    all_topics = get_all_gsheet_topics()
    
    if not all_topics:
        log.warning("❌ No topics found in GSheet!")
        return
    
    log.info(f"📋 Fetching content for {len(all_topics)} topics")
    
    articles = []
    seen_urls = set()
    
    # Get existing URLs to avoid duplicates
    try:
        existing = supabase.table("content_queue") \
            .select("url") \
            .eq("status", "pending") \
            .execute()
        
        for item in (existing.data or []):
            seen_urls.add(item["url"])
        
        log.info(f"📦 {len(seen_urls)} URLs already in queue")
    except Exception as e:
        log.warning(f"Could not check existing URLs: {e}")
    
    # ============================================
    # LEVEL 1: GSheet RSS Library (FR + INT)
    # ============================================
    gsheet_articles = get_gsheet_sources_for_topics(all_topics)
    
    for article in gsheet_articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            articles.append(article)
    
    log.info(f"📰 Level 1 (GSheet): {len(articles)} articles")
    
    # ============================================
    # LEVEL 2: Bing News (Backup)
    # ============================================
    # Count articles per topic to find gaps
    topic_counts = {}
    for article in articles:
        topic = article.get("topic", "general")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    # Find topics with insufficient content (< 5 articles)
    MIN_ARTICLES_PER_TOPIC = 5
    sparse_topics = [t for t in all_topics if topic_counts.get(t, 0) < MIN_ARTICLES_PER_TOPIC]
    
    if sparse_topics:
        log.info(f"📰 Topics needing Bing backup: {sparse_topics}")
        
        bing_articles = fetch_bing_for_topics(sparse_topics, max_articles=len(sparse_topics) * 3)
        
        for article in bing_articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                articles.append(article)
        
        log.info(f"📰 After Bing backup: {len(articles)} total articles")
    
    # ============================================
    # ADD TO GLOBAL CONTENT QUEUE
    # ============================================
    total_added = 0
    
    for article in articles:
        source_type = article.get("source_type", "unknown")
        source_name = article.get("source", "unknown")
        
        result = add_to_content_queue_auto(
            user_id="global",  # V17: Global queue, no user_id
            url=article["url"],
            title=article["title"],
            keyword=article.get("topic", "general"),
            edition=edition,
            source=source_type,
            source_name=source_name,
            source_country=article.get("source_country", "FR"),
            vertical_id=article.get("vertical_id")
        )
        if result:
            total_added += 1
    
    elapsed = (datetime.now() - start).total_seconds()
    log.info(f"✅ Fetcher complete: {total_added} articles added in {elapsed:.1f}s")


# V17: fetch_for_user REMOVED - queue is now global
# Segments are generated globally then distributed to users based on preferences


def cleanup_old():
    """
    Remove pending items older than 3 days.
    
    V17: Content queue items stay eligible for 3 days for clustering,
    then are cleaned up.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        supabase.table("content_queue") \
            .delete() \
            .eq("status", "pending") \
            .lt("created_at", cutoff) \
            .execute()
        log.info("Cleanup complete (removed items older than 3 days)")
    except Exception as e:
        log.error("Cleanup failed", error=str(e))


def main():
    parser = argparse.ArgumentParser(description="Keernel News Fetcher")
    parser.add_argument("--edition", choices=["morning", "evening"], default="morning")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--test-gsheet", action="store_true", help="Test GSheet connection")
    args = parser.parse_args()
    
    if args.test_gsheet:
        # Test GSheet connection
        log.info("Testing GSheet connection...")
        try:
            from sourcing import GSheetSourceLibrary, SUPPORTED_TOPICS
            
            log.info(f"Supported topics: {SUPPORTED_TOPICS}")
            
            library = GSheetSourceLibrary()
            if library.sheet:
                log.info("GSheet connected successfully!")
                
                # Try to get some sources with real topics
                test_topics = ["ia", "France", "crypto"]
                log.info(f"Testing with topics: {test_topics}")
                
                sources = library.get_sources_for_topics(test_topics, origin="FR")
                log.info(f"Found {len(sources)} FR sources")
                
                for s in sources[:5]:
                    log.info(f"  [{s['topic']}] {s['name']} (score={s['score']})")
                    log.info(f"    URL: {s['url'][:60]}...")
                
                # Test INT sources
                sources_int = library.get_sources_for_topics(test_topics, origin="INT")
                log.info(f"Found {len(sources_int)} INT sources")
            else:
                log.error("GSheet connection failed - sheet is None")
        except Exception as e:
            log.error("GSheet test failed", error=str(e))
            import traceback
            traceback.print_exc()
        return
    
    if args.cleanup:
        cleanup_old()
    
    run_fetcher(edition=args.edition)


if __name__ == "__main__":
    main()
