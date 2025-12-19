"""
Fetcher module for Bing News RSS.
Fetches news based on user interests/keywords.
Supports international sources (US, UK, DE, ES, IT).

Usage:
    python fetcher.py --edition morning
    python fetcher.py --edition evening
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, unquote, parse_qs, urlparse
import xml.etree.ElementTree as ET
import re

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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_DELAY_SECONDS = 2
MAX_ARTICLES_PER_KEYWORD = 3

# Bing News RSS endpoints by market
BING_NEWS_MARKETS = {
    "FR": {
        "url": "https://www.bing.com/news/search?q={query}&format=rss&mkt=fr-FR",
        "name": "France"
    },
    "US": {
        "url": "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-US",
        "name": "United States"
    },
    "UK": {
        "url": "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-GB",
        "name": "United Kingdom"
    },
    "DE": {
        "url": "https://www.bing.com/news/search?q={query}&format=rss&mkt=de-DE",
        "name": "Germany"
    },
    "ES": {
        "url": "https://www.bing.com/news/search?q={query}&format=rss&mkt=es-ES",
        "name": "Spain"
    },
    "IT": {
        "url": "https://www.bing.com/news/search?q={query}&format=rss&mkt=it-IT",
        "name": "Italy"
    },
}


# ============================================
# FETCHER FUNCTIONS
# ============================================

def build_bing_news_url(keyword: str, market: str = "FR") -> str:
    """Build Bing News RSS URL for a keyword and market."""
    encoded_keyword = quote_plus(keyword)
    market_config = BING_NEWS_MARKETS.get(market, BING_NEWS_MARKETS["FR"])
    return market_config["url"].format(query=encoded_keyword)


def extract_real_url(bing_url: str) -> str | None:
    """Extract the real article URL from Bing's redirect URL."""
    try:
        parsed = urlparse(bing_url)
        params = parse_qs(parsed.query)
        
        if 'url' in params:
            real_url = unquote(params['url'][0])
            return real_url
        
        if not bing_url.startswith('http://www.bing.com'):
            return bing_url
            
        return None
    except Exception as e:
        log.warning("Could not extract URL", bing_url=bing_url[:100], error=str(e))
        return None


def fetch_rss_feed(url: str) -> str | None:
    """Fetch RSS feed content with proper headers."""
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        
        return response.text
    
    except Exception as e:
        log.error("Error fetching RSS", url=url, error=str(e))
        return None


def parse_bing_news_rss(xml_content: str, max_items: int = 3, market: str = "FR") -> list[dict]:
    """Parse Bing News RSS and extract articles with real URLs."""
    articles = []
    
    try:
        root = ET.fromstring(xml_content)
        items = root.findall(".//item")
        
        for item in items:
            if len(articles) >= max_items:
                break
                
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            description_elem = item.find("description")
            
            # Get source from News:Source namespace
            source_elem = item.find("{https://www.bing.com/news/search}Source")
            source = source_elem.text if source_elem is not None else "Unknown"
            
            if title_elem is not None and link_elem is not None:
                bing_url = link_elem.text
                real_url = extract_real_url(bing_url)
                
                if real_url:
                    article = {
                        "title": title_elem.text or "Untitled",
                        "url": real_url,
                        "pub_date": pub_date_elem.text if pub_date_elem is not None else None,
                        "source": source,
                        "source_country": market,
                        "description": description_elem.text[:200] if description_elem is not None and description_elem.text else None,
                    }
                    articles.append(article)
                    log.info("Found article", 
                            title=article["title"][:60], 
                            source=source,
                            market=market)
        
        return articles
    
    except ET.ParseError as e:
        log.error("Error parsing RSS XML", error=str(e))
        return []


def fetch_news_for_keyword(keyword: str, markets: list[str] = None) -> list[dict]:
    """
    Fetch top news articles for a keyword from Bing News.
    
    Args:
        keyword: Search keyword
        markets: List of market codes (FR, US, UK, DE, ES, IT). Defaults to FR only.
    """
    if markets is None:
        markets = ["FR"]
    
    log.info("Fetching news for keyword", keyword=keyword, markets=markets)
    
    all_articles = []
    seen_urls = set()
    
    for market in markets:
        url = build_bing_news_url(keyword, market)
        xml_content = fetch_rss_feed(url)
        
        if not xml_content:
            log.warning("No content received", keyword=keyword, market=market)
            continue
        
        # Get fewer articles per market when fetching international
        max_per_market = MAX_ARTICLES_PER_KEYWORD if len(markets) == 1 else 2
        articles = parse_bing_news_rss(xml_content, max_items=max_per_market, market=market)
        
        # Deduplicate by URL
        for article in articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                all_articles.append(article)
        
        time.sleep(0.5)  # Small delay between markets
    
    log.info("Fetched articles", keyword=keyword, count=len(all_articles))
    return all_articles[:MAX_ARTICLES_PER_KEYWORD * 2]  # Max 6 articles with international


def run_fetcher(edition: str = "morning"):
    """
    Main fetcher function.
    Fetches news for all active user keywords and adds to content queue.
    Respects user's include_international setting.
    """
    log.info("Starting news fetcher", edition=edition)
    start_time = datetime.now()
    
    # Get all active keywords with their user_ids
    keyword_data = get_all_active_keywords()
    
    if not keyword_data:
        log.info("No active keywords found")
        return
    
    log.info("Active keywords found", count=len(keyword_data))
    
    # Get user preferences for international sources
    user_prefs = {}
    try:
        users_result = supabase.table("users").select("id, include_international").execute()
        for user in users_result.data or []:
            user_prefs[user["id"]] = user.get("include_international", False)
    except Exception as e:
        log.warning("Could not fetch user preferences", error=str(e))
    
    total_articles_added = 0
    
    for kw_info in keyword_data:
        keyword = kw_info["keyword"]
        user_ids = kw_info["user_ids"]
        
        # Check if any user wants international sources
        any_international = any(user_prefs.get(uid, False) for uid in user_ids)
        
        # Determine markets to fetch
        if any_international:
            markets = ["FR", "US", "UK", "DE", "ES", "IT"]
        else:
            markets = ["FR"]
        
        # Fetch articles for this keyword
        articles = fetch_news_for_keyword(keyword, markets)
        
        if not articles:
            log.warning("No articles found for keyword", keyword=keyword)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        
        # Add articles to content queue for each user following this keyword
        for article in articles:
            for user_id in user_ids:
                # Only add international articles to users who want them
                if article["source_country"] != "FR" and not user_prefs.get(user_id, False):
                    continue
                
                result = add_to_content_queue_auto(
                    user_id=user_id,
                    url=article["url"],
                    title=article["title"],
                    keyword=keyword,
                    edition=edition,
                    source=article.get("source", "bing_news"),
                    source_country=article.get("source_country", "FR")
                )
                
                if result:
                    total_articles_added += 1
                    log.debug("Article added to queue", 
                             user_id=user_id[:8], 
                             keyword=keyword, 
                             market=article["source_country"],
                             title=article["title"][:50])
        
        # Delay between keywords
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
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        
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
