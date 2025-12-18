"""
Fetcher module for Google News RSS.
Fetches news based on user interests/keywords.

Usage:
    python fetcher.py --edition morning
    python fetcher.py --edition evening
"""
import os
import sys
import time
import argparse
from datetime import datetime
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx
import structlog
from dotenv import load_dotenv

from db import (
    get_all_active_keywords,
    add_to_content_queue_auto,
    supabase,
)

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

# User-Agent to mimic a real browser (CRITICAL for Google News)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Delay between requests to avoid rate limiting
REQUEST_DELAY_SECONDS = 3

# Max articles per keyword
MAX_ARTICLES_PER_KEYWORD = 3

# Google News RSS base URL (French)
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=fr&gl=FR&ceid=FR:fr"

# Alternative: English
# GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


# ============================================
# FETCHER FUNCTIONS
# ============================================

def build_google_news_url(keyword: str) -> str:
    """Build Google News RSS URL for a keyword."""
    encoded_keyword = quote_plus(keyword)
    return GOOGLE_NEWS_RSS_URL.format(query=encoded_keyword)


def fetch_rss_feed(url: str) -> str | None:
    """Fetch RSS feed content with proper headers."""
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        }
        
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        
        return response.text
    
    except httpx.HTTPStatusError as e:
        log.error("HTTP error fetching RSS", url=url, status=e.response.status_code)
        return None
    except Exception as e:
        log.error("Error fetching RSS", url=url, error=str(e))
        return None


def parse_google_news_rss(xml_content: str, max_items: int = 3) -> list[dict]:
    """Parse Google News RSS and extract top articles."""
    articles = []
    
    try:
        root = ET.fromstring(xml_content)
        
        # Find all items in the RSS feed
        items = root.findall(".//item")
        
        for item in items[:max_items]:
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            source_elem = item.find("source")
            
            if title_elem is not None and link_elem is not None:
                # Resolve Google News redirect URL to get real article URL
                google_url = link_elem.text
                real_url = resolve_google_news_url(google_url)
                
                if real_url:
                    article = {
                        "title": title_elem.text or "Untitled",
                        "url": real_url,
                        "pub_date": pub_date_elem.text if pub_date_elem is not None else None,
                        "source": source_elem.text if source_elem is not None else "Unknown",
                    }
                    articles.append(article)
        
        return articles
    
    except ET.ParseError as e:
        log.error("Error parsing RSS XML", error=str(e))
        return []


def resolve_google_news_url(google_url: str) -> str | None:
    """Follow Google News redirect to get the real article URL."""
    try:
        headers = {
            "User-Agent": USER_AGENT,
        }
        # Follow redirects to get final URL
        response = httpx.head(google_url, headers=headers, timeout=10, follow_redirects=True)
        final_url = str(response.url)
        
        # Make sure we got a real URL, not still a Google URL
        if "news.google.com" not in final_url:
            return final_url
        
        # If HEAD didn't work, try GET
        response = httpx.get(google_url, headers=headers, timeout=10, follow_redirects=True)
        final_url = str(response.url)
        
        if "news.google.com" not in final_url:
            return final_url
            
        log.warning("Could not resolve Google News URL", url=google_url)
        return None
        
    except Exception as e:
        log.error("Error resolving Google News URL", url=google_url, error=str(e))
        return None


def fetch_news_for_keyword(keyword: str) -> list[dict]:
    """Fetch top news articles for a single keyword."""
    log.info("Fetching news for keyword", keyword=keyword)
    
    url = build_google_news_url(keyword)
    xml_content = fetch_rss_feed(url)
    
    if not xml_content:
        log.warning("No content received for keyword", keyword=keyword)
        return []
    
    articles = parse_google_news_rss(xml_content, max_items=MAX_ARTICLES_PER_KEYWORD)
    
    log.info("Fetched articles", keyword=keyword, count=len(articles))
    return articles


def run_fetcher(edition: str = "morning"):
    """
    Main fetcher function.
    Fetches news for all active user keywords and adds to content queue.
    
    Args:
        edition: 'morning' or 'evening'
    """
    log.info("Starting news fetcher", edition=edition)
    start_time = datetime.now()
    
    # Get all active keywords with their user_ids
    keyword_data = get_all_active_keywords()
    
    if not keyword_data:
        log.info("No active keywords found")
        return
    
    log.info("Active keywords found", count=len(keyword_data))
    
    total_articles_added = 0
    
    for kw_info in keyword_data:
        keyword = kw_info["keyword"]
        user_ids = kw_info["user_ids"]
        
        # Fetch articles for this keyword
        articles = fetch_news_for_keyword(keyword)
        
        if not articles:
            log.warning("No articles found for keyword", keyword=keyword)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        
        # Add articles to content queue for each user following this keyword
        for article in articles:
            for user_id in user_ids:
                result = add_to_content_queue_auto(
                    user_id=user_id,
                    url=article["url"],
                    title=article["title"],
                    keyword=keyword,
                    edition=edition,
                    source="google_news"
                )
                
                if result:
                    total_articles_added += 1
                    log.debug("Article added to queue", 
                             user_id=user_id[:8], 
                             keyword=keyword, 
                             title=article["title"][:50])
        
        # Respectful delay between keywords
        log.info("Waiting before next keyword", delay=REQUEST_DELAY_SECONDS)
        time.sleep(REQUEST_DELAY_SECONDS)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    log.info("Fetcher complete", 
             edition=edition,
             keywords_processed=len(keyword_data),
             articles_added=total_articles_added,
             elapsed_seconds=round(elapsed, 2))


def cleanup_old_pending():
    """Remove pending items older than 48 hours to avoid stale content."""
    try:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()
        
        result = supabase.table("content_queue") \
            .delete() \
            .eq("status", "pending") \
            .lt("created_at", cutoff) \
            .execute()
        
        if result.data:
            log.info("Cleaned up old pending items", count=len(result.data))
    except Exception as e:
        log.error("Error cleaning up old items", error=str(e))


# ============================================
# MAIN
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Fetch news for user interests")
    parser.add_argument(
        "--edition",
        choices=["morning", "evening"],
        default="morning",
        help="Edition to fetch (morning or evening)"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Also cleanup old pending items"
    )
    
    args = parser.parse_args()
    
    if args.cleanup:
        cleanup_old_pending()
    
    run_fetcher(edition=args.edition)


if __name__ == "__main__":
    main()
