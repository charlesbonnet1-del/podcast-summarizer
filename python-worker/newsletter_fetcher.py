"""
Keernel Newsletter Fetcher

Fetches newsletters from Gmail, extracts article links,
and stores them in the articles table.

OAuth credentials are stored as base64 in environment variables:
- GOOGLE_OAUTH_CREDENTIALS_JSON: OAuth client credentials
- GOOGLE_OAUTH_TOKEN_PICKLE: Authenticated token

V1: 2026-01-11 - Initial implementation
"""
import os
import re
import base64
import pickle
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs, unquote
import html

import httpx
import structlog
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

# Gmail fetch settings
MAX_EMAILS_PER_BATCH = 20
MAX_LINKS_PER_EMAIL = 10

# Link filtering
EXCLUDED_DOMAINS = {
    # Tracking & unsubscribe
    "mailchimp.com", "list-manage.com", "substack.com",
    "beehiiv.com", "convertkit.com", "mailgun.com",
    "sendgrid.net", "klaviyo.com", "hubspot.com",
    # Social media (not articles)
    "twitter.com", "x.com", "facebook.com", "linkedin.com",
    "instagram.com", "youtube.com", "tiktok.com",
    # Generic
    "google.com", "apple.com", "microsoft.com",
}

EXCLUDED_URL_PATTERNS = [
    "/unsubscribe", "/manage-preferences", "/view-in-browser",
    "/preferences", "/optout", "/opt-out", "/profile",
    "utm_source=", "click.convertkit", "trk.klclick",
]

# Article domains (prioritize these)
ARTICLE_DOMAINS = {
    "techcrunch.com", "theverge.com", "arstechnica.com", "wired.com",
    "bloomberg.com", "reuters.com", "nytimes.com", "wsj.com",
    "theguardian.com", "bbc.com", "lemonde.fr", "lesechos.fr",
    "ft.com", "economist.com", "therecord.media", "krebsonsecurity.com",
    "spacenews.com", "nasaspaceflight.com", "ieee.org", "nature.com",
    "science.org", "technologyreview.com", "venturebeat.com",
}


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
# GMAIL OAUTH CREDENTIALS
# ============================================

def get_gmail_credentials():
    """
    Load Gmail OAuth credentials from base64-encoded environment variables.

    Returns:
        google.oauth2.credentials.Credentials object
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        # Get base64-encoded token from environment
        token_b64 = os.getenv("GOOGLE_OAUTH_TOKEN_PICKLE")
        if not token_b64:
            log.error("GOOGLE_OAUTH_TOKEN_PICKLE not set")
            return None

        # Decode and load pickle
        token_bytes = base64.b64decode(token_b64)
        creds = pickle.loads(token_bytes)

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            log.info("Refreshing expired Gmail token...")
            creds.refresh(Request())

            # Update the environment variable with new token
            # (In production, you'd want to persist this)
            new_token_b64 = base64.b64encode(pickle.dumps(creds)).decode()
            log.info("Token refreshed successfully")

        return creds

    except Exception as e:
        log.error(f"Failed to load Gmail credentials: {e}")
        return None


def get_gmail_service():
    """
    Build Gmail API service.

    Returns:
        googleapiclient.discovery.Resource
    """
    try:
        from googleapiclient.discovery import build

        creds = get_gmail_credentials()
        if not creds:
            return None

        service = build('gmail', 'v1', credentials=creds)
        return service

    except Exception as e:
        log.error(f"Failed to build Gmail service: {e}")
        return None


# ============================================
# EMAIL FETCHING
# ============================================

def fetch_unread_emails(service, max_results: int = MAX_EMAILS_PER_BATCH) -> list[dict]:
    """
    Fetch unread emails from Gmail.

    Returns:
        List of email dicts with id, subject, from, html_body
    """
    emails = []

    try:
        # List unread messages
        results = service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        log.info(f"📬 Found {len(messages)} unread emails")

        for msg_info in messages:
            msg_id = msg_info['id']

            try:
                # Get full message
                msg = service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='full'
                ).execute()

                # Extract headers
                headers = {h['name'].lower(): h['value'] for h in msg['payload']['headers']}
                subject = headers.get('subject', 'No Subject')
                from_email = headers.get('from', '')
                date_str = headers.get('date', '')

                # Parse date
                received_at = None
                if date_str:
                    try:
                        received_at = parsedate_to_datetime(date_str)
                    except:
                        pass

                # Extract HTML body
                html_body = extract_html_body(msg['payload'])

                if html_body:
                    emails.append({
                        'id': msg_id,
                        'subject': subject,
                        'from': from_email,
                        'received_at': received_at,
                        'html_body': html_body
                    })

            except Exception as e:
                log.warning(f"Failed to fetch email {msg_id}: {e}")
                continue

        return emails

    except Exception as e:
        log.error(f"Failed to list emails: {e}")
        return []


def extract_html_body(payload: dict) -> str | None:
    """
    Extract HTML body from Gmail message payload.
    Handles multipart messages.
    """
    if 'body' in payload and payload['body'].get('data'):
        mime_type = payload.get('mimeType', '')
        if 'html' in mime_type:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')

    if 'parts' in payload:
        for part in payload['parts']:
            # Recurse into nested parts
            result = extract_html_body(part)
            if result:
                return result

            # Check this part
            mime_type = part.get('mimeType', '')
            if 'html' in mime_type and part.get('body', {}).get('data'):
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')

    return None


def mark_email_as_read(service, msg_id: str):
    """Mark an email as read."""
    try:
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
    except Exception as e:
        log.warning(f"Failed to mark email {msg_id} as read: {e}")


# ============================================
# LINK EXTRACTION
# ============================================

def extract_article_links(html_body: str, newsletter_from: str) -> list[dict]:
    """
    Extract article links from newsletter HTML.

    Returns:
        List of dicts with url, title (link text)
    """
    links = []
    seen_urls = set()

    try:
        soup = BeautifulSoup(html_body, 'html.parser')

        # Find all links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()

            # Skip empty or javascript links
            if not href or href.startswith('javascript:') or href.startswith('#'):
                continue

            # Unwrap tracking URLs
            clean_url = unwrap_tracking_url(href)
            if not clean_url:
                continue

            # Check if it's an article link
            if not is_article_link(clean_url):
                continue

            # Deduplicate
            url_key = clean_url.split('?')[0]  # Remove query params for dedup
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)

            # Extract link text as title
            link_text = a_tag.get_text(strip=True)
            if len(link_text) < 10:
                link_text = None  # Too short to be a title

            links.append({
                'url': clean_url,
                'title': link_text,
                'newsletter_from': newsletter_from
            })

            if len(links) >= MAX_LINKS_PER_EMAIL:
                break

        return links

    except Exception as e:
        log.error(f"Failed to extract links: {e}")
        return []


def unwrap_tracking_url(url: str) -> str | None:
    """
    Unwrap tracking/redirect URLs to get the real article URL.

    Handles:
    - Substack redirects
    - Mailchimp tracking
    - Generic ?url= parameters
    """
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        # Common redirect parameters
        for param in ['url', 'redirect', 'target', 'dest', 'link', 'u']:
            if param in query:
                return unquote(query[param][0])

        # Substack redirect pattern
        if 'substack.com' in parsed.netloc and '/redirect' in parsed.path:
            if 'r' in query:
                # Base64 encoded in some cases
                try:
                    return base64.b64decode(query['r'][0]).decode()
                except:
                    pass

        # If no redirect found, return original URL
        return url

    except Exception as e:
        log.debug(f"URL unwrap failed: {e}")
        return url


def is_article_link(url: str) -> bool:
    """
    Check if a URL looks like an article link.

    Returns:
        True if likely an article, False otherwise
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        path = parsed.path.lower()

        # Skip excluded domains
        for excluded in EXCLUDED_DOMAINS:
            if excluded in domain:
                return False

        # Skip excluded patterns
        url_lower = url.lower()
        for pattern in EXCLUDED_URL_PATTERNS:
            if pattern in url_lower:
                return False

        # Must have a path (not just homepage)
        if path in ['', '/', '/index.html']:
            return False

        # Prefer known article domains
        for article_domain in ARTICLE_DOMAINS:
            if article_domain in domain:
                return True

        # Generic heuristics for article URLs
        # - Has date-like pattern in path
        # - Has /article/, /news/, /post/, /blog/ in path
        article_patterns = [
            r'/\d{4}/\d{2}/',  # /2024/01/
            r'/article/', r'/news/', r'/post/', r'/blog/',
            r'/story/', r'/p/', r'/s/',
            r'\.html$', r'\.htm$',
        ]

        for pattern in article_patterns:
            if re.search(pattern, path):
                return True

        # If domain is not excluded and has a decent path, accept it
        if len(path) > 10 and '/' in path[1:]:
            return True

        return False

    except Exception as e:
        log.debug(f"Link check failed: {e}")
        return False


# ============================================
# ENGAGEMENT SIMULATION
# ============================================

def load_tracking_pixels(html_body: str):
    """
    Load tracking pixels to simulate email open.
    This helps stay on newsletter lists.
    """
    try:
        soup = BeautifulSoup(html_body, 'html.parser')

        # Find 1x1 images (tracking pixels)
        for img in soup.find_all('img'):
            src = img.get('src', '')
            width = img.get('width', '')
            height = img.get('height', '')

            # Likely a tracking pixel
            if (width == '1' and height == '1') or 'track' in src.lower() or 'open' in src.lower():
                try:
                    httpx.get(src, timeout=5, follow_redirects=True)
                except:
                    pass

    except Exception as e:
        log.debug(f"Tracking pixel load failed: {e}")


def click_first_link(links: list[dict]):
    """
    Click on the first article link to simulate engagement.
    """
    if not links:
        return

    try:
        url = links[0]['url']
        httpx.get(url, timeout=10, follow_redirects=True)
        log.debug(f"Clicked first link: {url[:50]}...")
    except:
        pass


# ============================================
# ARTICLE STORAGE
# ============================================

def store_newsletter_articles(
    supabase: Client,
    links: list[dict],
    newsletter_subject: str,
    newsletter_from: str
) -> int:
    """
    Store extracted links in the articles table.

    Returns:
        Number of new articles stored
    """
    stored = 0

    for link in links:
        try:
            url = link['url']
            title = link.get('title') or newsletter_subject

            # Check if URL already exists
            existing = supabase.table("articles") \
                .select("id") \
                .eq("url", url) \
                .execute()

            if existing.data:
                continue  # Skip duplicate

            # Infer topic from newsletter sender or content
            topic = infer_topic_from_newsletter(newsletter_from, title)

            # Insert article
            supabase.table("articles").insert({
                "url": url,
                "title": title[:500],
                "description": f"From newsletter: {newsletter_subject[:200]}",
                "source_name": extract_sender_name(newsletter_from),
                "source_type": "newsletter",
                "topic": topic,
                "published_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            stored += 1

        except Exception as e:
            if "duplicate" not in str(e).lower():
                log.debug(f"Failed to store article: {e}")

    return stored


def extract_sender_name(from_header: str) -> str:
    """Extract readable name from email From header."""
    # "Newsletter Name <email@example.com>" -> "Newsletter Name"
    if '<' in from_header:
        return from_header.split('<')[0].strip().strip('"')
    return from_header.split('@')[0]


def infer_topic_from_newsletter(from_email: str, title: str) -> str:
    """
    Infer topic from newsletter sender or title.

    Returns:
        Topic slug (ia, cyber, space, etc.) or 'general'
    """
    text = f"{from_email} {title}".lower()

    topic_keywords = {
        "ia": ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic"],
        "cyber": ["security", "cyber", "hack", "breach", "malware", "ransomware", "krebs"],
        "space": ["space", "nasa", "spacex", "rocket", "satellite", "orbit", "mars", "moon"],
        "crypto": ["crypto", "bitcoin", "ethereum", "blockchain", "web3", "defi"],
        "health": ["health", "biotech", "pharma", "medical", "longevity", "gene"],
        "energy": ["energy", "climate", "solar", "wind", "battery", "nuclear", "oil"],
        "deep_tech": ["quantum", "semiconductor", "chip", "hardware", "robotics"],
        "deals": ["funding", "acquisition", "ipo", "venture", "startup", "raised"],
        "macro": ["economy", "fed", "inflation", "gdp", "markets", "finance"],
    }

    for topic, keywords in topic_keywords.items():
        for kw in keywords:
            if kw in text:
                return topic

    return "general"


# ============================================
# MAIN FETCH FUNCTION
# ============================================

def fetch_and_store_newsletters() -> dict:
    """
    Main entry point: fetch newsletters and store articles.

    Returns:
        {
            "emails_processed": int,
            "articles_found": int,
            "articles_new": int,
            "errors": int
        }
    """
    stats = {
        "emails_processed": 0,
        "articles_found": 0,
        "articles_new": 0,
        "errors": 0
    }

    # Get Gmail service
    service = get_gmail_service()
    if not service:
        log.error("❌ Gmail service not available")
        stats["errors"] = 1
        return stats

    # Get Supabase client
    supabase = get_supabase()

    # Fetch unread emails
    emails = fetch_unread_emails(service)

    for email in emails:
        try:
            msg_id = email['id']
            subject = email['subject']
            from_email = email['from']
            html_body = email['html_body']

            log.info(f"📧 Processing: {subject[:50]}...")

            # Load tracking pixels (engagement)
            load_tracking_pixels(html_body)

            # Extract article links
            links = extract_article_links(html_body, from_email)
            stats["articles_found"] += len(links)

            # Click first link (engagement)
            click_first_link(links)

            # Store articles
            if links:
                new_count = store_newsletter_articles(
                    supabase, links, subject, from_email
                )
                stats["articles_new"] += new_count

            # Mark as read
            mark_email_as_read(service, msg_id)
            stats["emails_processed"] += 1

            log.info(f"✅ {subject[:30]}: {len(links)} links, {new_count if links else 0} new")

        except Exception as e:
            log.error(f"❌ Failed to process email: {e}")
            stats["errors"] += 1

    log.info(f"📬 Newsletter fetch complete: {stats['emails_processed']} emails, {stats['articles_new']} new articles")

    return stats


# ============================================
# CLI ENTRY POINT
# ============================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test-auth":
        # Test Gmail authentication
        service = get_gmail_service()
        if service:
            print("✅ Gmail authentication OK")
            # List 1 email to verify
            results = service.users().messages().list(userId='me', maxResults=1).execute()
            print(f"📬 Found {results.get('resultSizeEstimate', 0)} emails in inbox")
        else:
            print("❌ Gmail authentication failed")
    else:
        # Run full fetch
        stats = fetch_and_store_newsletters()
        print(f"Done: {stats}")
