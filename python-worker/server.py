"""
HTTP Server for triggering podcast generation from the Dashboard.
Also handles Cloudmailin webhooks for newsletter ingestion.

V2: Support for Flash/Digest formats and on-demand generation
"""
import os
import hmac
import hashlib
import threading
from flask import Flask, request, jsonify
import structlog
from dotenv import load_dotenv

# V2 imports
from worker_v2 import generate_on_demand, process_user_queue_v2
from db import supabase
from sourcing import parse_cloudmailin_webhook

load_dotenv()
log = structlog.get_logger()

app = Flask(__name__)

# Simple auth token (set in environment)
WORKER_SECRET = os.getenv("WORKER_SECRET", "")
CLOUDMAILIN_SECRET = os.getenv("CLOUDMAILIN_SECRET", "")


def verify_auth():
    """Verify the request is authorized."""
    if not WORKER_SECRET:
        return True  # No auth configured
    
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return token == WORKER_SECRET
    return False


def verify_cloudmailin_signature():
    """Verify Cloudmailin webhook signature."""
    if not CLOUDMAILIN_SECRET:
        return True  # No secret configured, accept all
    
    signature = request.headers.get("X-CloudMailin-Signature", "")
    if not signature:
        return False
    
    # Compute expected signature
    expected = hmac.new(
        CLOUDMAILIN_SECRET.encode(),
        request.data,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


@app.route("/", methods=["GET"])
def root():
    """Root endpoint."""
    return jsonify({"service": "keernel-worker", "version": "2.0", "status": "running"})


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "keernel-worker", "version": "2.0"})


@app.route("/generate", methods=["POST"])
def generate():
    """
    Trigger podcast generation for a user (V2).
    
    Body params:
    - user_id: Required
    - format: Optional, "flash" (4min) or "digest" (15min)
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    user_id = data.get("user_id")
    format_type = data.get("format")  # flash or digest
    
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    log.info("Generation request received (V2)", user_id=user_id, format=format_type)
    
    # Run generation in background thread
    def run_generation():
        try:
            # Use on-demand generation (bypasses phantom check, updates last_listened)
            episode = generate_on_demand(user_id, format_type=format_type)
            if episode:
                log.info("Episode generated via HTTP (V2)", episode_id=episode["id"])
            else:
                log.warning("Generation failed via HTTP", user_id=user_id)
        except Exception as e:
            log.error("Generation error", user_id=user_id, error=str(e))
    
    thread = threading.Thread(target=run_generation)
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Generation started (V2 Lego)",
        "user_id": user_id,
        "format": format_type or "default"
    })


@app.route("/status/<user_id>", methods=["GET"])
def status(user_id: str):
    """Get generation status for a user."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Get pending count
        pending = supabase.table("content_queue") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("status", "pending") \
            .execute()
        
        # Get latest episode
        episode = supabase.table("episodes") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        return jsonify({
            "pending_count": len(pending.data) if pending.data else 0,
            "latest_episode": episode.data[0] if episode.data else None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# V14: CLUSTER PIPELINE CRON
# ============================================

@app.route("/cron/cluster", methods=["POST"])
def cron_cluster():
    """
    V14: Daily clustering job.
    Transforms raw articles into semantic clusters.
    Call this before podcast generation (e.g., 6am daily).
    
    Can be triggered by:
    - Render Cron Job
    - External cron service (cron-job.org, etc.)
    - GitHub Actions scheduled workflow
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    user_id = data.get("user_id")  # Optional: cluster for specific user only
    
    log.info("🎯 Cluster cron job triggered", user_id=user_id or "all users")
    
    # Run clustering in background thread
    def run_clustering():
        try:
            from cluster_pipeline import run_cluster_pipeline, run_daily_clustering
            
            if user_id:
                # Cluster for specific user
                clusters = run_cluster_pipeline(user_id=user_id, store_results=True)
                log.info(f"✅ Clustered {len(clusters)} topics for user {user_id[:8]}...")
            else:
                # Cluster for all users with pending content
                run_daily_clustering()
                log.info("✅ Daily clustering complete for all users")
                
        except Exception as e:
            log.error(f"❌ Clustering error: {e}")
    
    thread = threading.Thread(target=run_clustering)
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Clustering job started",
        "user_id": user_id or "all"
    })


@app.route("/clusters/<user_id>", methods=["GET"])
def get_clusters(user_id: str):
    """
    V14: Get today's clusters for a user.
    Useful for debugging and dashboard display.
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from cluster_pipeline import get_daily_clusters
        
        clusters = get_daily_clusters(user_id=user_id)
        
        return jsonify({
            "success": True,
            "cluster_count": len(clusters),
            "clusters": clusters
        })
    except ImportError:
        return jsonify({"error": "Cluster pipeline not available"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# V14: SOURCE SCORING ENGINE
# ============================================

@app.route("/test-script", methods=["POST"])
def test_script():
    """
    TEST ENDPOINT: Generate script only (no TTS).
    
    Returns the LLM-generated dialogue text without audio generation.
    Useful for iterating on prompts quickly.
    
    Body params:
    - user_id: Required
    - format: Optional, "flash" (4min) or "digest" (15min)
    - topic: Optional, filter to specific topic
    - skip_script: Optional, if true only show articles (no LLM call)
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    user_id = data.get("user_id")
    format_type = data.get("format", "flash")
    topic_filter = data.get("topic")  # Optional: only test specific topic
    skip_script = data.get("skip_script", False)  # Skip LLM, just show articles
    
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    log.info("🧪 Test script generation", user_id=user_id, format=format_type)
    
    try:
        from stitcher_v2 import (
            get_podcast_config, 
            generate_dialogue_script,
            get_or_create_ephemeride
        )
        from sourcing import get_content_for_podcast, fetch_all_sources
        
        # 1. Get config
        config = get_podcast_config(format_type)
        target_minutes = config.get("target_minutes", 4)
        
        # 2. Get RAW articles from all sources (before any filtering)
        raw_articles = fetch_all_sources(user_id=user_id)
        raw_articles_summary = []
        for art in raw_articles[:50]:  # Limit to 50 for response size
            raw_articles_summary.append({
                "title": art.get("title", "")[:100],
                "source": art.get("source_name", ""),
                "topic": art.get("keyword", art.get("topic_slug", "")),
                "url": art.get("url", "")[:100],
                "published": art.get("published", ""),
                "score": art.get("score", 0)
            })
        
        # 3. Get SELECTED content (after scoring/filtering)
        items = get_content_for_podcast(
            user_id=user_id,
            target_minutes=target_minutes
        )
        
        if not items:
            return jsonify({
                "success": False,
                "error": "No content selected for podcast",
                "raw_articles_count": len(raw_articles),
                "raw_articles": raw_articles_summary,
                "suggestion": "Check scoring or add more sources"
            }), 200  # Return 200 so you can see the raw articles
        
        # Filter by topic if specified
        if topic_filter:
            items = [i for i in items if i.get("keyword") == topic_filter or i.get("topic_slug") == topic_filter]
            if not items:
                return jsonify({
                    "error": f"No content for topic '{topic_filter}'",
                    "available_topics": list(set(i.get("keyword", "") for i in items))
                }), 404
        
        # 4. Group by topic (show clustering)
        clusters = {}
        for item in items:
            topic_key = item.get("keyword", item.get("topic_slug", "general"))
            if topic_key not in clusters:
                clusters[topic_key] = []
            clusters[topic_key].append(item)
        
        # Selected articles summary
        selected_articles = []
        for item in items:
            selected_articles.append({
                "title": item.get("title", "")[:100],
                "source": item.get("source_name", ""),
                "topic": item.get("keyword", ""),
                "url": item.get("url", "")[:100],
                "score": item.get("score", 0)
            })
        
        # If skip_script, return just the articles
        if skip_script:
            return jsonify({
                "success": True,
                "mode": "articles_only",
                "format": format_type,
                "target_minutes": target_minutes,
                "raw_articles_count": len(raw_articles),
                "raw_articles": raw_articles_summary,
                "selected_articles_count": len(items),
                "selected_articles": selected_articles,
                "topics": {topic: len(arts) for topic, arts in clusters.items()}
            })
        
        # 5. Generate scripts for each topic cluster
        scripts = []
        
        for topic, topic_items in clusters.items():
            # Get articles info
            articles_for_script = []
            for item in topic_items[:3]:  # Max 3 per topic
                articles_for_script.append({
                    "title": item.get("title", ""),
                    "summary": item.get("summary", item.get("content", ""))[:500],
                    "source": item.get("source_name", ""),
                    "url": item.get("url", "")
                })
            
            # Generate script
            script = generate_dialogue_script(
                articles=articles_for_script,
                format_config=config
            )
            
            scripts.append({
                "topic": topic,
                "article_count": len(topic_items),
                "articles": [{"title": a["title"], "source": a["source"]} for a in articles_for_script],
                "script": script
            })
        
        # 6. Also get ephemeride for reference
        ephemeride = get_or_create_ephemeride()
        ephemeride_script = ephemeride.get("script", "") if ephemeride else None
        
        return jsonify({
            "success": True,
            "format": format_type,
            "target_minutes": target_minutes,
            "raw_articles_count": len(raw_articles),
            "raw_articles": raw_articles_summary[:20],  # First 20 for reference
            "selected_articles_count": len(items),
            "selected_articles": selected_articles,
            "topic_count": len(clusters),
            "ephemeride_script": ephemeride_script,
            "scripts": scripts
        })
        
    except Exception as e:
        log.error(f"Test script error: {e}")
        import traceback
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route("/cron/scoring", methods=["POST"])
def cron_scoring():
    """
    Daily source scoring job.
    Updates dynamic scores for all active sources.
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    log.info("📊 Source scoring cron triggered")
    
    def run_scoring():
        try:
            from source_scoring import update_all_source_scores
            result = update_all_source_scores()
            log.info(f"✅ Scoring complete: {result}")
        except Exception as e:
            log.error(f"❌ Scoring error: {e}")
    
    thread = threading.Thread(target=run_scoring)
    thread.start()
    
    return jsonify({"success": True, "message": "Scoring job started"})


@app.route("/cron/redemption", methods=["POST"])
def cron_redemption():
    """
    Monthly redemption job.
    Tests quarantined sources for quality improvement.
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    log.info("🔄 Redemption cron triggered")
    
    def run_redemption():
        try:
            from source_scoring import run_monthly_redemption
            result = run_monthly_redemption()
            log.info(f"✅ Redemption complete: {result}")
        except Exception as e:
            log.error(f"❌ Redemption error: {e}")
    
    thread = threading.Thread(target=run_redemption)
    thread.start()
    
    return jsonify({"success": True, "message": "Redemption job started"})


@app.route("/source/<domain>/score", methods=["GET"])
def get_source_score(domain: str):
    """Get dynamic score for a specific source."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from source_scoring import calculate_dynamic_score
        scores = calculate_dynamic_score(domain)
        return jsonify(scores)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/safety-check", methods=["GET"])
def safety_check():
    """Check if global safety lock is active."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from source_scoring import check_global_safety_lock
        result = check_global_safety_lock()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# CLOUDMAILIN WEBHOOK (Newsletter Ingestion)
# ============================================

@app.route("/webhook/newsletter", methods=["POST"])
def newsletter_webhook():
    """
    Receive newsletters via Cloudmailin webhook.
    
    Cloudmailin sends JSON POST with:
    - envelope: from, to
    - headers: subject, from, etc.
    - plain: text content
    - html: HTML content
    """
    if not verify_cloudmailin_signature():
        log.warning("Invalid Cloudmailin signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    try:
        payload = request.get_json()
        
        if not payload:
            return jsonify({"error": "Empty payload"}), 400
        
        # Parse newsletter content
        newsletter = parse_cloudmailin_webhook(payload)
        
        if not newsletter:
            return jsonify({"error": "Failed to parse newsletter"}), 400
        
        # Get recipient email to find user
        envelope = payload.get("envelope", {})
        to_address = envelope.get("to", "")
        
        # Extract user identifier from email (e.g., user-abc123@newsletter.keernel.app)
        # This assumes you set up a catch-all email pattern
        user_id = None
        if "+" in to_address:
            # user+abc123@... format
            user_id = to_address.split("+")[1].split("@")[0]
        elif to_address.startswith("user-"):
            # user-abc123@... format
            user_id = to_address.split("@")[0].replace("user-", "")
        
        if not user_id:
            log.warning("Could not extract user_id from email", to=to_address)
            # Store in a general queue for manual assignment
            user_id = "system"
        
        # Insert into content_queue with high priority
        result = supabase.table("content_queue").insert({
            "user_id": user_id,
            "url": f"newsletter://{newsletter['source']}",
            "title": newsletter["title"],
            "source_type": "newsletter",
            "source": newsletter["source"],
            "priority": "high",
            "status": "pending",
            "processed_content": newsletter["content"][:5000]  # Store content directly
        }).execute()
        
        log.info("Newsletter ingested", 
                 user_id=user_id, 
                 subject=newsletter["title"][:50])
        
        return jsonify({
            "success": True,
            "message": "Newsletter received",
            "queue_id": result.data[0]["id"] if result.data else None
        })
        
    except Exception as e:
        log.error("Newsletter webhook error", error=str(e))
        return jsonify({"error": str(e)}), 500


def run_server(port: int = 8080):
    """Run the Flask server."""
    log.info("Starting HTTP server", port=port)
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    run_server(port)
