"""
Keernel Article Fetcher - Fresh + Archive Architecture

Fetches articles from RSS sources with:
- Parallel HTTP requests (10 concurrent)
- Batch processing (150 sources per batch)
- Embeddings generated at fetch time
- Source fetch status tracking for rotation

V1: 2026-01-11 - Initial implementation
"""
import os
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
import xml.etree.ElementTree as ET

import httpx
import structlog
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

# Parallel fetch settings
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT = 15  # seconds
BATCH_SIZE = 150  # sources per batch

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds

# Freshness settings
FRESH_HOURS = 48  # Articles are "fresh" for 48 hours

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Noise filters (from sourcing.py)
NOISE_TITLE_WORDS = {
    "home", "subscribe", "subscription", "contact", "login", "careers",
    "consultant", "sign up", "sign in", "register", "newsletter", "cookie",
    "privacy policy", "terms of service", "404", "page not found",
    "accueil", "inscription", "connexion", "mentions légales",
    "politique de confidentialité"
}

NOISE_URL_PATTERNS = [
    "/home", "/about", "/subscribe", "/contact", "/careers", "/login",
    "/signin", "/signup", "/register", "/newsletter", "/privacy", "/terms",
    "/cookie", "/404", "/search", "/tag/", "/category/", "/author/",
    "/page/", "/feed/", "/rss/", "/sitemap", "/wp-admin", "/wp-login"
]

MIN_TITLE_WORDS = 4


# ============================================
# SUPABASE CLIENT
# ============================================

def get_supabase() -> Client:
    """Get Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
    return create_client(url, key)


# ============================================
# EMBEDDING GENERATION
# ============================================

def generate_embedding(text: str) -> list[float] | None:
    """
    Generate embedding for text using OpenAI.
    Returns 1536-dim vector or None on failure.
    """
    try:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            log.warning("OpenAI API key not available")
            return None

        client = OpenAI(api_key=api_key)

        # Truncate to avoid token limits (~8k tokens for embedding model)
        text = text[:8000]

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )

        return response.data[0].embedding

    except Exception as e:
        log.error("Embedding generation failed", error=str(e))
        return None


def generate_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """
    Generate embeddings for multiple texts in a single API call.
    Returns list of embeddings (None for failures).
    """
    if not texts:
        return []

    try:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            log.warning("OpenAI API key not available")
            return [None] * len(texts)

        client = OpenAI(api_key=api_key)

        # Truncate texts
        truncated = [t[:8000] for t in texts]

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=truncated
        )

        # Map response to original order
        embeddings = [None] * len(texts)
        for item in response.data:
            embeddings[item.index] = item.embedding

        return embeddings

    except Exception as e:
        log.error("Batch embedding generation failed", error=str(e))
        return [None] * len(texts)


# ============================================
# NOISE FILTER
# ============================================

def is_noise_article(title: str, url: str) -> bool:
    """
    Check if an article is likely noise.
    Returns True if should be filtered out.
    """
    title_lower = title.lower().strip()
    url_lower = url.lower()

    # Empty title
    if not title_lower:
        return True

    # Title too short
    if len(title_lower.split()) < MIN_TITLE_WORDS:
        return True

    # Navigation words in title
    for noise_word in NOISE_TITLE_WORDS:
        if noise_word in title_lower:
            return True

    # URL patterns for non-article pages
    for pattern in NOISE_URL_PATTERNS:
        if pattern in url_lower:
            return True

    return False


# ============================================
# RSS PARSING
# ============================================

def parse_rss_content(xml_content: str, source_name: str, source_url: str, topic: str) -> list[dict]:
    """
    Parse RSS/Atom XML content.
    Returns list of article dicts.
    """
    articles = []

    try:
        root = ET.fromstring(xml_content)

        # Try RSS 2.0 format
        items = root.findall(".//item")
        if not items:
            # Try Atom format
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in items:
            # RSS 2.0
            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")
            pub_date_elem = item.find("pubDate")

            # Atom fallback
            if link_elem is None:
                link_elem = item.find("{http://www.w3.org/2005/Atom}link")
                if link_elem is not None:
                    link_url = link_elem.get("href")
                else:
                    link_url = None
            else:
                link_url = link_elem.text

            if title_elem is None:
                title_elem = item.find("{http://www.w3.org/2005/Atom}title")

            if desc_elem is None:
                desc_elem = item.find("{http://www.w3.org/2005/Atom}summary")

            title = title_elem.text if title_elem is not None else None
            description = desc_elem.text if desc_elem is not None else ""

            if not title or not link_url:
                continue

            # Skip noise
            if is_noise_article(title, link_url):
                continue

            # Parse publication date
            published_at = None
            if pub_date_elem is not None and pub_date_elem.text:
                try:
                    from email.utils import parsedate_to_datetime
                    published_at = parsedate_to_datetime(pub_date_elem.text)
                except Exception:
                    pass

            articles.append({
                "url": link_url.strip(),
                "title": title.strip(),
                "description": (description or "")[:500].strip(),
                "source_name": source_name,
                "source_url": source_url,
                "topic": topic,
                "published_at": published_at
            })

    except ET.ParseError as e:
        log.debug("RSS parse error", error=str(e), source=source_name)
    except Exception as e:
        log.debug("RSS parsing failed", error=str(e), source=source_name)

    return articles


# ============================================
# ASYNC RSS FETCHING
# ============================================

async def fetch_single_rss(
    client: httpx.AsyncClient,
    source: dict,
    semaphore: asyncio.Semaphore
) -> dict:
    """
    Fetch a single RSS feed with rate limiting.

    Returns:
        {
            "source": source dict,
            "success": bool,
            "articles": list,
            "error": str or None
        }
    """
    async with semaphore:
        source_name = source.get("source_name", "Unknown")
        source_url = source.get("source_url", "")
        topic = source.get("topic", "general")

        result = {
            "source": source,
            "success": False,
            "articles": [],
            "error": None
        }

        if not source_url:
            result["error"] = "No URL"
            return result

        headers = {
            "User-Agent": "Keernel/2.0 RSS Reader",
            "Accept": "application/rss+xml, application/xml, text/xml"
        }

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(
                    source_url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=True
                )

                if response.status_code >= 400:
                    result["error"] = f"HTTP {response.status_code}"
                    continue

                # Check if looks like RSS
                content = response.text[:500].lower()
                if not any(marker in content for marker in ['<rss', '<feed', '<?xml', '<channel']):
                    result["error"] = "Not RSS content"
                    break  # Don't retry - wrong content type

                # Parse RSS
                articles = parse_rss_content(
                    response.text,
                    source_name,
                    source_url,
                    topic
                )

                result["success"] = True
                result["articles"] = articles
                result["error"] = None
                break

            except httpx.TimeoutException:
                result["error"] = "Timeout"
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF[attempt])

            except Exception as e:
                result["error"] = str(e)[:100]
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF[attempt])

        return result


async def fetch_sources_parallel(sources: list[dict]) -> list[dict]:
    """
    Fetch multiple RSS sources in parallel.

    Args:
        sources: List of source dicts with source_name, source_url, topic

    Returns:
        List of fetch results
    """
    if not sources:
        return []

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_single_rss(client, source, semaphore)
            for source in sources
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "source": sources[i],
                    "success": False,
                    "articles": [],
                    "error": str(result)[:100]
                })
            else:
                processed_results.append(result)

        return processed_results


# ============================================
# SOURCE SYNC (GSheet → Supabase)
# ============================================

def sync_sources_from_gsheet(supabase: Client) -> int:
    """
    Sync RSS sources from GSheet to source_fetch_status table.
    Only adds new sources (upsert on source_name).

    Returns:
        Number of sources synced
    """
    try:
        from sourcing import GSheetSourceLibrary

        library = GSheetSourceLibrary()
        all_sources = library.get_all_sources()

        if not all_sources:
            log.warning("No sources found in GSheet")
            return 0

        synced = 0
        for source in all_sources:
            try:
                # Upsert source
                supabase.table("source_fetch_status").upsert({
                    "source_name": source["name"],
                    "source_url": source["url"],
                    "topic": source["topic"],
                }, on_conflict="source_name").execute()
                synced += 1
            except Exception as e:
                log.debug("Source sync error", source=source["name"], error=str(e))

        log.info(f"✅ Synced {synced}/{len(all_sources)} sources from GSheet")
        return synced

    except Exception as e:
        log.error("GSheet sync failed", error=str(e))
        return 0


# ============================================
# MAIN FETCH BATCH FUNCTION
# ============================================

def fetch_and_store_batch(batch_size: int = BATCH_SIZE) -> dict:
    """
    Fetch a batch of sources and store articles.

    This is the main entry point for the cron job.

    Flow:
    1. Get sources due for fetch (oldest first)
    2. Fetch RSS feeds in parallel
    3. Generate embeddings for new articles
    4. Store articles in DB
    5. Update source fetch status

    Returns:
        {
            "sources_fetched": int,
            "articles_found": int,
            "articles_new": int,
            "errors": int
        }
    """
    supabase = get_supabase()

    stats = {
        "sources_fetched": 0,
        "articles_found": 0,
        "articles_new": 0,
        "errors": 0
    }

    # Step 1: Get sources to fetch
    try:
        result = supabase.rpc("get_sources_to_fetch", {"batch_size": batch_size}).execute()
        sources = result.data or []
    except Exception as e:
        # If function doesn't exist, fall back to direct query
        log.warning("get_sources_to_fetch RPC failed, using direct query", error=str(e))
        result = supabase.table("source_fetch_status") \
            .select("source_name, source_url, topic, last_fetched_at, consecutive_failures") \
            .neq("status", "broken") \
            .order("next_fetch_at") \
            .limit(batch_size) \
            .execute()
        sources = result.data or []

    if not sources:
        log.info("No sources due for fetch")
        # Try syncing from GSheet if no sources
        sync_sources_from_gsheet(supabase)
        return stats

    log.info(f"📡 Fetching {len(sources)} sources...")

    # Step 2: Fetch RSS feeds in parallel
    fetch_results = asyncio.run(fetch_sources_parallel(sources))

    # Step 3: Collect all articles and prepare for storage
    all_articles = []
    source_updates = []

    for result in fetch_results:
        source = result["source"]
        source_name = source.get("source_name", "Unknown")

        stats["sources_fetched"] += 1

        if result["success"]:
            articles = result["articles"]
            stats["articles_found"] += len(articles)
            all_articles.extend(articles)

            # Prepare success update
            source_updates.append({
                "source_name": source_name,
                "success": True,
                "article_count": len(articles),
                "error": None
            })
        else:
            stats["errors"] += 1

            # Prepare failure update
            source_updates.append({
                "source_name": source_name,
                "success": False,
                "article_count": 0,
                "error": result.get("error", "Unknown error")
            })

    # Step 4: Deduplicate articles by URL
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        url = article.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)

    log.info(f"📰 Found {len(unique_articles)} unique articles (from {len(all_articles)} total)")

    # Step 5: Check which articles are new (not in DB)
    if unique_articles:
        urls = [a["url"] for a in unique_articles]

        # Query existing URLs in batches (Supabase has limits)
        existing_urls = set()
        for i in range(0, len(urls), 100):
            batch_urls = urls[i:i+100]
            result = supabase.table("articles") \
                .select("url") \
                .in_("url", batch_urls) \
                .execute()
            existing_urls.update(r["url"] for r in (result.data or []))

        new_articles = [a for a in unique_articles if a["url"] not in existing_urls]
        log.info(f"🆕 {len(new_articles)} new articles to store")
    else:
        new_articles = []

    # Step 6 & 7: Generate embeddings and store in SMALL BATCHES to save memory
    CHUNK_SIZE = 50  # Process 50 articles at a time

    if new_articles:
        for chunk_start in range(0, len(new_articles), CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, len(new_articles))
            chunk = new_articles[chunk_start:chunk_end]

            log.info(f"📦 Processing chunk {chunk_start//CHUNK_SIZE + 1}: articles {chunk_start+1}-{chunk_end}")

            # Generate embeddings for this chunk only
            texts = [
                f"{a['title']}. {a.get('description', '')}"
                for a in chunk
            ]
            chunk_embeddings = generate_embeddings_batch(texts)

            # Store this chunk immediately
            for i, article in enumerate(chunk):
                try:
                    insert_data = {
                        "url": article["url"],
                        "title": article["title"],
                        "description": article.get("description"),
                        "source_name": article["source_name"],
                        "source_url": article.get("source_url"),
                        "topic": article["topic"],
                        "published_at": article.get("published_at").isoformat() if article.get("published_at") else None,
                    }

                    # Add embedding if available
                    if i < len(chunk_embeddings) and chunk_embeddings[i]:
                        insert_data["embedding"] = chunk_embeddings[i]

                    supabase.table("articles").insert(insert_data).execute()
                    stats["articles_new"] += 1

                except Exception as e:
                    # Handle duplicate URL conflict silently
                    if "duplicate" not in str(e).lower() and "unique" not in str(e).lower():
                        log.debug("Article insert failed", url=article["url"][:50], error=str(e))

            # Clear chunk from memory
            del chunk_embeddings
            del texts

        log.info(f"✅ Stored {stats['articles_new']} articles")

    # Step 8: Update source fetch status
    now = datetime.now(timezone.utc)
    for update in source_updates:
        try:
            source_name = update["source_name"]

            # First, get current stats
            current = supabase.table("source_fetch_status") \
                .select("consecutive_failures, total_fetches, successful_fetches, failed_fetches, avg_articles_per_fetch") \
                .eq("source_name", source_name) \
                .execute()

            if not current.data:
                continue

            current_data = current.data[0]
            total_fetches = current_data.get("total_fetches", 0) + 1
            avg_articles = current_data.get("avg_articles_per_fetch", 0)

            if update["success"]:
                # Success: reset failures, update stats
                successful_fetches = current_data.get("successful_fetches", 0) + 1

                # Update running average of articles per fetch
                article_count = update.get("article_count", 0)
                if avg_articles == 0:
                    new_avg = float(article_count)
                else:
                    # Exponential moving average (weight recent more)
                    new_avg = 0.3 * article_count + 0.7 * avg_articles

                # Next fetch in 15 minutes (working sources get regular schedule)
                next_fetch = now + timedelta(minutes=15)

                supabase.table("source_fetch_status").update({
                    "last_fetched_at": now.isoformat(),
                    "next_fetch_at": next_fetch.isoformat(),
                    "consecutive_failures": 0,
                    "last_error": None,
                    "status": "working",
                    "total_fetches": total_fetches,
                    "successful_fetches": successful_fetches,
                    "avg_articles_per_fetch": new_avg,
                    "updated_at": now.isoformat()
                }).eq("source_name", source_name).execute()

            else:
                # Failure: increment failures, apply backoff
                failures = current_data.get("consecutive_failures", 0) + 1
                failed_fetches = current_data.get("failed_fetches", 0) + 1

                # Backoff: 15min, 30min, 1h, 2h, 4h, 8h, then mark broken
                backoff_minutes = [15, 30, 60, 120, 240, 480]
                if failures >= len(backoff_minutes):
                    # Mark as broken after 6 consecutive failures
                    status = "broken"
                    next_fetch = now + timedelta(days=7)  # Check again in a week
                else:
                    status = "unknown"
                    next_fetch = now + timedelta(minutes=backoff_minutes[failures])

                supabase.table("source_fetch_status").update({
                    "last_fetched_at": now.isoformat(),
                    "next_fetch_at": next_fetch.isoformat(),
                    "consecutive_failures": failures,
                    "last_error": update.get("error"),
                    "status": status,
                    "total_fetches": total_fetches,
                    "failed_fetches": failed_fetches,
                    "updated_at": now.isoformat()
                }).eq("source_name", source_name).execute()

        except Exception as e:
            log.debug("Source status update failed", source=update["source_name"], error=str(e))

    log.info(f"✅ Fetch complete: {stats['sources_fetched']} sources, {stats['articles_new']} new articles, {stats['errors']} errors")

    return stats


# ============================================
# FRESH ARTICLES QUERY
# ============================================

def get_fresh_articles(hours_back: int = FRESH_HOURS, topic: str = None) -> list[dict]:
    """
    Get fresh articles (fetched within hours_back).

    Args:
        hours_back: How many hours to look back
        topic: Optional topic filter

    Returns:
        List of article dicts with embeddings
    """
    supabase = get_supabase()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    query = supabase.table("articles") \
        .select("id, url, title, description, content, embedding, source_name, topic, published_at, fetched_at") \
        .gte("fetched_at", cutoff.isoformat()) \
        .not_.is_("embedding", "null") \
        .order("fetched_at", desc=True)

    if topic:
        query = query.eq("topic", topic)

    result = query.execute()

    return result.data or []


# ============================================
# ARCHIVE CONTEXT SEARCH
# ============================================

def find_archive_context(
    cluster_embedding: list[float],
    exclude_urls: list[str],
    max_results: int = 2,
    min_similarity: float = 0.7,
    max_age_days: int = 90
) -> list[dict]:
    """
    Find archive articles similar to a cluster centroid.

    Args:
        cluster_embedding: Centroid vector of the cluster
        exclude_urls: URLs already in the cluster (to exclude)
        max_results: Max archive articles to return
        min_similarity: Minimum cosine similarity
        max_age_days: Max age of archive articles

    Returns:
        List of archive articles with similarity scores
    """
    supabase = get_supabase()

    try:
        result = supabase.rpc("find_archive_context", {
            "cluster_centroid": cluster_embedding,
            "exclude_urls": exclude_urls,
            "max_results": max_results,
            "min_similarity": min_similarity,
            "max_age_days": max_age_days
        }).execute()

        return result.data or []

    except Exception as e:
        log.error("Archive context search failed", error=str(e))
        return []


# ============================================
# CLUSTER DEDUPLICATION
# ============================================

def is_cluster_used(article_urls: list[str], days_back: int = 7) -> bool:
    """
    Check if a cluster was already used recently.

    Args:
        article_urls: List of article URLs in the cluster
        days_back: How far back to check

    Returns:
        True if cluster was already used
    """
    supabase = get_supabase()

    try:
        result = supabase.rpc("is_cluster_used", {
            "article_urls_to_check": article_urls,
            "days_back": days_back
        }).execute()

        return result.data or False

    except Exception as e:
        log.error("Cluster check failed", error=str(e))
        return False


def mark_cluster_used(article_urls: list[str], topic: str, representative_title: str) -> str | None:
    """
    Mark a cluster as used.

    Args:
        article_urls: List of article URLs in the cluster
        topic: Cluster topic
        representative_title: Title representing the cluster

    Returns:
        Cluster ID or None on failure
    """
    supabase = get_supabase()

    try:
        result = supabase.rpc("mark_cluster_used", {
            "p_article_urls": article_urls,
            "p_topic": topic,
            "p_representative_title": representative_title
        }).execute()

        return result.data

    except Exception as e:
        log.error("Mark cluster failed", error=str(e))
        return None


# ============================================
# CLI ENTRY POINT
# ============================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "sync":
            # Sync sources from GSheet
            supabase = get_supabase()
            count = sync_sources_from_gsheet(supabase)
            print(f"Synced {count} sources")

        elif command == "fetch":
            # Fetch a batch
            batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else BATCH_SIZE
            stats = fetch_and_store_batch(batch_size)
            print(f"Fetched: {stats}")

        elif command == "fresh":
            # Get fresh articles
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else FRESH_HOURS
            articles = get_fresh_articles(hours)
            print(f"Found {len(articles)} fresh articles")
            for a in articles[:5]:
                print(f"  - [{a['topic']}] {a['title'][:60]}...")

        else:
            print(f"Unknown command: {command}")
            print("Usage: python article_fetcher.py [sync|fetch|fresh] [args]")
    else:
        # Default: run a fetch batch
        print("Running fetch batch...")
        stats = fetch_and_store_batch()
        print(f"Done: {stats}")
