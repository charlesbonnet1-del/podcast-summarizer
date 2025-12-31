"""
Keernel Fetcher - Multi-Level News Sourcing

3-Level Hierarchy:
1. Manual URLs (from content_queue) - Highest priority
2. GSheet RSS Library + Newsletters - Curated sources
3. Bing News - Backup/fallback

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
MAX_ARTICLES_PER_VERTICAL = 3
MAX_ARTICLES_PER_TOPIC = 2

# Markets configuration (Bing News - Level 3 backup)
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

def get_gsheet_sources_for_topics(topic_ids: list[str], include_international: bool = False) -> list[dict]:
    """
    Get articles from GSheet RSS library (Level 2 sourcing).
    Returns list of articles fetched from trusted RSS sources.
    """
    try:
        from sourcing import GSheetSourceLibrary, fetch_rss_feed
        
        library = GSheetSourceLibrary()
        if not library.sheet:
            log.warning("GSheet not available, skipping Level 2 sourcing")
            return []
        
        articles = []
        seen_urls = set()
        
        # Get FR sources
        sources = library.get_sources_for_topics(topic_ids, origin="FR")
        log.info("Found GSheet sources (FR)", count=len(sources))
        
        # Add international sources if enabled
        if include_international:
            intl_sources = library.get_sources_for_topics(topic_ids, origin="INT")
            sources.extend(intl_sources)
            log.info("Found GSheet sources (INT)", count=len(intl_sources))
        
        # Fetch from top sources (sorted by score)
        for source in sources[:30]:  # V14: Increased from 15 to 30 RSS feeds
            feed_articles = fetch_rss_feed(source["url"], max_items=MAX_ARTICLES_PER_TOPIC)
            
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


def fetch_bing_for_topics(topic_ids: list[str], include_international: bool = False, 
                          max_articles: int = 10) -> list[dict]:
    """
    Fetch articles from Bing News (Level 3 - Backup).
    Used only when GSheet sources don't provide enough content.
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
        
        # International
        if include_international:
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
# MAIN FETCHER (3-Level Hierarchy)
# ============================================

def run_fetcher(edition: str = "morning"):
    """
    Main fetcher with 3-level sourcing hierarchy:
    1. Manual URLs (already in queue) - Skip, handled separately
    2. GSheet RSS Library - Trusted curated sources
    3. Bing News - Backup when Level 2 insufficient
    """
    log.info("Starting Keernel fetcher", edition=edition)
    start = datetime.now()
    
    # Get all users with their settings
    try:
        users_result = supabase.table("users") \
            .select("id, first_name, include_international, selected_verticals") \
            .execute()
        users = users_result.data or []
    except Exception as e:
        log.error("Failed to get users", error=str(e))
        return
    
    if not users:
        log.info("No users found")
        return
    
    # Get custom keywords (user_interests) - these are the granular topics
    try:
        interests_result = supabase.table("user_interests") \
            .select("user_id, keyword, display_name, search_keywords") \
            .execute()
        interests_by_user = {}
        for item in (interests_result.data or []):
            uid = item["user_id"]
            if uid not in interests_by_user:
                interests_by_user[uid] = []
            interests_by_user[uid].append({
                "keyword": item["keyword"],
                "display_name": item.get("display_name"),
                "search_keywords": item.get("search_keywords")
            })
    except Exception as e:
        log.warning("Failed to get interests", error=str(e))
        interests_by_user = {}
    
    total_added = 0
    
    for user in users:
        user_id = user["id"]
        include_intl = user.get("include_international", False)
        
        log.info("Processing user", user_id=user_id[:8], intl=include_intl)
        
        # Get user's topics (keywords from user_interests)
        user_topics = interests_by_user.get(user_id, [])
        topic_ids = [t["keyword"] for t in user_topics]
        
        if not topic_ids:
            log.info("No topics for user, skipping", user_id=user_id[:8])
            continue
        
        # V14: No limit - use all user topics
        # topic_ids = topic_ids[:8]  # Removed artificial limit
        
        articles = []
        seen_urls = set()
        
        # ============================================
        # LEVEL 2: GSheet RSS Library
        # ============================================
        gsheet_articles = get_gsheet_sources_for_topics(topic_ids, include_intl)
        
        for article in gsheet_articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                articles.append(article)
        
        log.info("Level 2 (GSheet) articles", count=len(articles), user=user_id[:8])
        
        # ============================================
        # LEVEL 3: Bing News (Backup)
        # ============================================
        # Only fetch from Bing if we don't have enough articles
        target_articles = len(topic_ids) * 3  # ~3 articles per topic
        
        if len(articles) < target_articles:
            remaining = target_articles - len(articles)
            log.info("Fetching backup from Bing", 
                    need=remaining, 
                    user=user_id[:8])
            
            bing_articles = fetch_bing_for_topics(
                topic_ids, 
                include_intl, 
                max_articles=remaining
            )
            
            for article in bing_articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    articles.append(article)
        
        log.info("Total articles for user", 
                count=len(articles), 
                user=user_id[:8])
        
        # ============================================
        # ADD TO CONTENT QUEUE
        # ============================================
        for article in articles:
            # source_type: gsheet_rss, bing_news, etc. (for categorization)
            # source_name: "Le Monde", "TechCrunch", etc. (for display in dialogue)
            source_type = article.get("source_type", "unknown")
            source_name = article.get("source", "unknown")  # Media name from GSheet or Bing
            
            result = add_to_content_queue_auto(
                user_id=user_id,
                url=article["url"],
                title=article["title"],
                keyword=article.get("topic", "general"),
                edition=edition,
                source=source_type,  # gsheet_rss, bing_news, etc.
                source_name=source_name,  # V13: Media name for dialogue prompt
                source_country=article.get("source_country", "FR"),
                vertical_id=article.get("vertical_id")
            )
            if result:
                total_added += 1
    
    elapsed = (datetime.now() - start).total_seconds()
    log.info("Fetcher complete", 
             users=len(users), 
             articles_added=total_added, 
             elapsed=round(elapsed, 1))


def fetch_for_user(user_id: str, edition: str = None) -> int:
    """
    Fetch content for a specific user.
    Called before on-demand generation to ensure enough content.
    
    Returns:
        Number of articles added
    """
    if not edition:
        edition = "morning" if datetime.now().hour < 14 else "evening"
    
    log.info(f"🔄 Fetching content for user {user_id[:8]}...")
    
    try:
        # Get user settings
        user_result = supabase.table("users") \
            .select("id, first_name, include_international, selected_verticals") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if not user_result.data:
            log.warning(f"User {user_id[:8]} not found")
            return 0
        
        user = user_result.data
        include_intl = user.get("include_international", False)
        
        # Get user's topics
        interests_result = supabase.table("user_interests") \
            .select("keyword, display_name, search_keywords") \
            .eq("user_id", user_id) \
            .execute()
        
        topic_ids = [t["keyword"] for t in (interests_result.data or [])]
        
        if not topic_ids:
            log.warning(f"No topics for user {user_id[:8]}")
            return 0
        
        # V14: No limit - use all user topics
        # topic_ids = topic_ids[:8]  # Removed artificial limit
        
        articles = []
        seen_urls = set()
        
        # Get existing URLs to avoid duplicates
        existing = supabase.table("content_queue") \
            .select("url") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        
        for item in (existing.data or []):
            seen_urls.add(item["url"])
        
        # Level 2: GSheet RSS
        gsheet_articles = get_gsheet_sources_for_topics(topic_ids, include_intl)
        
        for article in gsheet_articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                articles.append(article)
        
        log.info(f"📰 GSheet articles: {len(articles)}")
        
        # Level 3: Bing News backup - only if GSheet gave very few articles
        target_articles = len(topic_ids) * 5  # V14: Increased from 3 to 5 per topic
        if len(articles) < target_articles:
            remaining = target_articles - len(articles)
            bing_articles = fetch_bing_for_topics(topic_ids, include_intl, max_articles=remaining)
            
            for article in bing_articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    articles.append(article)
        
        log.info(f"📰 Total articles: {len(articles)}")
        
        # Add to queue
        added = 0
        for article in articles:
            source_type = article.get("source_type", "unknown")
            source_name = article.get("source", None)  # Media name
            
            result = add_to_content_queue_auto(
                user_id=user_id,
                url=article["url"],
                title=article["title"],
                keyword=article.get("topic", "general"),
                edition=edition,
                source=source_type,
                source_name=source_name,  # V13: Media name for dialogue
                source_country=article.get("source_country", "FR"),
                vertical_id=article.get("vertical_id")
            )
            if result:
                added += 1
        
        log.info(f"✅ Added {added} articles for user {user_id[:8]}")
        return added
        
    except Exception as e:
        log.error(f"fetch_for_user failed: {e}")
        return 0


def cleanup_old():
    """Remove pending items older than 48h."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        supabase.table("content_queue") \
            .delete() \
            .eq("status", "pending") \
            .lt("created_at", cutoff) \
            .execute()
        log.info("Cleanup complete")
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
