"""
Keernel Fetcher - Multi-Vertical News Sourcing

Fetches news based on:
1. User's selected verticals (5 Alpha Verticals)
2. User's custom keywords
3. User's international preference

The 5 Alpha Verticals:
- V1: IA & Tech (LLM, Hardware, Robotique)
- V2: Politique & Monde (France, USA, International)
- V3: Finance & Marchés (Bourse, Crypto, Macro)
- V4: Science & Santé (Espace, Biotech, Énergie)
- V5: Culture & Divertissement (Cinéma, Gaming, Streaming)
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
MAX_ARTICLES_PER_VERTICAL = 3

# Markets configuration
MARKETS = {
    "FR": "https://www.bing.com/news/search?q={query}&format=rss&mkt=fr-FR",
    "US": "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-US",
    "UK": "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-GB",
    "DE": "https://www.bing.com/news/search?q={query}&format=rss&mkt=de-DE",
    "ES": "https://www.bing.com/news/search?q={query}&format=rss&mkt=es-ES",
    "IT": "https://www.bing.com/news/search?q={query}&format=rss&mkt=it-IT",
}

# The 5 Alpha Verticals
VERTICALS = {
    "ai_tech": {
        "name": "IA & Tech",
        "queries": {
            "FR": ["intelligence artificielle", "OpenAI GPT", "startup tech"],
            "US": ["artificial intelligence", "OpenAI ChatGPT", "LLM AI news"],
        }
    },
    "politics": {
        "name": "Politique & Monde",
        "queries": {
            "FR": ["politique France", "Macron gouvernement", "géopolitique"],
            "US": ["US politics", "White House news", "world politics"],
        }
    },
    "finance": {
        "name": "Finance & Marchés",
        "queries": {
            "FR": ["bourse CAC 40", "économie France", "crypto bitcoin"],
            "US": ["Wall Street stocks", "Fed rates", "crypto market"],
        }
    },
    "science": {
        "name": "Science & Santé",
        "queries": {
            "FR": ["espace NASA SpaceX", "biotech santé", "climat énergie"],
            "US": ["NASA SpaceX", "biotech news", "climate science"],
        }
    },
    "culture": {
        "name": "Culture & Divertissement",
        "queries": {
            "FR": ["cinéma films", "jeux vidéo", "streaming Netflix"],
            "US": ["movies box office", "gaming news", "streaming"],
        }
    }
}


# ============================================
# CORE FUNCTIONS
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


def parse_rss(xml_content: str, max_items: int, market: str) -> list[dict]:
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
                        "source": source.text if source is not None else "Unknown",
                        "source_country": market,
                    })
        return articles
    except Exception as e:
        log.error("RSS parse failed", error=str(e))
        return []


def fetch_for_query(query: str, market: str, max_items: int = 3) -> list[dict]:
    """Fetch articles for a query in a market."""
    url = MARKETS[market].format(query=quote_plus(query))
    xml = fetch_rss(url)
    if not xml:
        return []
    return parse_rss(xml, max_items, market)


def fetch_for_vertical(vertical_id: str, include_international: bool = False) -> list[dict]:
    """Fetch articles for a vertical."""
    vertical = VERTICALS.get(vertical_id)
    if not vertical:
        return []
    
    articles = []
    seen_urls = set()
    
    # Always fetch FR
    queries_fr = vertical["queries"].get("FR", [])
    for query in queries_fr[:2]:  # Max 2 queries per market
        for article in fetch_for_query(query, "FR", 2):
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                article["vertical_id"] = vertical_id
                articles.append(article)
        time.sleep(REQUEST_DELAY)
    
    # Fetch international if enabled
    if include_international:
        queries_us = vertical["queries"].get("US", [])
        query = random.choice(queries_us) if queries_us else None
        if query:
            for article in fetch_for_query(query, "US", 2):
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    article["vertical_id"] = vertical_id
                    articles.append(article)
            time.sleep(REQUEST_DELAY)
    
    return articles[:MAX_ARTICLES_PER_VERTICAL]


def fetch_for_keyword(keyword: str, include_international: bool = False) -> list[dict]:
    """Fetch articles for a user keyword."""
    articles = []
    seen_urls = set()
    
    # FR market
    for article in fetch_for_query(keyword, "FR", 3):
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            articles.append(article)
    
    # International
    if include_international:
        time.sleep(REQUEST_DELAY)
        for market in ["US", "UK"]:
            for article in fetch_for_query(keyword, market, 1):
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    articles.append(article)
    
    return articles


# ============================================
# MAIN FETCHER
# ============================================

def run_fetcher(edition: str = "morning"):
    """Main fetcher: fetch news for all users based on their settings."""
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
    
    # Get custom keywords (user_interests)
    try:
        interests_result = supabase.table("user_interests") \
            .select("user_id, keyword") \
            .execute()
        interests_by_user = {}
        for item in (interests_result.data or []):
            uid = item["user_id"]
            if uid not in interests_by_user:
                interests_by_user[uid] = []
            interests_by_user[uid].append(item["keyword"])
    except Exception as e:
        log.warning("Failed to get interests", error=str(e))
        interests_by_user = {}
    
    total_added = 0
    
    for user in users:
        user_id = user["id"]
        include_intl = user.get("include_international", False)
        selected_verticals = user.get("selected_verticals") or {
            "ai_tech": True, "politics": True, "finance": True, "science": True, "culture": True
        }
        
        log.info("Processing user", user_id=user_id[:8], intl=include_intl)
        
        # 1. Fetch from selected verticals
        for v_id, enabled in selected_verticals.items():
            if not enabled:
                continue
            
            articles = fetch_for_vertical(v_id, include_intl)
            for article in articles:
                result = add_to_content_queue_auto(
                    user_id=user_id,
                    url=article["url"],
                    title=article["title"],
                    keyword=v_id,  # Use vertical ID as keyword
                    edition=edition,
                    source=article.get("source", "bing"),
                    source_country=article.get("source_country", "FR"),
                    vertical_id=v_id
                )
                if result:
                    total_added += 1
        
        # 2. Fetch from custom keywords
        custom_keywords = interests_by_user.get(user_id, [])
        for keyword in custom_keywords[:5]:  # Max 5 custom keywords
            articles = fetch_for_keyword(keyword, include_intl)
            for article in articles:
                result = add_to_content_queue_auto(
                    user_id=user_id,
                    url=article["url"],
                    title=article["title"],
                    keyword=keyword,
                    edition=edition,
                    source=article.get("source", "bing"),
                    source_country=article.get("source_country", "FR")
                )
                if result:
                    total_added += 1
            time.sleep(REQUEST_DELAY)
    
    elapsed = (datetime.now() - start).total_seconds()
    log.info("Fetcher complete", 
             users=len(users), 
             articles_added=total_added, 
             elapsed=round(elapsed, 1))


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
    args = parser.parse_args()
    
    if args.cleanup:
        cleanup_old()
    
    run_fetcher(edition=args.edition)


if __name__ == "__main__":
    main()
