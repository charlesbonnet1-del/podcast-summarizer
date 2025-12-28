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
        "GOOGLE_PROJECT_ID", 
        "GOOGLE_PRIVATE_KEY_ID",
        "GOOGLE_PRIVATE_KEY",
        "GOOGLE_CLIENT_EMAIL",
        "GOOGLE_CLIENT_ID"
    ]
    
    # Check all required vars exist
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        log.warning(f"Missing Google credentials: {', '.join(missing)}")
        return None
    
    # Get and fix private key (handle escaped newlines)
    private_key = os.getenv("GOOGLE_PRIVATE_KEY", "")
    # Replace literal \n with actual newlines
    private_key = private_key.replace("\\n", "\n")
    # Remove surrounding quotes if present
    if private_key.startswith('"') and private_key.endswith('"'):
        private_key = private_key[1:-1]
    if private_key.startswith("'") and private_key.endswith("'"):
        private_key = private_key[1:-1]
    
    # Validate private key format
    if not private_key.startswith("-----BEGIN"):
        log.error("GOOGLE_PRIVATE_KEY does not start with '-----BEGIN'. Check format.")
        log.error(f"Key starts with: {private_key[:50]}...")
        return None
    
    # Build credentials dict
    credentials = {
        "type": os.getenv("GOOGLE_SERVICE_ACCOUNT_TYPE", "service_account"),
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
    
    log.info("Google credentials loaded", 
             project=credentials["project_id"], 
             email=credentials["client_email"])
    
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

# V13: Updated verticals and topics (16 topics)
# ia = super-topic (IA, Robotique, Hardware)
# deals = M&A, VC, Funding rounds
VERTICALS_TOPICS = {
    "TECH": ["ia", "cyber", "deep_tech"],
    "SCIENCE": ["health", "space", "energy"],
    "ECONOMICS": ["crypto", "macro", "stocks", "deals"],
    "WORLD": ["asia", "regulation", "resources"],
    "INFLUENCE": ["info", "attention", "persuasion"],
}

# Legacy topic mappings (GSheet may still use old names)
# Maps old topic names to new ones
LEGACY_TOPIC_MAPPING = {
    "quantum": "deep_tech",
    "robotics": "ia",
    "longevity": "health",
    "cinema": "attention",
    "gaming": "attention",
    "lifestyle": "persuasion",
}

# Flat list of all supported topics (including legacy)
SUPPORTED_TOPICS = []
for topics in VERTICALS_TOPICS.values():
    SUPPORTED_TOPICS.extend(topics)
# Add legacy topics as valid
SUPPORTED_TOPICS.extend(LEGACY_TOPIC_MAPPING.keys())


def get_vertical_for_topic(topic: str) -> str | None:
    """Get the vertical name for a given topic."""
    topic_lower = topic.lower()
    for vertical, topics in VERTICALS_TOPICS.items():
        if topic_lower in [t.lower() for t in topics]:
            return vertical.lower()
    return None


class GSheetSourceLibrary:
    """
    Read and manage RSS sources from Google Sheets.
    
    Single worksheet "sources" with dynamic range A2:G (no upper limit).
    
    Column mapping (0-indexed from A2):
    A (0): vertical (WORLD, TECH, ECONOMICS, SCIENCE, CULTURE)
    B (1): topic (must be in SUPPORTED_TOPICS)
    C (2): origin (FR/INT)
    D (3): source_name
    E (4): type (Flux RSS, etc.)
    F (5): url_rss
    G (6): score (optional, default 50)
    """
    
    # Column indices (0-indexed)
    COL_VERTICAL = 0
    COL_TOPIC = 1
    COL_ORIGIN = 2
    COL_SOURCE_NAME = 3
    COL_TYPE = 4
    COL_URL_RSS = 5
    COL_SCORE = 6
    
    # Single worksheet name
    WORKSHEET_NAME = "sources"
    
    def __init__(self):
        self.client = get_gsheet_client()
        self.spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
        self.spreadsheet = None
        self.worksheet = None
        self.sheet = True  # Flag for compatibility check
        self._load_spreadsheet()
    
    def _load_spreadsheet(self):
        """Load the spreadsheet and 'sources' worksheet."""
        if not self.client or not self.spreadsheet_id:
            log.warning("GSheet client or spreadsheet_id not available")
            self.sheet = None
            return
        
        try:
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            # Get the 'sources' worksheet
            try:
                self.worksheet = self.spreadsheet.worksheet(self.WORKSHEET_NAME)
                log.info("GSheet loaded", 
                        spreadsheet_id=self.spreadsheet_id[:20] + "...",
                        worksheet=self.WORKSHEET_NAME)
            except Exception:
                # Fallback: try first worksheet
                self.worksheet = self.spreadsheet.sheet1
                log.warning("'sources' worksheet not found, using first sheet",
                           sheet_name=self.worksheet.title)
                
        except Exception as e:
            log.error("Failed to load GSheet", error=str(e))
            self.sheet = None
    
    def get_all_sources(self) -> list[dict]:
        """
        Get ALL sources from the 'sources' worksheet.
        Reads dynamically from A2:G with no upper limit.
        
        Returns:
            List of all sources with vertical, topic, origin, name, type, url, score
        """
        if not self.worksheet:
            log.warning("GSheet worksheet not loaded")
            return []
        
        try:
            # Dynamic range: A2:G (no upper limit - reads all rows)
            all_values = self.worksheet.get("A2:G")
            
            if not all_values:
                log.warning("No data found in sources worksheet")
                return []
            
            log.info("GSheet sources loaded", total_rows=len(all_values))
            
            sources = []
            for row_idx, row in enumerate(all_values, start=2):  # Start at row 2
                # Skip empty rows
                if not row or len(row) < 6:
                    continue
                
                # Extract values with safe indexing
                vertical = row[self.COL_VERTICAL].strip().upper() if len(row) > self.COL_VERTICAL else ""
                topic = row[self.COL_TOPIC].strip().lower() if len(row) > self.COL_TOPIC else ""
                origin = row[self.COL_ORIGIN].strip().upper() if len(row) > self.COL_ORIGIN else "FR"
                source_name = row[self.COL_SOURCE_NAME].strip() if len(row) > self.COL_SOURCE_NAME else ""
                source_type = row[self.COL_TYPE].strip() if len(row) > self.COL_TYPE else ""
                url_rss = row[self.COL_URL_RSS].strip() if len(row) > self.COL_URL_RSS else ""
                
                # Score with default
                try:
                    score = int(row[self.COL_SCORE]) if len(row) > self.COL_SCORE and row[self.COL_SCORE].strip() else 50
                except (ValueError, IndexError):
                    score = 50
                
                # Validate required fields
                if not url_rss or not topic:
                    continue
                
                # Map legacy topics to new ones
                if topic in LEGACY_TOPIC_MAPPING:
                    original_topic = topic
                    topic = LEGACY_TOPIC_MAPPING[topic]
                    log.debug("Mapped legacy topic", original=original_topic, mapped=topic, row=row_idx)
                
                # Validate topic is in SUPPORTED_TOPICS (after mapping)
                if topic not in [t.lower() for t in SUPPORTED_TOPICS]:
                    log.debug("Skipping unknown topic", topic=topic, row=row_idx)
                    continue
                
                sources.append({
                    "vertical": vertical,
                    "topic": topic,
                    "origin": origin,
                    "name": source_name,
                    "type": source_type,
                    "url": url_rss,
                    "score": score,
                    "row_index": row_idx
                })
            
            log.info("Valid sources found", count=len(sources))
            return sources
            
        except Exception as e:
            log.error("Failed to read GSheet sources", error=str(e))
            return []
    
    def get_sources_for_topics(self, topic_ids: list[str], origin: str = "FR") -> list[dict]:
        """
        Get RSS sources filtered by topics and origin, sorted by score.
        
        Args:
            topic_ids: List of topic IDs (must be in SUPPORTED_TOPICS)
            origin: "FR" or "INT" for international
            
        Returns:
            List of sources matching criteria, sorted by score (desc)
        """
        # Get all sources first (single API call)
        all_sources = self.get_all_sources()
        
        if not all_sources:
            return []
        
        # Normalize topic_ids to lowercase
        normalized_topics = [t.lower() for t in topic_ids]
        
        # Filter by topics and origin
        filtered = []
        for source in all_sources:
            # Check topic match
            if source["topic"] not in normalized_topics:
                continue
            
            # Check origin match
            if origin and source["origin"] != origin:
                continue
            
            filtered.append(source)
        
        # Sort by score (descending)
        filtered.sort(key=lambda x: x["score"], reverse=True)
        
        log.info("Found GSheet sources", 
                count=len(filtered), 
                origin=origin, 
                topics=normalized_topics[:5])
        
        return filtered
    
    def decrement_score(self, row_index: int, amount: int = 5):
        """Decrement source score when RSS fetch fails."""
        if not self.worksheet:
            return
        
        try:
            # Score is in column G (7th column)
            cell = f"G{row_index}"
            current = self.worksheet.acell(cell).value
            current_score = int(current) if current else 50
            new_score = max(0, current_score - amount)
            self.worksheet.update_acell(cell, new_score)
            log.debug("Score decremented", row=row_index, old=current_score, new=new_score)
        except Exception as e:
            log.warning("Failed to decrement score", error=str(e))


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
