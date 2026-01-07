"""
RSS Health Check - Vérifie toutes les sources et colorie en rouge celles qui échouent dans GSheet.

Usage:
    python rss_health_check.py          # Check MVP sources
    python rss_health_check.py --all    # Check all sources
    python rss_health_check.py --dry-run # Don't update GSheet

API:
    POST /api/health-check/rss  # Trigger from server
"""
import os
import time
from datetime import datetime
import xml.etree.ElementTree as ET

import httpx
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import structlog

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

SPREADSHEET_ID = os.getenv("SOURCES_SPREADSHEET_ID") or os.getenv("GOOGLE_SPREADSHEET_ID")
SHEET_NAME = "sources"  # Nom de l'onglet

# Couleurs (Google Sheets format: 0-1 range)
COLOR_RED = {"red": 1, "green": 0.8, "blue": 0.8}      # Rouge clair pour erreurs
COLOR_ORANGE = {"red": 1, "green": 0.9, "blue": 0.7}   # Orange pour warnings
COLOR_WHITE = {"red": 1, "green": 1, "blue": 1}        # Blanc (reset)
COLOR_GREEN = {"red": 0.85, "green": 1, "blue": 0.85}  # Vert clair pour OK


# ============================================
# GOOGLE SHEETS AUTH
# ============================================

def get_gsheet_client():
    """Initialize Google Sheets client."""
    required_vars = [
        "GOOGLE_PROJECT_ID", 
        "GOOGLE_PRIVATE_KEY_ID",
        "GOOGLE_PRIVATE_KEY",
        "GOOGLE_CLIENT_EMAIL",
        "GOOGLE_CLIENT_ID"
    ]
    
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise ValueError(f"Missing env vars: {missing}")
    
    private_key = os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")
    if private_key.startswith('"') and private_key.endswith('"'):
        private_key = private_key[1:-1]
    
    creds_dict = {
        "type": "service_account",
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": private_key,
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


# ============================================
# RSS CHECK
# ============================================

def check_rss_feed(url: str, timeout: int = 15) -> tuple[bool, str]:
    """
    Check if an RSS feed is accessible and valid.
    
    Returns:
        (success: bool, error_message: str or None)
    """
    if not url or not url.startswith("http"):
        return False, "Invalid URL"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, application/atom+xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        
        # Try to parse as XML
        root = ET.fromstring(response.text)
        
        # Check if it has RSS or Atom items
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        
        if not items:
            return False, "No items found"
        
        return True, None
        
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}"
    except httpx.TimeoutException:
        return False, "Timeout"
    except httpx.ConnectError:
        return False, "Connection failed"
    except ET.ParseError as e:
        return False, f"Parse error"
    except Exception as e:
        error = str(e)[:30]
        return False, error


# ============================================
# MAIN HEALTH CHECK
# ============================================

def run_health_check(only_mvp: bool = True, update_sheet: bool = True, topics: list = None):
    """
    Run health check on all RSS feeds and update GSheet colors.
    
    Args:
        only_mvp: Only check sources with priority=1
        update_sheet: If True, update colors in GSheet
        topics: Optional list of topics to filter (e.g., ["ia", "macro", "asia", "general"])
    """
    print("🔍 RSS Health Check")
    print("=" * 50)
    
    # Connect to GSheet
    client = get_gsheet_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(SHEET_NAME)
    
    # Get all data
    all_data = worksheet.get_all_records()
    print(f"📊 Found {len(all_data)} total sources in GSheet")
    
    # Track results
    results = {
        "ok": [],
        "error": [],
        "skipped": []
    }
    
    # Stats by topic and tier
    stats = {
        "by_topic": {},
        "by_tier": {}
    }
    
    # Batch updates for colors
    color_updates = []
    
    for i, row in enumerate(all_data):
        row_num = i + 2  # +2 because header is row 1
        
        url = row.get("url_rss", "")
        priority = row.get("priority", 0)
        name = row.get("source_name", f"Row {row_num}")
        topic = row.get("topic", "unknown")
        tier = row.get("tier", "unknown")
        
        # Convert priority to int if it's a string
        try:
            priority = int(priority) if priority else 0
        except (ValueError, TypeError):
            priority = 0
        
        # Skip non-MVP if requested
        if only_mvp and priority != 1:
            results["skipped"].append(name)
            continue
        
        # Skip if topic filter is set and doesn't match
        if topics and topic.lower() not in [t.lower() for t in topics]:
            results["skipped"].append(name)
            continue
        
        # Skip empty URLs
        if not url or not url.startswith("http"):
            results["skipped"].append(name)
            continue
        
        # Check RSS
        print(f"  [{topic}/{tier}] {name[:35]}...", end=" ", flush=True)
        success, error = check_rss_feed(url)
        
        # Track stats
        if topic not in stats["by_topic"]:
            stats["by_topic"][topic] = {"ok": 0, "error": 0}
        if tier not in stats["by_tier"]:
            stats["by_tier"][tier] = {"ok": 0, "error": 0}
        
        if success:
            print("✅ OK")
            results["ok"].append({"name": name, "topic": topic, "tier": tier})
            stats["by_topic"][topic]["ok"] += 1
            stats["by_tier"][tier]["ok"] += 1
            color = COLOR_GREEN
        else:
            print(f"❌ {error}")
            results["error"].append({"name": name, "error": error, "url": url, "topic": topic, "tier": tier})
            stats["by_topic"][topic]["error"] += 1
            stats["by_tier"][tier]["error"] += 1
            color = COLOR_RED
        
        # Prepare color update for the entire row
        if update_sheet:
            color_updates.append({
                "row_num": row_num,
                "color": color
            })
        
        # Rate limiting
        time.sleep(0.2)
    
    # Apply color updates in batch
    if update_sheet and color_updates:
        print("\n📝 Updating GSheet colors...")
        
        # Use batch update for efficiency
        requests = []
        for update in color_updates:
            row_num = update["row_num"]
            color = update["color"]
            
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": worksheet.id,
                        "startRowIndex": row_num - 1,
                        "endRowIndex": row_num,
                        "startColumnIndex": 0,
                        "endColumnIndex": 10
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })
        
        # Execute batch update
        if requests:
            spreadsheet.batch_update({"requests": requests})
            print(f"  ✅ Updated {len(requests)} rows")
    
    # Print summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    print(f"✅ OK: {len(results['ok'])}")
    print(f"❌ Errors: {len(results['error'])}")
    print(f"⏭️ Skipped: {len(results['skipped'])}")
    
    # Stats by topic
    print("\n📁 By Topic:")
    for topic, counts in sorted(stats["by_topic"].items()):
        total = counts["ok"] + counts["error"]
        pct = (counts["ok"] / total * 100) if total > 0 else 0
        print(f"  {topic}: {counts['ok']}/{total} OK ({pct:.0f}%)")
    
    # Stats by tier
    print("\n🏷️ By Tier:")
    for tier, counts in sorted(stats["by_tier"].items()):
        total = counts["ok"] + counts["error"]
        pct = (counts["ok"] / total * 100) if total > 0 else 0
        print(f"  {tier}: {counts['ok']}/{total} OK ({pct:.0f}%)")
    
    # List errors
    if results["error"]:
        print("\n❌ Failed sources:")
        for err in results["error"][:20]:
            print(f"  • [{err['topic']}/{err['tier']}] {err['name']}: {err['error']}")
        if len(results["error"]) > 20:
            print(f"  ... and {len(results['error']) - 20} more")
    
    return results


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import sys
    
    only_mvp = "--all" not in sys.argv
    dry_run = "--dry-run" in sys.argv
    
    print(f"Mode: {'MVP only' if only_mvp else 'All sources'}")
    print(f"Update sheet: {not dry_run}")
    
    run_health_check(only_mvp=only_mvp, update_sheet=not dry_run)
