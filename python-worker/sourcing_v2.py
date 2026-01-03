"""
Keernel Sourcing V2 - B2B Intelligence Platform

New GSheet structure:
- topic: ai, macro, asia, etc.
- source_name: Human-readable name
- tier: authority | generalist | corporate
- url_rss: RSS feed URL
- score: 0-100 quality score
- priority: 1 (MVP) | 2 (dormant) | 0 (disabled)
- language: en | fr

Key changes from V1:
- tier replaces origin for source classification
- priority filters MVP sources
- corporate sources treated as authority but capped per cluster
"""
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()


# ============================================
# CONSTANTS
# ============================================

# MVP Topics (priority=1)
MVP_TOPICS = ["ia", "macro", "asia"]

# All supported topics
ALL_TOPICS = [
    "ia", "macro", "asia",  # MVP
    "cyber", "deep_tech", "health", "space", "energy",  # Phase 2
    "crypto", "deals", "regulation", "resources",  # Phase 2
    "info", "attention", "persuasion"  # Phase 2
]

# Tier values
TIER_AUTHORITY = "authority"
TIER_GENERALIST = "generalist"
TIER_CORPORATE = "corporate"

# Legacy topic mapping
LEGACY_TOPIC_MAPPING = {
    "quantum": "deep_tech",
    "robotics": "ia",
    "longevity": "health",
    "longevity bio hacking": "health",
    "biohacking": "health",
}


# ============================================
# GOOGLE SHEETS CLIENT (reused from sourcing.py)
# ============================================

def get_gsheet_credentials() -> dict | None:
    """Build Google Service Account credentials from environment variables."""
    required_vars = [
        "GOOGLE_PROJECT_ID", 
        "GOOGLE_PRIVATE_KEY_ID",
        "GOOGLE_PRIVATE_KEY",
        "GOOGLE_CLIENT_EMAIL",
        "GOOGLE_CLIENT_ID"
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        log.warning(f"Missing Google credentials: {', '.join(missing)}")
        return None
    
    private_key = os.getenv("GOOGLE_PRIVATE_KEY", "")
    private_key = private_key.replace("\\n", "\n")
    if private_key.startswith('"') and private_key.endswith('"'):
        private_key = private_key[1:-1]
    if private_key.startswith("'") and private_key.endswith("'"):
        private_key = private_key[1:-1]
    
    if not private_key.startswith("-----BEGIN"):
        log.error("GOOGLE_PRIVATE_KEY format invalid")
        return None
    
    return {
        "type": "service_account",
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": private_key,
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GOOGLE_CLIENT_EMAIL', '').replace('@', '%40')}",
        "universe_domain": "googleapis.com"
    }


def get_gsheet_client():
    """Initialize Google Sheets client."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        creds_dict = get_gsheet_credentials()
        if not creds_dict:
            return None
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        log.info("GSheet client initialized")
        return client
        
    except Exception as e:
        log.error("Failed to init GSheet client", error=str(e))
        return None


# ============================================
# SOURCE LIBRARY V2
# ============================================

class SourceLibrary:
    """
    Read sources from Google Sheets with new V3 structure.
    
    Columns (0-indexed):
    A (0): topic
    B (1): source_name
    C (2): tier (authority/generalist/corporate)
    D (3): url_rss
    E (4): score
    F (5): priority (1=MVP, 2=dormant, 0=disabled)
    G (6): language (en/fr)
    """
    
    COL_TOPIC = 0
    COL_SOURCE_NAME = 1
    COL_TIER = 2
    COL_URL_RSS = 3
    COL_SCORE = 4
    COL_PRIORITY = 5
    COL_LANGUAGE = 6
    
    WORKSHEET_NAME = "sources"
    
    def __init__(self):
        self.client = get_gsheet_client()
        self.spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
        self.worksheet = None
        self._sources_cache = None
        self._cache_time = None
        self._cache_ttl = 300  # 5 minutes cache
        self._load_worksheet()
    
    def _load_worksheet(self):
        """Load the spreadsheet worksheet."""
        if not self.client or not self.spreadsheet_id:
            log.warning("GSheet not configured")
            return
        
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            try:
                self.worksheet = spreadsheet.worksheet(self.WORKSHEET_NAME)
            except Exception:
                self.worksheet = spreadsheet.sheet1
                log.warning("Using first sheet as fallback")
            
            log.info("GSheet worksheet loaded", worksheet=self.worksheet.title)
            
        except Exception as e:
            log.error("Failed to load GSheet", error=str(e))
    
    def _parse_row(self, row: list, row_idx: int) -> dict | None:
        """Parse a single row into a source dict."""
        if not row or len(row) < 4:
            return None
        
        def safe_get(idx: int, default: str = "") -> str:
            return row[idx].strip() if len(row) > idx and row[idx] else default
        
        topic = safe_get(self.COL_TOPIC).lower()
        source_name = safe_get(self.COL_SOURCE_NAME)
        tier = safe_get(self.COL_TIER, TIER_AUTHORITY).lower()
        url_rss = safe_get(self.COL_URL_RSS)
        language = safe_get(self.COL_LANGUAGE, "en").lower()
        
        # Parse score
        try:
            score = int(safe_get(self.COL_SCORE, "50"))
        except ValueError:
            score = 50
        
        # Parse priority
        try:
            priority = int(safe_get(self.COL_PRIORITY, "2"))
        except ValueError:
            priority = 2
        
        # Validate required fields
        if not url_rss or not topic:
            return None
        
        # Map legacy topics
        if topic in LEGACY_TOPIC_MAPPING:
            topic = LEGACY_TOPIC_MAPPING[topic]
        
        # Validate topic
        if topic not in ALL_TOPICS:
            log.warning(f"Unknown topic '{topic}' at row {row_idx}")
            return None
        
        # Validate tier
        if tier not in [TIER_AUTHORITY, TIER_GENERALIST, TIER_CORPORATE]:
            tier = TIER_AUTHORITY
        
        return {
            "topic": topic,
            "source_name": source_name,
            "tier": tier,
            "url_rss": url_rss,
            "score": score,
            "priority": priority,
            "language": language,
            "row_index": row_idx,
            # Derived flags
            "is_authority": tier in [TIER_AUTHORITY, TIER_CORPORATE],
            "is_corporate": tier == TIER_CORPORATE,
            "is_generalist": tier == TIER_GENERALIST,
        }
    
    def get_all_sources(self, use_cache: bool = True) -> list[dict]:
        """Get all sources from GSheet."""
        # Check cache
        if use_cache and self._sources_cache and self._cache_time:
            age = (datetime.now() - self._cache_time).seconds
            if age < self._cache_ttl:
                return self._sources_cache
        
        if not self.worksheet:
            return []
        
        try:
            all_values = self.worksheet.get("A2:G")
            if not all_values:
                return []
            
            sources = []
            for idx, row in enumerate(all_values, start=2):
                source = self._parse_row(row, idx)
                if source:
                    sources.append(source)
            
            # Update cache
            self._sources_cache = sources
            self._cache_time = datetime.now()
            
            log.info(f"✅ Loaded {len(sources)} sources from GSheet")
            return sources
            
        except Exception as e:
            log.error("Failed to read sources", error=str(e))
            return []
    
    def get_mvp_sources(self) -> list[dict]:
        """Get only MVP sources (priority=1)."""
        all_sources = self.get_all_sources()
        mvp = [s for s in all_sources if s["priority"] == 1]
        log.info(f"📊 MVP sources: {len(mvp)} (priority=1)")
        return mvp
    
    def get_sources_by_topic(self, topics: list[str], mvp_only: bool = True) -> list[dict]:
        """Get sources filtered by topics."""
        sources = self.get_mvp_sources() if mvp_only else self.get_all_sources()
        topics_lower = [t.lower() for t in topics]
        filtered = [s for s in sources if s["topic"] in topics_lower]
        
        # Sort by score descending
        filtered.sort(key=lambda x: x["score"], reverse=True)
        
        return filtered
    
    def get_sources_by_tier(self, tier: str, mvp_only: bool = True) -> list[dict]:
        """Get sources filtered by tier."""
        sources = self.get_mvp_sources() if mvp_only else self.get_all_sources()
        return [s for s in sources if s["tier"] == tier]
    
    def get_authority_sources(self, topics: list[str] = None, mvp_only: bool = True) -> list[dict]:
        """Get authority + corporate sources (for Radar scoring)."""
        sources = self.get_mvp_sources() if mvp_only else self.get_all_sources()
        authority = [s for s in sources if s["is_authority"]]
        
        if topics:
            topics_lower = [t.lower() for t in topics]
            authority = [s for s in authority if s["topic"] in topics_lower]
        
        return authority
    
    def get_generalist_sources(self, topics: list[str] = None, mvp_only: bool = True) -> list[dict]:
        """Get generalist sources (for Loupe validation)."""
        sources = self.get_mvp_sources() if mvp_only else self.get_all_sources()
        generalist = [s for s in sources if s["is_generalist"]]
        
        if topics:
            topics_lower = [t.lower() for t in topics]
            generalist = [s for s in generalist if s["topic"] in topics_lower]
        
        return generalist
    
    def get_stats(self) -> dict:
        """Get statistics about the source library."""
        sources = self.get_all_sources()
        mvp = [s for s in sources if s["priority"] == 1]
        
        stats = {
            "total": len(sources),
            "mvp_total": len(mvp),
            "by_tier": {},
            "by_topic": {},
            "mvp_by_tier": {},
            "mvp_by_topic": {},
        }
        
        for s in sources:
            stats["by_tier"][s["tier"]] = stats["by_tier"].get(s["tier"], 0) + 1
            stats["by_topic"][s["topic"]] = stats["by_topic"].get(s["topic"], 0) + 1
        
        for s in mvp:
            stats["mvp_by_tier"][s["tier"]] = stats["mvp_by_tier"].get(s["tier"], 0) + 1
            stats["mvp_by_topic"][s["topic"]] = stats["mvp_by_topic"].get(s["topic"], 0) + 1
        
        return stats


# ============================================
# RSS FETCHER (enhanced)
# ============================================

# Noise filter patterns
NOISE_TITLE_PATTERNS = [
    "best of", "top 10", "year in review", "predictions for",
    "most-read", "editor's pick", "newsletter", "subscribe",
    "laboratory", "research unit", "news & reports",
]

NOISE_URL_PATTERNS = [
    "/tag/", "/category/", "/author/", "/page/",
    "/newsletter", "/subscribe", "/about", "/contact",
]


def is_noise_article(title: str, url: str) -> bool:
    """Check if article is likely noise (not real news)."""
    title_lower = title.lower()
    url_lower = url.lower()
    
    # Check title patterns
    for pattern in NOISE_TITLE_PATTERNS:
        if pattern in title_lower:
            return True
    
    # Check URL patterns
    for pattern in NOISE_URL_PATTERNS:
        if pattern in url_lower:
            return True
    
    # Very short titles are suspicious
    if len(title.split()) < 4:
        return True
    
    return False


def fetch_rss_feed(
    url: str, 
    max_items: int = 10,
    max_age_hours: int = 72,
    filter_noise: bool = True
) -> list[dict]:
    """
    Fetch and parse RSS feed with noise filtering.
    
    Args:
        url: RSS feed URL
        max_items: Maximum articles to return
        max_age_hours: Filter out articles older than this
        filter_noise: Apply noise filtering
    
    Returns:
        List of articles with title, url, description, published_at
    """
    try:
        headers = {
            "User-Agent": "Keernel/2.0 Intelligence Platform",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        }
        
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        
        root = ET.fromstring(response.text)
        
        articles = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        # Try RSS 2.0
        items = root.findall(".//item")
        if not items:
            # Try Atom
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        
        for item in items:
            # Parse title
            title_elem = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            
            # Parse link
            link_elem = item.find("link")
            if link_elem is not None:
                link_url = link_elem.text or link_elem.get("href", "")
            else:
                link_elem = item.find("{http://www.w3.org/2005/Atom}link")
                link_url = link_elem.get("href", "") if link_elem is not None else ""
            
            if not title or not link_url:
                continue
            
            # Parse description
            desc_elem = (
                item.find("description") or 
                item.find("{http://www.w3.org/2005/Atom}summary") or
                item.find("{http://www.w3.org/2005/Atom}content")
            )
            description = ""
            if desc_elem is not None and desc_elem.text:
                # Strip HTML tags roughly
                import re
                description = re.sub(r'<[^>]+>', '', desc_elem.text)[:500]
            
            # Parse date
            pub_elem = item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}published")
            published_at = pub_elem.text if pub_elem is not None else None
            
            # Filter noise
            if filter_noise and is_noise_article(title, link_url):
                continue
            
            articles.append({
                "title": title,
                "url": link_url.strip(),
                "description": description,
                "published_at": published_at,
            })
            
            if len(articles) >= max_items:
                break
        
        return articles
        
    except httpx.HTTPStatusError as e:
        log.warning("RSS HTTP error", url=url[:50], status=e.response.status_code)
        return []
    except ET.ParseError:
        log.warning("RSS parse error", url=url[:50])
        return []
    except Exception as e:
        log.warning("RSS fetch failed", url=url[:50], error=str(e))
        return []


# ============================================
# FETCH ALL SOURCES
# ============================================

def fetch_all_sources(
    library: SourceLibrary,
    topics: list[str] = None,
    mvp_only: bool = True,
    max_articles_per_source: int = 10
) -> list[dict]:
    """
    Fetch articles from all sources in the library.
    
    Returns articles enriched with source metadata:
    - source_name, source_tier, source_score, topic
    """
    if topics:
        sources = library.get_sources_by_topic(topics, mvp_only=mvp_only)
    else:
        sources = library.get_mvp_sources() if mvp_only else library.get_all_sources()
    
    log.info(f"🔍 Fetching from {len(sources)} sources...")
    
    all_articles = []
    success_count = 0
    
    for source in sources:
        articles = fetch_rss_feed(
            source["url_rss"],
            max_items=max_articles_per_source,
            filter_noise=True
        )
        
        if articles:
            success_count += 1
            for article in articles:
                article.update({
                    "source_name": source["source_name"],
                    "source_tier": source["tier"],
                    "source_score": source["score"],
                    "source_is_authority": source["is_authority"],
                    "source_is_corporate": source["is_corporate"],
                    "topic": source["topic"],
                    "language": source["language"],
                })
                all_articles.append(article)
        
        # Rate limiting
        time.sleep(0.1)
    
    log.info(f"✅ Fetched {len(all_articles)} articles from {success_count}/{len(sources)} sources")
    
    return all_articles


# ============================================
# MAIN (for testing)
# ============================================

if __name__ == "__main__":
    # Test the library
    library = SourceLibrary()
    
    print("\n=== LIBRARY STATS ===")
    stats = library.get_stats()
    print(f"Total sources: {stats['total']}")
    print(f"MVP sources: {stats['mvp_total']}")
    print(f"By tier: {stats['by_tier']}")
    print(f"MVP by tier: {stats['mvp_by_tier']}")
    print(f"MVP by topic: {stats['mvp_by_topic']}")
    
    print("\n=== MVP AUTHORITY SOURCES (first 5) ===")
    auth = library.get_authority_sources(mvp_only=True)[:5]
    for s in auth:
        print(f"  [{s['topic']}] {s['source_name']} (score={s['score']})")
    
    print("\n=== FETCH TEST (asia topic) ===")
    articles = fetch_all_sources(library, topics=["asia"], max_articles_per_source=3)
    print(f"Fetched {len(articles)} articles")
    for a in articles[:5]:
        print(f"  [{a['source_tier']}] {a['title'][:50]}...")
