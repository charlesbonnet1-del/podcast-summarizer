"""
RSS Health Check - Vérifie toutes les sources et colorie en rouge celles qui échouent dans GSheet.

Usage:
    python rss_health_check.py

Prérequis:
    - Variables d'environnement Google (GOOGLE_PROJECT_ID, GOOGLE_PRIVATE_KEY, etc.)
    - SOURCES_SPREADSHEET_ID
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

SPREADSHEET_ID = os.getenv("SOURCES_SPREADSHEET_ID")
SHEET_NAME = "sources"  # Nom de l'onglet

# Couleurs
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
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing Google credentials: {', '.join(missing)}")
    
    private_key = os.getenv("GOOGLE_PRIVATE_KEY", "")
    private_key = private_key.replace("\\n", "\n")
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
            "User-Agent": "Keernel/2.0 RSS Health Check",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
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
    except ET.ParseError:
        return False, "Parse error"
    except httpx.ConnectError:
        return False, "Connection failed"
    except Exception as e:
        error = str(e)[:30]
        return False, error


# ============================================
# MAIN HEALTH CHECK
# ============================================

def run_health_check(only_mvp: bool = True, update_sheet: bool = True):
    """
    Run health check on all RSS feeds and update GSheet colors.
    
    Args:
        only_mvp: Only check sources with priority=1
        update_sheet: If True, update colors in GSheet
    """
    print("🔍 RSS Health Check")
    print("=" * 50)
    
    # Connect to GSheet
    client = get_gsheet_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(SHEET_NAME)
    
    # Get all data
    all_data = worksheet.get_all_records()
    print(f"📊 Found {len(all_data)} sources")
    
    # Find column indices (1-indexed for GSheet)
    headers = worksheet.row_values(1)
    url_col = headers.index("url_rss") + 1 if "url_rss" in headers else None
    priority_col = headers.index("priority") + 1 if "priority" in headers else None
    name_col = headers.index("source_name") + 1 if "source_name" in headers else None
    
    if not url_col:
        raise ValueError("Column 'url_rss' not found in sheet")
    
    # Track results
    results = {
        "ok": [],
        "error": [],
        "skipped": []
    }
    
    # Batch updates for colors
    color_updates = []
    
    for i, row in enumerate(all_data):
        row_num = i + 2  # +2 because header is row 1
        
        url = row.get("url_rss", "")
        priority = row.get("priority", 0)
        name = row.get("source_name", f"Row {row_num}")
        
        # Skip non-MVP if requested
        if only_mvp and priority != 1:
            results["skipped"].append(name)
            continue
        
        # Check RSS
        print(f"  Checking: {name[:40]}...", end=" ", flush=True)
        success, error = check_rss_feed(url)
        
        if success:
            print("✅ OK")
            results["ok"].append(name)
            color = COLOR_GREEN
        else:
            print(f"❌ {error}")
            results["error"].append({"name": name, "error": error, "url": url})
            color = COLOR_RED
        
        # Prepare color update for the entire row
        if update_sheet:
            color_updates.append({
                "range": f"A{row_num}:Z{row_num}",
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
            # Parse range to get row
            row_match = update["range"].split(":")[0]
            row_num = int(''.join(filter(str.isdigit, row_match)))
            
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": worksheet.id,
                        "startRowIndex": row_num - 1,
                        "endRowIndex": row_num,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers)
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": update["color"]
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })
        
        # Execute batch update
        if requests:
            spreadsheet.batch_update({"requests": requests})
            print("✅ Colors updated!")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print(f"  ✅ OK: {len(results['ok'])}")
    print(f"  ❌ Errors: {len(results['error'])}")
    print(f"  ⏭️  Skipped: {len(results['skipped'])}")
    
    if results["error"]:
        print("\n❌ FAILED SOURCES:")
        for err in results["error"]:
            print(f"  • {err['name']}: {err['error']}")
            print(f"    URL: {err['url'][:60]}...")
    
    return results


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RSS Health Check - Vérifie les sources et colorie le GSheet")
    parser.add_argument("--all", action="store_true", help="Vérifier toutes les sources (pas seulement MVP)")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas modifier le GSheet")
    
    args = parser.parse_args()
    
    run_health_check(
        only_mvp=not args.all,
        update_sheet=not args.dry_run
    )
