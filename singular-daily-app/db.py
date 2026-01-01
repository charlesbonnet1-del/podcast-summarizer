"""
Supabase client configuration for the Python worker.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("Missing Supabase configuration. Check SUPABASE_URL and SUPABASE_SERVICE_KEY.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_user_by_connection_code(code: str) -> dict | None:
    """Find a user by their 6-digit connection code."""
    result = supabase.table("users").select("*").eq("connection_code", code).execute()
    return result.data[0] if result.data else None


def get_user_by_telegram_id(telegram_chat_id: int) -> dict | None:
    """Find a user by their Telegram chat ID."""
    result = supabase.table("users").select("*").eq("telegram_chat_id", telegram_chat_id).execute()
    return result.data[0] if result.data else None


def link_telegram_to_user(user_id: str, telegram_chat_id: int) -> bool:
    """Link a Telegram chat ID to a user account."""
    try:
        supabase.table("users").update({
            "telegram_chat_id": telegram_chat_id
        }).eq("id", user_id).execute()
        return True
    except Exception as e:
        print(f"Error linking Telegram: {e}")
        return False


def add_to_content_queue(user_id: str, url: str, source_type: str, title: str = None) -> dict | None:
    """Add a new item to the content queue."""
    try:
        result = supabase.table("content_queue").insert({
            "user_id": user_id,
            "url": url,
            "source_type": source_type,
            "title": title,
            "status": "pending"
        }).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error adding to queue: {e}")
        return None


def get_pending_content(user_id: str) -> list:
    """Get all pending content for a user."""
    result = supabase.table("content_queue").select("*").eq("user_id", user_id).eq("status", "pending").order("created_at").execute()
    return result.data or []


def update_content_status(content_id: str, status: str, processed_content: str = None, error_message: str = None) -> bool:
    """Update the status of a content queue item."""
    try:
        update_data = {"status": status}
        if processed_content:
            update_data["processed_content"] = processed_content
        if error_message:
            update_data["error_message"] = error_message
        
        supabase.table("content_queue").update(update_data).eq("id", content_id).execute()
        return True
    except Exception as e:
        print(f"Error updating content status: {e}")
        return False


def create_episode(user_id: str, title: str, summary_text: str, audio_url: str, audio_duration: int, sources_data: list) -> dict | None:
    """Create a new episode record with sources_data for Show Notes."""
    try:
        result = supabase.table("episodes").insert({
            "user_id": user_id,
            "title": title,
            "summary_text": summary_text,
            "audio_url": audio_url,
            "audio_duration": audio_duration,
            "sources_data": sources_data
        }).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error creating episode: {e}")
        return None


def upload_audio_file(user_id: str, file_path: str, filename: str) -> str | None:
    """Upload an audio file to Supabase Storage and return the public URL."""
    try:
        storage_path = f"{user_id}/{filename}"
        
        with open(file_path, "rb") as f:
            supabase.storage.from_("episodes").upload(
                storage_path,
                f,
                file_options={"content-type": "audio/mpeg"}
            )
        
        # Get public URL
        public_url = supabase.storage.from_("episodes").get_public_url(storage_path)
        return public_url
    except Exception as e:
        print(f"Error uploading audio: {e}")
        return None


def get_user_settings(user_id: str) -> dict | None:
    """Get user settings for episode generation."""
    result = supabase.table("users").select("default_duration, voice_id").eq("id", user_id).execute()
    return result.data[0] if result.data else None


# ============================================
# USER INTERESTS (Sourcing Dynamique)
# ============================================

def add_user_interest(user_id: str, keyword: str) -> dict | None:
    """Add a keyword interest for a user."""
    try:
        # Normalize keyword (lowercase, strip)
        keyword = keyword.strip().lower()
        
        result = supabase.table("user_interests").insert({
            "user_id": user_id,
            "keyword": keyword
        }).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        # Handle duplicate keyword error gracefully
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return {"error": "duplicate", "keyword": keyword}
        print(f"Error adding interest: {e}")
        return None


def get_user_interests(user_id: str) -> list:
    """Get all keyword interests for a user."""
    result = supabase.table("user_interests").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return result.data or []


def remove_user_interest(user_id: str, keyword: str) -> bool:
    """Remove a keyword interest for a user."""
    try:
        keyword = keyword.strip().lower()
        result = supabase.table("user_interests").delete().eq("user_id", user_id).eq("keyword", keyword).execute()
        return len(result.data) > 0 if result.data else False
    except Exception as e:
        print(f"Error removing interest: {e}")
        return False


def get_all_active_keywords() -> list:
    """Get all unique keywords from all users."""
    try:
        # Get all keywords from user_interests
        interests_result = supabase.table("user_interests").select("keyword, user_id").execute()
        
        if not interests_result.data:
            return []
        
        # Group keywords with their user_ids
        keyword_users = {}
        for item in interests_result.data:
            kw = item["keyword"]
            if kw not in keyword_users:
                keyword_users[kw] = []
            keyword_users[kw].append(item["user_id"])
        
        return [{"keyword": k, "user_ids": v} for k, v in keyword_users.items()]
    except Exception as e:
        print(f"Error getting active keywords: {e}")
        return []


# Mapping from GSheet vertical names to Supabase vertical IDs
# New V2 structure: WORLD, TECH, ECONOMICS, SCIENCE, CULTURE
VERTICAL_MAPPING = {
    # GSheet values (case-insensitive) -> Supabase IDs
    # TECH vertical
    "tech": "tech",
    "ia&tech": "tech",
    "ia tech": "tech",
    "ai_tech": "tech",
    # WORLD vertical
    "world": "world",
    "monde": "world",
    "politique": "world",  # Legacy mapping
    "politics": "world",   # Legacy mapping
    # ECONOMICS vertical (new, replaces finance)
    "economics": "economics",
    "finance": "economics",  # Legacy mapping
    "économie": "economics",
    # SCIENCE vertical
    "science": "science",
    # CULTURE vertical
    "culture": "culture",
}


def add_to_content_queue_auto(user_id: str, url: str, title: str, keyword: str, edition: str, source: str = "bing_news", source_name: str = None, source_country: str = "FR", vertical_id: str = None) -> dict | None:
    """Add a news item to the content queue from automatic fetching.
    Checks for duplicates before inserting.
    
    V17: Supports global queue with user_id="global" → uses first real user
    
    Args:
        user_id: User ID or "global" for global queue
        source: Source type (gsheet_rss, bing_news, manual, etc.)
        source_name: Display name of the media (e.g., "Le Monde", "TechCrunch") - optional
    """
    try:
        # V17: Handle global queue - get first real user from DB
        if user_id is None or user_id == "global":
            try:
                first_user = supabase.table("users").select("id").limit(1).execute()
                if first_user.data:
                    user_id = first_user.data[0]["id"]
                else:
                    print("Error: No users in database for global queue")
                    return None
            except Exception as e:
                print(f"Error getting user for global queue: {e}")
                return None
        
        # Check if URL already exists (any status)
        existing = supabase.table("content_queue") \
            .select("id") \
            .eq("url", url) \
            .execute()
        
        if existing.data:
            # Already exists, skip silently
            return None
        
        # Build insert data
        insert_data = {
            "user_id": user_id,
            "url": url,
            "title": title,
            "source_type": "article",
            "source": source,
            "source_country": source_country,
            "keyword": keyword,
            "edition": edition,
            "priority": "normal",
            "status": "pending"
        }
        
        # Add source_name if provided (media display name)
        # Note: Column must exist in DB - run migration first
        # Skipped silently if column doesn't exist to avoid breaking fetcher
        if source_name:
            insert_data["source_name"] = source_name
        
        # Normalize and map vertical_id
        if vertical_id:
            # Normalize: lowercase, strip
            normalized = vertical_id.lower().strip()
            # Map to Supabase ID
            mapped_id = VERTICAL_MAPPING.get(normalized)
            if mapped_id:
                insert_data["vertical_id"] = mapped_id
            # If not in mapping, don't include vertical_id (let it be NULL)
        
        # Try insert with source_name first
        try:
            result = supabase.table("content_queue").insert(insert_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            # If source_name column doesn't exist, retry without it
            if "source_name" in str(e) and "source_name" in insert_data:
                del insert_data["source_name"]
                result = supabase.table("content_queue").insert(insert_data).execute()
                return result.data[0] if result.data else None
            raise
            
    except Exception as e:
        print(f"Error adding auto content: {e}")
        return None
