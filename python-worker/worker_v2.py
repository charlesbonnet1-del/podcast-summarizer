"""
Keernel Worker V2 - Lego Architecture

CHANGEMENTS MAJEURS V2:
1. Phantom User Guardrail: Skip génération si inactif > 3 jours
2. Segments mutualisés: Cache audio par topic/date/edition
3. Nouveaux formats: Flash (4min) / Digest (15min)
4. Assemblage Lego: Intro + Segments cachés + Outro
"""
import os
import argparse
from datetime import datetime, timedelta, timezone
import structlog
from dotenv import load_dotenv

from db import supabase
from stitcher_v2 import assemble_lego_podcast

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION V2
# ============================================

PHANTOM_USER_DAYS = 3  # Jours d'inactivité avant skip
FORMAT_DURATIONS = {
    "flash": 4,    # ~4 minutes
    "digest": 15   # ~15 minutes
}

# ============================================
# PHANTOM USER GUARDRAIL
# ============================================

def is_user_active(user_id: str, max_inactive_days: int = PHANTOM_USER_DAYS) -> bool:
    """
    Vérifie si l'utilisateur a écouté un épisode récemment.
    
    Returns:
        True si actif (< max_inactive_days sans écoute)
        False si inactif (> max_inactive_days)
    """
    try:
        result = supabase.table("users") \
            .select("last_listened_at, created_at") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if not result.data:
            return False
        
        last_listened = result.data.get("last_listened_at")
        created_at = result.data.get("created_at")
        
        # Si jamais écouté, utiliser created_at
        if not last_listened:
            # Nouvel utilisateur: on génère pour lui donner sa chance
            # Mais pas plus de 7 jours après inscription
            if created_at:
                created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                days_since_signup = (datetime.now(timezone.utc) - created).days
                if days_since_signup > 7:
                    log.info("User never listened, signup > 7 days", user_id=user_id[:8])
                    return False
            return True
        
        # Calculer jours depuis dernière écoute
        last = datetime.fromisoformat(last_listened.replace('Z', '+00:00'))
        days_inactive = (datetime.now(timezone.utc) - last).days
        
        if days_inactive > max_inactive_days:
            log.info("User inactive", user_id=user_id[:8], days_inactive=days_inactive)
            return False
        
        return True
        
    except Exception as e:
        log.error("Failed to check user activity", user_id=user_id[:8], error=str(e))
        # En cas d'erreur, on génère quand même
        return True


def get_user_format(user_id: str) -> tuple[str, int]:
    """
    Récupère le format préféré de l'utilisateur.
    
    Returns:
        (format_name, duration_minutes)
    """
    try:
        result = supabase.table("users") \
            .select("preferred_format") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if result.data:
            format_name = result.data.get("preferred_format", "digest")
            duration = FORMAT_DURATIONS.get(format_name, 15)
            return format_name, duration
        
        return "digest", 15
        
    except Exception as e:
        log.warning("Failed to get user format", error=str(e))
        return "digest", 15


def send_ondemand_notification(user_id: str):
    """
    Envoie une notification "Votre briefing est prêt" 
    au lieu de générer pour un utilisateur inactif.
    
    TODO: Implémenter avec email/push notification
    """
    log.info("Would send on-demand notification", user_id=user_id[:8])
    
    # Marquer l'utilisateur comme "notified" aujourd'hui
    try:
        supabase.table("users") \
            .update({"last_notified_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", user_id) \
            .execute()
    except:
        pass


# ============================================
# PROCESS USER (V2)
# ============================================

def process_user_queue_v2(user_id: str, force: bool = False) -> dict | None:
    """
    Process pending content for a user with V2 Lego architecture.
    
    Args:
        user_id: User ID
        force: If True, bypass phantom user check
        
    Returns:
        Created episode or None
    """
    log.info("Processing user V2", user_id=user_id[:8])
    
    # 1. PHANTOM USER CHECK
    if not force and not is_user_active(user_id):
        log.info("Skipping inactive user (Phantom Guardrail)", user_id=user_id[:8])
        send_ondemand_notification(user_id)
        return None
    
    # 2. GET USER FORMAT
    format_name, target_duration = get_user_format(user_id)
    log.info("User format", user_id=user_id[:8], format=format_name, duration=target_duration)
    
    # 3. ASSEMBLE LEGO PODCAST
    episode = assemble_lego_podcast(
        user_id=user_id,
        target_duration=target_duration,
        format_type=format_name
    )
    
    if episode:
        log.info("Episode generated V2", 
                episode_id=episode.get("id"), 
                user_id=user_id[:8],
                format=format_name)
    else:
        log.warning("Failed to generate episode", user_id=user_id[:8])
    
    return episode


# ============================================
# BATCH PROCESSING (CRON)
# ============================================

def process_all_pending(edition: str = "morning", force_all: bool = False):
    """
    Process pending content for all users.
    
    Args:
        edition: morning or evening
        force_all: If True, bypass phantom user check for all users
    """
    log.info("Starting batch processing V2", edition=edition)
    
    # Get all unique users with pending content
    result = supabase.table("content_queue") \
        .select("user_id") \
        .eq("status", "pending") \
        .eq("edition", edition) \
        .execute()
    
    if not result.data:
        log.info("No pending content to process")
        return
    
    # Get unique user IDs
    user_ids = list(set(item["user_id"] for item in result.data))
    log.info("Users with pending content", count=len(user_ids))
    
    # Stats
    stats = {
        "processed": 0,
        "skipped_inactive": 0,
        "failed": 0
    }
    
    # Process each user
    for user_id in user_ids:
        try:
            # Check activity before processing
            if not force_all and not is_user_active(user_id):
                stats["skipped_inactive"] += 1
                send_ondemand_notification(user_id)
                continue
            
            episode = process_user_queue_v2(user_id, force=True)
            
            if episode:
                stats["processed"] += 1
            else:
                stats["failed"] += 1
                
        except Exception as e:
            log.error("Error processing user", user_id=user_id[:8], error=str(e))
            stats["failed"] += 1
    
    log.info("Batch processing complete", 
             processed=stats["processed"],
             skipped=stats["skipped_inactive"],
             failed=stats["failed"])


# ============================================
# ON-DEMAND GENERATION
# ============================================

def generate_on_demand(user_id: str, format_type: str = None) -> dict | None:
    """
    Génère un épisode à la demande (bypass phantom check).
    Appelé quand l'utilisateur clique sur "Générer maintenant".
    
    V12 FIX: Check content_queue before generating, fetch if needed
    
    Args:
        user_id: User ID
        format_type: Override format (flash/digest)
        
    Returns:
        Created episode or None
    """
    log.info("On-demand generation", user_id=user_id[:8], format=format_type)
    
    # Update last_listened_at (user is engaging)
    try:
        supabase.table("users") \
            .update({"last_listened_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", user_id) \
            .execute()
    except:
        pass
    
    # Get format if not specified
    if not format_type:
        format_type, target_duration = get_user_format(user_id)
    else:
        target_duration = FORMAT_DURATIONS.get(format_type, 15)
    
    # V17: Queue is now global - check global pending content
    # No more per-user fetching, segments are pre-generated
    min_segments_needed = 3 if format_type == "flash" else 6
    try:
        # Check global queue for pending content
        pending_result = supabase.table("content_queue") \
            .select("id") \
            .eq("status", "pending") \
            .execute()
        
        pending_count = len(pending_result.data) if pending_result.data else 0
        log.info(f"📋 Global queue check: {pending_count} articles pending")
        
        if pending_count < min_segments_needed:
            log.warning(f"⚠️ Low content in global queue ({pending_count}). Run fetcher cron job.")
            # V17: No more on-demand fetching - queue should be filled by cron
    except Exception as e:
        log.warning(f"⚠️ Could not check pending content: {e}")
    
    return assemble_lego_podcast(
        user_id=user_id,
        target_duration=target_duration,
        format_type=format_type
    )


# ============================================
# CLEANUP
# ============================================

def cleanup_expired_segments():
    """
    Supprime les segments audio expirés (> 7 jours, jamais utilisés).
    """
    try:
        result = supabase.rpc('cleanup_expired_segments').execute()
        log.info("Cleaned up expired segments", count=result.data)
    except Exception as e:
        log.warning("Cleanup failed (function may not exist)", error=str(e))


# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Keernel Worker V2")
    parser.add_argument("--edition", choices=["morning", "evening"], default="morning",
                       help="Edition to process")
    parser.add_argument("--force", action="store_true",
                       help="Force generation for all users (bypass phantom check)")
    parser.add_argument("--user", type=str,
                       help="Process specific user ID")
    parser.add_argument("--cleanup", action="store_true",
                       help="Cleanup expired segments")
    parser.add_argument("--on-demand", type=str, metavar="USER_ID",
                       help="On-demand generation for user")
    
    args = parser.parse_args()
    
    if args.cleanup:
        cleanup_expired_segments()
        return
    
    if args.on_demand:
        episode = generate_on_demand(args.on_demand)
        if episode:
            print(f"Episode created: {episode.get('id')}")
        else:
            print("Failed to generate episode")
        return
    
    if args.user:
        episode = process_user_queue_v2(args.user, force=args.force)
        if episode:
            print(f"Episode created: {episode.get('id')}")
        else:
            print("Failed to generate episode")
        return
    
    # Batch processing
    process_all_pending(edition=args.edition, force_all=args.force)


if __name__ == "__main__":
    main()
