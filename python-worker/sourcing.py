"""
Keernel Sourcing Module

Multi-level content sourcing:
- Level 1: Manual URLs from user (highest priority)
- Level 2: GSheet RSS library + Newsletter webhooks
- Level 3: Bing News (fallback)

Also provides verified historical facts from Wikimedia API.
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Optional
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, quote_plus

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()

# ============================================
# GOOGLE SHEETS CLIENT
# ============================================

def get_gsheet_credentials() -> dict | None:
    """Build Google Service Account credentials from environment variables."""
    required_vars = [
        "GOOGLE_SERVICE_ACCOUNT_TYPE",
        "GOOGLE_PROJECT_ID", 
        "GOOGLE_PRIVATE_KEY_ID",
        "GOOGLE_PRIVATE_KEY",
        "GOOGLE_CLIENT_EMAIL",
        "GOOGLE_CLIENT_ID"
    ]
    
    # Check all required vars exist
    for var in required_vars:
        if not os.getenv(var):
            log.warning(f"Missing Google credential: {var}")
            return None
    
    # Build credentials dict
    credentials = {
        "type": os.getenv("GOOGLE_SERVICE_ACCOUNT_TYPE", "service_account"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n"),
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GOOGLE_CLIENT_EMAIL', '').replace('@', '%40')}",
        "universe_domain": "googleapis.com"
    }
    
    return credentials


def get_gsheet_client():
    """Initialize Google Sheets client with service account."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        creds_dict = get_gsheet_credentials()
        if not creds_dict:
            log.warning("Google Sheets credentials not configured")
            return None
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        
        log.info("Google Sheets client initialized")
        return client
        
    except ImportError:
        log.error("gspread not installed. Run: pip install gspread google-auth")
        return None
    except Exception as e:
        log.error("Failed to initialize GSheet client", error=str(e))
        return None


# ============================================
# GSHEET SOURCE LIBRARY
# ============================================

class GSheetSourceLibrary:
    """
    Read and manage RSS sources from Google Sheets.
    
    Expected columns:
    A: Verticale (ai_tech, politics, finance, science, culture)
    B: Topic (llm, hardware, france, usa, etc.)
    C: Origin (FR/INT)
    D: Source_Name
    E: Source_Type (rss, twitter, youtube)
    F: Description
    G: URL_RSS
    H: Score (0-100, higher = more trusted)
    """
    
    def __init__(self):
        self.client = get_gsheet_client()
        self.spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
        self.sheet = None
        self._load_sheet()
    
    def _load_sheet(self):
        """Load the spreadsheet."""
        if not self.client or not self.spreadsheet_id:
            return
        
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            self.sheet = spreadsheet.sheet1  # First sheet
            log.info("GSheet loaded", spreadsheet_id=self.spreadsheet_id)
        except Exception as e:
            log.error("Failed to load GSheet", error=str(e))
    
    def get_sources_for_topics(self, topic_ids: list[str], origin: str = "FR") -> list[dict]:
        """
        Get RSS sources for given topics, sorted by score.
        
        Args:
            topic_ids: List of topic IDs (e.g., ["llm", "france", "crypto"])
            origin: "FR" or "INT" for international
            
        Returns:
            List of sources with url, name, score, vertical, topic
        """
        if not self.sheet:
            return []
        
        try:
            # Get all records
            records = self.sheet.get_all_records()
            
            sources = []
            for row in records:
                topic = str(row.get("Topic", "")).lower().strip()
                row_origin = str(row.get("Origin", "FR")).upper().strip()
                url = str(row.get("URL_RSS", "")).strip()
                score = int(row.get("Score", 50))
                
                # Filter by topic and origin
                if topic in topic_ids and row_origin == origin and url:
                    sources.append({
                        "url": url,
                        "name": row.get("Source_Name", "Unknown"),
                        "score": score,
                        "vertical": row.get("Verticale", ""),
                        "topic": topic,
                        "source_type": row.get("Source_Type", "rss"),
                        "row_index": records.index(row) + 2  # +2 for header and 0-index
                    })
            
            # Sort by score (highest first)
            sources.sort(key=lambda x: x["score"], reverse=True)
            
            log.info("Found GSheet sources", count=len(sources), topics=topic_ids)
            return sources
            
        except Exception as e:
            log.error("Failed to get GSheet sources", error=str(e))
            return []
    
    def decrement_score(self, row_index: int, amount: int = 5):
        """Decrement score for a source (e.g., after RSS fetch error)."""
        if not self.sheet:
            return
        
        try:
            # Column H is score (column 8)
            current_score = self.sheet.cell(row_index, 8).value
            new_score = max(0, int(current_score or 50) - amount)
            self.sheet.update_cell(row_index, 8, new_score)
            log.info("Decremented source score", row=row_index, new_score=new_score)
        except Exception as e:
            log.error("Failed to update score", error=str(e))


# ============================================
# RSS FETCHER
# ============================================

def fetch_rss_feed(url: str, max_items: int = 5) -> list[dict]:
    """
    Fetch and parse RSS feed.
    
    Returns list of articles with title, url, published_at, description.
    """
    try:
        headers = {
            "User-Agent": "Keernel/1.0 RSS Reader",
            "Accept": "application/rss+xml, application/xml, text/xml"
        }
        
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(response.text)
        
        articles = []
        
        # Try RSS 2.0 format
        items = root.findall(".//item")
        if not items:
            # Try Atom format
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        
        for item in items[:max_items]:
            # RSS 2.0
            title = item.find("title")
            link = item.find("link")
            description = item.find("description")
            pub_date = item.find("pubDate")
            
            # Atom fallback
            if link is None:
                link = item.find("{http://www.w3.org/2005/Atom}link")
                if link is not None:
                    link_url = link.get("href")
                else:
                    link_url = None
            else:
                link_url = link.text
            
            if title is not None and link_url:
                articles.append({
                    "title": title.text or "Untitled",
                    "url": link_url,
                    "description": (description.text or "")[:500] if description is not None else "",
                    "published_at": pub_date.text if pub_date is not None else None
                })
        
        return articles
        
    except httpx.HTTPStatusError as e:
        log.warning("RSS fetch HTTP error", url=url[:50], status=e.response.status_code)
        return []
    except ET.ParseError:
        log.warning("RSS parse error (invalid XML)", url=url[:50])
        return []
    except Exception as e:
        log.warning("RSS fetch failed", url=url[:50], error=str(e))
        return []


# ============================================
# WIKIMEDIA "ON THIS DAY" API
# ============================================

def get_historical_facts_wikimedia(
    month: int = None, 
    day: int = None, 
    language: str = "fr",
    max_facts: int = 3
) -> list[dict]:
    """
    Fetch verified historical facts from Wikimedia "On This Day" API.
    
    Returns list of facts with year, text, and optional Wikipedia links.
    Filters for tech/science/finance relevant events.
    """
    if month is None or day is None:
        now = datetime.now()
        month = now.month
        day = now.day
    
    user_agent = os.getenv("WIKIMEDIA_USER_AGENT", "Keernel/1.0")
    
    # Wikimedia REST API endpoint
    url = f"https://api.wikimedia.org/feed/v1/wikipedia/{language}/onthisday/all/{month:02d}/{day:02d}"
    
    try:
        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json"
        }
        
        response = httpx.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        facts = []
        
        # Priority keywords for tech/finance relevance
        tech_keywords = [
            "ordinateur", "computer", "internet", "satellite", "fusée", "rocket",
            "espace", "space", "nasa", "apple", "microsoft", "google", "ibm",
            "téléphone", "phone", "radio", "télévision", "television",
            "bourse", "stock", "banque", "bank", "économie", "economy",
            "invention", "découverte", "discovery", "scientifique", "scientist",
            "prix nobel", "nobel prize", "physique", "physics", "chimie", "chemistry",
            "aviation", "avion", "aircraft", "vol", "flight"
        ]
        
        # Process "events" (historical events)
        events = data.get("events", []) + data.get("selected", [])
        
        for event in events:
            year = event.get("year")
            text = event.get("text", "")
            
            if not year or not text:
                continue
            
            # Check relevance (tech/science/finance keywords)
            text_lower = text.lower()
            is_relevant = any(kw in text_lower for kw in tech_keywords)
            
            # Get Wikipedia link if available
            pages = event.get("pages", [])
            wiki_url = None
            if pages:
                wiki_url = pages[0].get("content_urls", {}).get("desktop", {}).get("page")
            
            facts.append({
                "year": year,
                "text": text,
                "wiki_url": wiki_url,
                "is_tech_relevant": is_relevant
            })
        
        # Sort: tech-relevant first, then by year (most recent first for modern tech)
        facts.sort(key=lambda x: (not x["is_tech_relevant"], -x["year"] if x["year"] > 1900 else x["year"]))
        
        log.info("Fetched Wikimedia facts", date=f"{month}/{day}", total=len(facts))
        return facts[:max_facts]
        
    except Exception as e:
        log.error("Wikimedia API failed", error=str(e))
        return []


def get_best_ephemeride_fact(month: int = None, day: int = None) -> dict | None:
    """
    Get the single best historical fact for the ephemeride.
    Prioritizes tech/science/finance relevance.
    """
    facts = get_historical_facts_wikimedia(month, day, max_facts=5)
    
    if not facts:
        return None
    
    # Return the first (already sorted by relevance)
    best = facts[0]
    
    log.info("Selected ephemeride fact", year=best["year"], relevant=best["is_tech_relevant"])
    return best


# ============================================
# BING NEWS (FALLBACK - Level 3)
# ============================================

BING_MARKETS = {
    "FR": "https://www.bing.com/news/search?q={query}&format=rss&mkt=fr-FR",
    "US": "https://www.bing.com/news/search?q={query}&format=rss&mkt=en-US",
}

def fetch_bing_news(query: str, market: str = "FR", max_items: int = 3) -> list[dict]:
    """Fetch news from Bing News RSS (fallback source)."""
    url_template = BING_MARKETS.get(market, BING_MARKETS["FR"])
    url = url_template.format(query=quote_plus(query))
    
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        
        root = ET.fromstring(response.text)
        articles = []
        
        for item in root.findall(".//item")[:max_items]:
            title = item.find("title")
            link = item.find("link")
            
            if title is not None and link is not None:
                # Extract real URL from Bing redirect
                real_url = link.text
                if "bing.com" in real_url:
                    from urllib.parse import parse_qs
                    parsed = urlparse(real_url)
                    params = parse_qs(parsed.query)
                    if "url" in params:
                        real_url = params["url"][0]
                
                articles.append({
                    "title": title.text or "Untitled",
                    "url": real_url,
                    "source": "bing_news"
                })
        
        return articles
        
    except Exception as e:
        log.warning("Bing News fetch failed", query=query, error=str(e))
        return []


# ============================================
# NEWSLETTER WEBHOOK HANDLER
# ============================================

def parse_cloudmailin_webhook(payload: dict) -> dict | None:
    """
    Parse Cloudmailin webhook payload for newsletter content.
    
    Expected payload structure (Cloudmailin JSON format):
    {
        "envelope": {"from": "...", "to": "..."},
        "headers": {"subject": "...", "from": "..."},
        "plain": "text content",
        "html": "html content"
    }
    """
    try:
        headers = payload.get("headers", {})
        subject = headers.get("subject", "Newsletter")
        sender = headers.get("from", "unknown")
        
        # Get content (prefer plain text)
        content = payload.get("plain", "") or ""
        if not content:
            # Extract text from HTML if no plain text
            html = payload.get("html", "")
            if html:
                # Simple HTML stripping (for production, use BeautifulSoup)
                import re
                content = re.sub(r'<[^>]+>', ' ', html)
                content = re.sub(r'\s+', ' ', content).strip()
        
        if not content:
            log.warning("Empty newsletter content")
            return None
        
        return {
            "title": subject,
            "content": content[:10000],  # Limit content
            "source": sender,
            "source_type": "newsletter",
            "priority": "high",
            "received_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        log.error("Failed to parse newsletter webhook", error=str(e))
        return None


# ============================================
# UNIFIED SOURCING FUNCTION
# ============================================

def fetch_content_for_user(
    user_id: str,
    topic_ids: list[str],
    manual_urls: list[str] = None,
    target_duration_min: int = 20,
    include_international: bool = False
) -> dict:
    """
    Unified sourcing function with 3-level hierarchy.
    
    Returns:
        {
            "level1_manual": [...],  # Deep dives from user URLs
            "level2_library": [...],  # From GSheet RSS library
            "level3_backup": [...],   # From Bing News
            "ephemeride": {...}       # Historical fact
        }
    """
    result = {
        "level1_manual": [],
        "level2_library": [],
        "level3_backup": [],
        "ephemeride": None
    }
    
    # Estimate content needs (150 words/min, ~3 articles per 5 min)
    target_articles = max(3, target_duration_min // 5)
    
    # Level 1: Manual URLs (already in content_queue, just pass through)
    if manual_urls:
        result["level1_manual"] = [{"url": url, "priority": "high"} for url in manual_urls]
        target_articles -= len(manual_urls)
    
    # Level 2: GSheet RSS Library
    if target_articles > 0 and topic_ids:
        library = GSheetSourceLibrary()
        sources = library.get_sources_for_topics(topic_ids, origin="FR")
        
        if include_international:
            sources += library.get_sources_for_topics(topic_ids, origin="INT")
        
        for source in sources[:10]:  # Max 10 RSS feeds
            articles = fetch_rss_feed(source["url"], max_items=2)
            
            if not articles:
                # RSS failed, decrement score
                library.decrement_score(source["row_index"], amount=5)
                continue
            
            for article in articles:
                article["source_name"] = source["name"]
                article["score"] = source["score"]
                article["vertical"] = source["vertical"]
                result["level2_library"].append(article)
            
            if len(result["level2_library"]) >= target_articles:
                break
            
            time.sleep(0.5)  # Rate limiting
    
    # Level 3: Bing News (fallback)
    remaining = target_articles - len(result["level2_library"])
    if remaining > 0 and topic_ids:
        # Map topic IDs to search queries
        topic_queries = {
            "llm": "intelligence artificielle LLM",
            "hardware": "semiconducteurs GPU",
            "robotics": "robotique",
            "france": "politique France",
            "usa": "politique USA",
            "international": "géopolitique monde",
            "stocks": "bourse CAC 40",
            "crypto": "bitcoin crypto",
            "macro": "économie mondiale",
            "space": "espace NASA SpaceX",
            "health": "santé médecine",
            "energy": "énergie climat",
            "cinema": "cinéma films",
            "gaming": "jeux vidéo",
            "lifestyle": "tendances mode"
        }
        
        for topic_id in topic_ids[:3]:
            query = topic_queries.get(topic_id, topic_id)
            articles = fetch_bing_news(query, market="FR", max_items=2)
            
            for article in articles:
                article["source_name"] = "Bing News"
                article["score"] = 30  # Lower score for backup
                result["level3_backup"].append(article)
            
            if len(result["level3_backup"]) >= remaining:
                break
    
    # Ephemeride (historical fact)
    result["ephemeride"] = get_best_ephemeride_fact()
    
    log.info("Sourcing complete", 
             level1=len(result["level1_manual"]),
             level2=len(result["level2_library"]),
             level3=len(result["level3_backup"]),
             has_ephemeride=result["ephemeride"] is not None)
    
    return result
