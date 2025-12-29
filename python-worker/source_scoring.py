"""
Keernel Source Scoring Engine
==============================

Intelligent source quality assessment with:
1. GLOBAL SAFETY LOCK - Prevents runaway score updates
2. DYNAMIC SCORING - Multi-factor quality score (0-100)
3. QUARANTINE & REDEMPTION - Autonomous source lifecycle management

Factors (weighted):
- 50% Retention: User listens >75% of segment from source
- 25% Lead Time: Source publishes 6-24h before cluster formation
- 25% Signal-to-Noise: Selection ratio over last 30 publications
"""

import os
from datetime import datetime, timedelta, date
from typing import Optional
from collections import defaultdict

import structlog
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Safety thresholds
GLOBAL_SKIP_RATE_THRESHOLD = 0.80  # 80% - triggers safety lock
SAFETY_CHECK_WINDOW_HOURS = 24

# Scoring weights
WEIGHT_RETENTION = 0.50
WEIGHT_LEAD_TIME = 0.25
WEIGHT_SIGNAL_TO_NOISE = 0.25

# Retention threshold (75% of segment = success)
RETENTION_SUCCESS_THRESHOLD = 0.75

# Lead time bonus window (6-24h before cluster)
LEAD_TIME_MIN_HOURS = 6
LEAD_TIME_MAX_HOURS = 24

# Signal-to-noise window (last N publications, not time-based)
SNR_PUBLICATION_WINDOW = 30

# Quarantine thresholds
ELITE_SOURCE_THRESHOLD = 90  # GSheet score > 90
ELITE_GRACE_PUBLICATIONS = 30  # 30 publications without success before degradation
STANDARD_QUARANTINE_THRESHOLD = 30  # dynamic_score < 30
STANDARD_MIN_PUBLICATIONS = 10  # Minimum publications before quarantine
LOW_SCORE_THRESHOLD = 70  # GSheet score < 70 = standard source

# Redemption settings
REDEMPTION_TEST_ARTICLES = 5
REDEMPTION_INTERVAL_DAYS = 30

# Source statuses
STATUS_ACTIVE = "ACTIF"
STATUS_QUARANTINE = "QUARANTAINE"
STATUS_RETEST = "RE-TEST"

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_URL else None


# ============================================
# 1. GLOBAL SAFETY LOCK
# ============================================

def check_global_safety_lock() -> dict:
    """
    Check if the global skip rate exceeds threshold.
    If >80% of segments are skipped in last 24h, freeze all score updates.
    
    Returns:
        dict with 'is_locked', 'skip_rate', 'reason'
    """
    if not supabase:
        log.error("❌ Supabase not available for safety check")
        return {"is_locked": True, "skip_rate": None, "reason": "Database unavailable"}
    
    try:
        cutoff = (datetime.now() - timedelta(hours=SAFETY_CHECK_WINDOW_HOURS)).isoformat()
        
        # Get all segment listens in the last 24h
        result = supabase.table("segment_listens") \
            .select("id, listened_ratio") \
            .gte("created_at", cutoff) \
            .execute()
        
        if not result.data or len(result.data) < 10:
            # Not enough data to determine, allow updates
            log.info("✅ Safety check: Insufficient data, allowing updates")
            return {"is_locked": False, "skip_rate": 0, "reason": "Insufficient data"}
        
        total_segments = len(result.data)
        skipped_segments = sum(1 for s in result.data if s.get("listened_ratio", 0) < 0.25)
        
        skip_rate = skipped_segments / total_segments
        
        if skip_rate > GLOBAL_SKIP_RATE_THRESHOLD:
            log.error(f"🚨 SAFETY LOCK TRIGGERED: {skip_rate:.1%} skip rate exceeds {GLOBAL_SKIP_RATE_THRESHOLD:.0%}")
            
            # Record the alert
            supabase.table("system_alerts").insert({
                "alert_type": "SAFETY_LOCK",
                "severity": "CRITICAL",
                "message": f"Global skip rate {skip_rate:.1%} exceeds threshold. Score updates frozen.",
                "data": {"skip_rate": skip_rate, "total_segments": total_segments}
            }).execute()
            
            return {
                "is_locked": True,
                "skip_rate": skip_rate,
                "reason": f"Skip rate {skip_rate:.1%} > {GLOBAL_SKIP_RATE_THRESHOLD:.0%}"
            }
        
        log.info(f"✅ Safety check passed: {skip_rate:.1%} skip rate")
        return {"is_locked": False, "skip_rate": skip_rate, "reason": "OK"}
        
    except Exception as e:
        log.error(f"❌ Safety check failed: {e}")
        # Fail-safe: lock updates if we can't verify
        return {"is_locked": True, "skip_rate": None, "reason": f"Check failed: {e}"}


# ============================================
# 2. DYNAMIC SCORING SYSTEM
# ============================================

def calculate_retention_score(source_domain: str) -> float:
    """
    Calculate retention score (0-100) based on user listening behavior.
    Success = user listens >75% of segment from this source.
    
    Returns score 0-100
    """
    if not supabase:
        return 50.0  # Default neutral score
    
    try:
        # Get last 30 segments from this source
        result = supabase.table("segment_listens") \
            .select("listened_ratio, source_domain") \
            .eq("source_domain", source_domain) \
            .order("created_at", desc=True) \
            .limit(SNR_PUBLICATION_WINDOW) \
            .execute()
        
        if not result.data:
            return 50.0  # No data, neutral score
        
        listens = result.data
        successes = sum(1 for l in listens if l.get("listened_ratio", 0) >= RETENTION_SUCCESS_THRESHOLD)
        
        retention_rate = successes / len(listens)
        score = retention_rate * 100
        
        log.debug(f"📊 Retention score for {source_domain}: {score:.1f} ({successes}/{len(listens)} successes)")
        return score
        
    except Exception as e:
        log.warning(f"⚠️ Retention calculation failed for {source_domain}: {e}")
        return 50.0


def calculate_lead_time_score(source_domain: str) -> float:
    """
    Calculate lead time score (0-100) based on publication timing.
    Bonus if source publishes 6-24h before cluster formation.
    
    Returns score 0-100
    """
    if not supabase:
        return 50.0
    
    try:
        # Get articles from this source that were part of clusters
        result = supabase.table("cluster_articles") \
            .select("article_published_at, cluster_created_at, source_domain") \
            .eq("source_domain", source_domain) \
            .order("cluster_created_at", desc=True) \
            .limit(SNR_PUBLICATION_WINDOW) \
            .execute()
        
        if not result.data:
            return 50.0  # No data
        
        optimal_leads = 0
        total = len(result.data)
        
        for item in result.data:
            pub_time = item.get("article_published_at")
            cluster_time = item.get("cluster_created_at")
            
            if not pub_time or not cluster_time:
                continue
            
            # Calculate lead time in hours
            pub_dt = datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
            cluster_dt = datetime.fromisoformat(cluster_time.replace("Z", "+00:00"))
            lead_hours = (cluster_dt - pub_dt).total_seconds() / 3600
            
            # Optimal range: 6-24 hours before cluster
            if LEAD_TIME_MIN_HOURS <= lead_hours <= LEAD_TIME_MAX_HOURS:
                optimal_leads += 1
        
        score = (optimal_leads / total) * 100 if total > 0 else 50.0
        
        log.debug(f"📊 Lead time score for {source_domain}: {score:.1f} ({optimal_leads}/{total} optimal)")
        return score
        
    except Exception as e:
        log.warning(f"⚠️ Lead time calculation failed for {source_domain}: {e}")
        return 50.0


def calculate_signal_to_noise_score(source_domain: str) -> float:
    """
    Calculate signal-to-noise score (0-100).
    Ratio of selected articles vs scraped articles over last 30 PUBLICATIONS.
    
    CRITICAL: Window is publication-based, not time-based,
    to protect low-frequency sources (researcher blogs).
    
    Returns score 0-100
    """
    if not supabase:
        return 50.0
    
    try:
        # Get last 30 articles scraped from this source
        scraped = supabase.table("content_queue") \
            .select("id, url, status") \
            .eq("source_name", source_domain) \
            .order("created_at", desc=True) \
            .limit(SNR_PUBLICATION_WINDOW) \
            .execute()
        
        if not scraped.data:
            return 50.0  # No data
        
        total_scraped = len(scraped.data)
        selected = sum(1 for a in scraped.data if a.get("status") in ["processed", "selected"])
        
        if total_scraped == 0:
            return 50.0
        
        ratio = selected / total_scraped
        score = ratio * 100
        
        log.debug(f"📊 SNR score for {source_domain}: {score:.1f} ({selected}/{total_scraped} selected)")
        return score
        
    except Exception as e:
        log.warning(f"⚠️ SNR calculation failed for {source_domain}: {e}")
        return 50.0


def calculate_dynamic_score(source_domain: str) -> dict:
    """
    Calculate the complete dynamic score (0-100) for a source.
    
    Weighted formula:
    - 50% Retention (user listens >75% of segment)
    - 25% Lead Time (publishes 6-24h before cluster)
    - 25% Signal-to-Noise (selection ratio)
    
    Returns dict with scores breakdown and final score
    """
    retention = calculate_retention_score(source_domain)
    lead_time = calculate_lead_time_score(source_domain)
    snr = calculate_signal_to_noise_score(source_domain)
    
    dynamic_score = (
        retention * WEIGHT_RETENTION +
        lead_time * WEIGHT_LEAD_TIME +
        snr * WEIGHT_SIGNAL_TO_NOISE
    )
    
    return {
        "source_domain": source_domain,
        "dynamic_score": round(dynamic_score, 1),
        "retention_score": round(retention, 1),
        "lead_time_score": round(lead_time, 1),
        "snr_score": round(snr, 1),
        "calculated_at": datetime.now().isoformat()
    }


def update_source_performance(source_domain: str, gsheet_score: int = None) -> Optional[dict]:
    """
    Calculate and store dynamic score for a source.
    Checks safety lock before updating.
    
    Args:
        source_domain: The source's domain name
        gsheet_score: Optional base score from GSheet library
    
    Returns:
        Updated performance record or None if locked
    """
    # Check safety lock first
    safety = check_global_safety_lock()
    if safety["is_locked"]:
        log.warning(f"🔒 Score update blocked by safety lock: {safety['reason']}")
        return None
    
    # Calculate dynamic score
    scores = calculate_dynamic_score(source_domain)
    
    # Get publication count for this source
    pub_count = get_publication_count(source_domain)
    
    # Determine status based on scores
    status = determine_source_status(
        dynamic_score=scores["dynamic_score"],
        gsheet_score=gsheet_score or 50,
        publication_count=pub_count
    )
    
    # Store in source_performance table
    try:
        data = {
            "source_domain": source_domain,
            "dynamic_score": scores["dynamic_score"],
            "retention_score": scores["retention_score"],
            "lead_time_score": scores["lead_time_score"],
            "snr_score": scores["snr_score"],
            "gsheet_score": gsheet_score,
            "publication_count": pub_count,
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        
        supabase.table("source_performance").upsert(
            data,
            on_conflict="source_domain"
        ).execute()
        
        log.info(f"✅ Updated score for {source_domain}: {scores['dynamic_score']:.1f} ({status})")
        return data
        
    except Exception as e:
        log.error(f"❌ Failed to update source performance: {e}")
        return None


def get_publication_count(source_domain: str) -> int:
    """Get total publication count for a source."""
    if not supabase:
        return 0
    
    try:
        result = supabase.table("content_queue") \
            .select("id", count="exact") \
            .eq("source_name", source_domain) \
            .execute()
        
        return result.count or 0
    except:
        return 0


# ============================================
# 3. QUARANTINE & REDEMPTION LOGIC
# ============================================

def determine_source_status(
    dynamic_score: float,
    gsheet_score: int,
    publication_count: int,
    consecutive_failures: int = 0
) -> str:
    """
    Determine source status based on scores and publication history.
    
    Rules:
    - Elite sources (GSheet > 90): 30 publications grace period
    - Standard sources (GSheet < 70): Quarantine if dynamic < 30 after 10 pubs
    """
    
    # Elite source rules
    if gsheet_score >= ELITE_SOURCE_THRESHOLD:
        if consecutive_failures >= ELITE_GRACE_PUBLICATIONS:
            log.info(f"⚠️ Elite source degraded after {consecutive_failures} failures")
            return STATUS_QUARANTINE
        return STATUS_ACTIVE
    
    # Standard source rules (GSheet < 70)
    if gsheet_score < LOW_SCORE_THRESHOLD:
        if publication_count >= STANDARD_MIN_PUBLICATIONS:
            if dynamic_score < STANDARD_QUARANTINE_THRESHOLD:
                log.info(f"🔒 Standard source quarantined: score {dynamic_score} < {STANDARD_QUARANTINE_THRESHOLD}")
                return STATUS_QUARANTINE
    
    return STATUS_ACTIVE


def get_sources_for_redemption() -> list[dict]:
    """
    Get quarantined sources eligible for redemption test.
    
    Criteria:
    - Status = QUARANTINE
    - Last test was > 30 days ago (or never tested)
    """
    if not supabase:
        return []
    
    try:
        cutoff = (datetime.now() - timedelta(days=REDEMPTION_INTERVAL_DAYS)).isoformat()
        
        result = supabase.table("source_performance") \
            .select("*") \
            .eq("status", STATUS_QUARANTINE) \
            .or_(f"last_redemption_test.is.null,last_redemption_test.lt.{cutoff}") \
            .limit(10) \
            .execute()
        
        return result.data or []
        
    except Exception as e:
        log.error(f"❌ Failed to get redemption candidates: {e}")
        return []


def initiate_redemption_test(source_domain: str) -> bool:
    """
    Initiate a redemption test for a quarantined source.
    
    Action:
    - Mark source as RE-TEST
    - Queue 5 articles from this source for the next podcast
    """
    if not supabase:
        return False
    
    try:
        # Update status to RE-TEST
        supabase.table("source_performance").update({
            "status": STATUS_RETEST,
            "last_redemption_test": datetime.now().isoformat()
        }).eq("source_domain", source_domain).execute()
        
        # Get recent articles from this source that weren't processed
        articles = supabase.table("content_queue") \
            .select("id") \
            .eq("source_name", source_domain) \
            .eq("status", "quarantined") \
            .order("created_at", desc=True) \
            .limit(REDEMPTION_TEST_ARTICLES) \
            .execute()
        
        if articles.data:
            article_ids = [a["id"] for a in articles.data]
            
            # Re-enable these articles for processing
            supabase.table("content_queue").update({
                "status": "pending",
                "priority": "high",
                "redemption_test": True
            }).in_("id", article_ids).execute()
            
            log.info(f"🔄 Redemption test initiated for {source_domain}: {len(article_ids)} articles queued")
        
        return True
        
    except Exception as e:
        log.error(f"❌ Redemption test failed for {source_domain}: {e}")
        return False


def evaluate_redemption_test(source_domain: str) -> str:
    """
    Evaluate the results of a redemption test.
    
    Returns new status: ACTIF or QUARANTAINE
    """
    if not supabase:
        return STATUS_QUARANTINE
    
    try:
        # Get redemption test articles
        result = supabase.table("segment_listens") \
            .select("listened_ratio") \
            .eq("source_domain", source_domain) \
            .eq("redemption_test", True) \
            .execute()
        
        if not result.data:
            log.warning(f"⚠️ No redemption data for {source_domain}, keeping quarantine")
            return STATUS_QUARANTINE
        
        listens = result.data
        successes = sum(1 for l in listens if l.get("listened_ratio", 0) >= RETENTION_SUCCESS_THRESHOLD)
        success_rate = successes / len(listens)
        
        # Need >50% success rate to exit quarantine
        if success_rate >= 0.5:
            log.info(f"✅ Redemption successful for {source_domain}: {success_rate:.0%} retention")
            
            # Update status
            supabase.table("source_performance").update({
                "status": STATUS_ACTIVE,
                "consecutive_failures": 0
            }).eq("source_domain", source_domain).execute()
            
            return STATUS_ACTIVE
        else:
            log.info(f"❌ Redemption failed for {source_domain}: {success_rate:.0%} retention")
            
            # Stay in quarantine
            supabase.table("source_performance").update({
                "status": STATUS_QUARANTINE
            }).eq("source_domain", source_domain).execute()
            
            return STATUS_QUARANTINE
        
    except Exception as e:
        log.error(f"❌ Redemption evaluation failed: {e}")
        return STATUS_QUARANTINE


# ============================================
# GSHEET SYNC (Column G = system_status)
# ============================================

def sync_status_to_gsheet(source_domain: str, status: str) -> bool:
    """
    Write source status to GSheet Column G (system_status).
    
    Only writes: ACTIF, QUARANTAINE, RE-TEST
    """
    try:
        from sourcing import get_gsheet_client
        
        client = get_gsheet_client()
        if not client:
            log.warning("⚠️ GSheet client not available")
            return False
        
        # Open the source library spreadsheet
        LIBRARY_SPREADSHEET_ID = os.getenv("GSHEET_LIBRARY_ID")
        if not LIBRARY_SPREADSHEET_ID:
            return False
        
        spreadsheet = client.open_by_key(LIBRARY_SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1
        
        # Find the row with this source domain
        all_data = worksheet.get_all_values()
        
        for row_idx, row in enumerate(all_data[1:], start=2):  # Skip header
            if len(row) > 0 and source_domain.lower() in row[0].lower():
                # Column G = index 6 (0-based) = 7 (1-based)
                worksheet.update_cell(row_idx, 7, status)
                log.info(f"✅ GSheet updated: {source_domain} → {status}")
                return True
        
        log.warning(f"⚠️ Source {source_domain} not found in GSheet")
        return False
        
    except Exception as e:
        log.error(f"❌ GSheet sync failed: {e}")
        return False


# ============================================
# BATCH OPERATIONS
# ============================================

def update_all_source_scores() -> dict:
    """
    Update scores for all active sources.
    Called by daily cron job.
    """
    # Check safety lock first
    safety = check_global_safety_lock()
    if safety["is_locked"]:
        return {
            "success": False,
            "reason": safety["reason"],
            "updated": 0
        }
    
    if not supabase:
        return {"success": False, "reason": "Database unavailable", "updated": 0}
    
    try:
        # Get all sources with recent activity
        sources = supabase.table("content_queue") \
            .select("source_name") \
            .order("created_at", desc=True) \
            .limit(500) \
            .execute()
        
        # Unique sources
        unique_sources = list(set(s["source_name"] for s in (sources.data or []) if s.get("source_name")))
        
        updated = 0
        quarantined = 0
        
        for source in unique_sources:
            result = update_source_performance(source)
            if result:
                updated += 1
                if result.get("status") == STATUS_QUARANTINE:
                    quarantined += 1
                    # Sync to GSheet
                    sync_status_to_gsheet(source, STATUS_QUARANTINE)
        
        log.info(f"✅ Batch update complete: {updated} sources, {quarantined} quarantined")
        
        return {
            "success": True,
            "updated": updated,
            "quarantined": quarantined
        }
        
    except Exception as e:
        log.error(f"❌ Batch update failed: {e}")
        return {"success": False, "reason": str(e), "updated": 0}


def run_monthly_redemption() -> dict:
    """
    Run monthly redemption tests for quarantined sources.
    Called by monthly cron job.
    """
    candidates = get_sources_for_redemption()
    
    if not candidates:
        log.info("📋 No sources eligible for redemption")
        return {"tested": 0, "redeemed": 0}
    
    tested = 0
    redeemed = 0
    
    for source in candidates[:5]:  # Max 5 per month
        domain = source.get("source_domain")
        if initiate_redemption_test(domain):
            tested += 1
            # Note: Actual evaluation happens after podcast generation
            # when we have listening data
    
    log.info(f"🔄 Redemption tests initiated: {tested} sources")
    
    return {"tested": tested, "redeemed": redeemed}


# ============================================
# DATABASE MIGRATION
# ============================================

MIGRATION_SQL = """
-- Source Performance Table
CREATE TABLE IF NOT EXISTS source_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_domain TEXT UNIQUE NOT NULL,
    dynamic_score FLOAT DEFAULT 50,
    retention_score FLOAT DEFAULT 50,
    lead_time_score FLOAT DEFAULT 50,
    snr_score FLOAT DEFAULT 50,
    gsheet_score INTEGER,
    publication_count INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ACTIF',
    last_redemption_test TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS source_performance_domain_idx ON source_performance (source_domain);
CREATE INDEX IF NOT EXISTS source_performance_status_idx ON source_performance (status);
CREATE INDEX IF NOT EXISTS source_performance_score_idx ON source_performance (dynamic_score DESC);

-- Segment Listens Table (for retention tracking)
CREATE TABLE IF NOT EXISTS segment_listens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_id UUID,
    segment_index INTEGER,
    source_domain TEXT,
    listened_ratio FLOAT DEFAULT 0,
    redemption_test BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS segment_listens_source_idx ON segment_listens (source_domain);
CREATE INDEX IF NOT EXISTS segment_listens_date_idx ON segment_listens (created_at DESC);

-- Cluster Articles Table (for lead time tracking)
CREATE TABLE IF NOT EXISTS cluster_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id TEXT,
    article_url TEXT,
    source_domain TEXT,
    article_published_at TIMESTAMPTZ,
    cluster_created_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS cluster_articles_source_idx ON cluster_articles (source_domain);

-- System Alerts Table
CREATE TABLE IF NOT EXISTS system_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type TEXT NOT NULL,
    severity TEXT DEFAULT 'INFO',
    message TEXT,
    data JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS system_alerts_type_idx ON system_alerts (alert_type, created_at DESC);

-- Add redemption_test column to content_queue if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'content_queue' AND column_name = 'redemption_test'
    ) THEN
        ALTER TABLE content_queue ADD COLUMN redemption_test BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- RLS Policies
ALTER TABLE source_performance ENABLE ROW LEVEL SECURITY;
ALTER TABLE segment_listens ENABLE ROW LEVEL SECURITY;
ALTER TABLE cluster_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON source_performance FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON segment_listens FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON cluster_articles FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON system_alerts FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users read own listens" ON segment_listens FOR SELECT USING (auth.uid() = user_id);
"""


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Keernel Source Scoring Engine")
    parser.add_argument("--update-all", action="store_true", help="Update all source scores")
    parser.add_argument("--redemption", action="store_true", help="Run monthly redemption tests")
    parser.add_argument("--score", type=str, help="Calculate score for specific source")
    parser.add_argument("--safety-check", action="store_true", help="Run safety check")
    parser.add_argument("--migration", action="store_true", help="Print migration SQL")
    
    args = parser.parse_args()
    
    if args.migration:
        print(MIGRATION_SQL)
    elif args.safety_check:
        result = check_global_safety_lock()
        print(f"Safety Lock: {'🔒 LOCKED' if result['is_locked'] else '✅ OK'}")
        print(f"Skip Rate: {result.get('skip_rate', 'N/A')}")
        print(f"Reason: {result['reason']}")
    elif args.score:
        scores = calculate_dynamic_score(args.score)
        print(f"\n📊 Scores for {args.score}:")
        print(f"   Dynamic Score: {scores['dynamic_score']:.1f}/100")
        print(f"   - Retention:   {scores['retention_score']:.1f} (50% weight)")
        print(f"   - Lead Time:   {scores['lead_time_score']:.1f} (25% weight)")
        print(f"   - SNR:         {scores['snr_score']:.1f} (25% weight)")
    elif args.update_all:
        result = update_all_source_scores()
        print(f"Updated: {result['updated']} sources")
        if result.get('quarantined'):
            print(f"Quarantined: {result['quarantined']} sources")
    elif args.redemption:
        result = run_monthly_redemption()
        print(f"Tested: {result['tested']} sources")
    else:
        parser.print_help()
