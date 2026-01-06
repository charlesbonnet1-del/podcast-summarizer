"""
HTTP Server for triggering podcast generation from the Dashboard.
Also handles Cloudmailin webhooks for newsletter ingestion.

V2: Support for Flash/Digest formats and on-demand generation
"""
import os
import hmac
import hashlib
import threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
import structlog
from dotenv import load_dotenv

# V2 imports
from worker_v2 import generate_on_demand, process_user_queue_v2
from db import supabase
from sourcing import parse_cloudmailin_webhook

# V17: Pipeline Lab
from pipeline_lab import (
    get_default_params,
    sandbox_fetch,
    sandbox_cluster,
    sandbox_select,
    sandbox_full_pipeline
)

load_dotenv()
log = structlog.get_logger()

app = Flask(__name__)

# Enable CORS for all routes
CORS(app, origins=["https://podcast-summarizer1.vercel.app", "http://localhost:3000"])

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
        # Get pending count - V17: Global queue, no user_id filter
        pending = supabase.table("content_queue") \
            .select("id") \
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
    TEST ENDPOINT: Debug the full pipeline.
    
    Shows for EACH TOPIC:
    - Raw articles fetched from RSS (sample)
    - Articles in content_queue (pending)
    - Generated script (optional)
    
    Body params:
    - user_id: Required
    - format: Optional, "flash" or "digest"
    - with_script: Optional, if true generate LLM scripts (slower)
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    user_id = data.get("user_id")
    format_type = data.get("format", "flash")
    with_script = data.get("with_script", False)
    
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    log.info("🧪 Test pipeline", user_id=user_id, format=format_type)
    
    try:
        from stitcher_v2 import get_podcast_config, generate_dialogue_segment_script
        from sourcing import fetch_all_sources
        
        config = get_podcast_config(format_type)
        target_minutes = config.get("target_minutes", 4)
        
        # ========== STEP 1: RAW ARTICLES BY TOPIC (from RSS) ==========
        raw_articles = fetch_all_sources(user_id=user_id)
        
        # Group raw by topic
        raw_by_topic = {}
        for art in raw_articles:
            topic = art.get("keyword", art.get("topic_slug", "unknown"))
            if topic not in raw_by_topic:
                raw_by_topic[topic] = []
            raw_by_topic[topic].append({
                "title": art.get("title", "")[:100],
                "source": art.get("source_name", ""),
                "published": str(art.get("published", ""))[:16],
                "score": art.get("score", 0),
                "url": art.get("url", "")
            })
        
        # ========== STEP 2: PENDING ARTICLES FROM CONTENT_QUEUE ==========
        # V17: Global queue, no user_id filter
        pending = supabase.table("content_queue") \
            .select("*") \
            .eq("status", "pending") \
            .execute()
        
        selected = pending.data if pending.data else []
        
        selected_by_topic = {}
        for art in selected:
            topic = art.get("keyword", art.get("topic_slug", "unknown"))
            if topic not in selected_by_topic:
                selected_by_topic[topic] = []
            selected_by_topic[topic].append({
                "title": art.get("title", "")[:100],
                "source": art.get("source_name", art.get("source", "")),
                "score": art.get("score", 0),
                "url": art.get("url", "")
            })
        
        # ========== BUILD RESPONSE BY TOPIC ==========
        all_topics = sorted(set(list(raw_by_topic.keys()) + list(selected_by_topic.keys())))
        
        topics_detail = []
        for topic in all_topics:
            raw_list = raw_by_topic.get(topic, [])
            selected_list = selected_by_topic.get(topic, [])
            
            topic_data = {
                "topic": topic,
                "raw_count": len(raw_list),
                "raw_articles": raw_list[:10],  # Max 10 per topic
                "selected_count": len(selected_list),
                "selected_articles": selected_list,
                "script": None
            }
            
            # Generate script if requested
            if with_script and selected_list:
                # Find full article data for this topic
                topic_articles = [a for a in selected if a.get("keyword") == topic]
                
                if topic_articles:
                    first_article = topic_articles[0]
                    script = generate_dialogue_segment_script(
                        title=first_article.get("title", ""),
                        content=first_article.get("processed_content", first_article.get("content", ""))[:2000],
                        source_name=first_article.get("source_name", first_article.get("source", "")),
                        word_count=config.get("words_per_article", 150),
                        style=config.get("style", "dynamique")
                    )
                    topic_data["script"] = script
            
            topics_detail.append(topic_data)
        
        return jsonify({
            "success": True,
            "format": format_type,
            "target_minutes": target_minutes,
            "total_raw": len(raw_articles),
            "total_in_queue": len(selected),
            "topics": topics_detail
        })
        
    except Exception as e:
        log.error(f"Test error: {e}")
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


@app.route("/cron/fill-queue", methods=["POST"])
def cron_fill_queue():
    """
    Fill content_queue with fresh articles from all RSS sources.
    This fetches from GSheet sources and Bing backup, then stores in DB.
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    log.info("📥 Fill queue cron triggered")
    
    def run_fill():
        try:
            from sourcing import fetch_all_sources
            
            # Fetch all sources
            articles = fetch_all_sources(user_id=None)
            log.info(f"📰 Fetched {len(articles)} articles from sources")
            
            # Store in content_queue
            inserted = 0
            for art in articles:
                try:
                    # Check if URL already exists
                    existing = supabase.table("content_queue") \
                        .select("id") \
                        .eq("url", art.get("url", "")) \
                        .execute()
                    
                    if existing.data:
                        continue  # Skip duplicates
                    
                    supabase.table("content_queue").insert({
                        "url": art.get("url", ""),
                        "title": art.get("title", "")[:500],
                        "source_name": art.get("source_name", "Unknown"),
                        "source": art.get("source_name", "Unknown"),
                        "keyword": art.get("keyword", art.get("topic_slug", "general")),
                        "source_score": art.get("score", 50),
                        "status": "pending",
                        "description": art.get("description", "")[:1000] if art.get("description") else None
                    }).execute()
                    inserted += 1
                except Exception as e:
                    log.warning(f"Could not insert article: {e}")
            
            log.info(f"✅ Fill queue complete: {inserted} new articles added")
            
        except Exception as e:
            log.error(f"❌ Fill queue error: {e}")
    
    thread = threading.Thread(target=run_fill)
    thread.start()
    
    return jsonify({"success": True, "message": "Fill queue job started"})


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


# ============================================
# V17: PIPELINE LAB ENDPOINTS
# ============================================

@app.route("/pipeline-lab/params", methods=["GET"])
def pipeline_lab_params():
    """Get default pipeline parameters."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    return jsonify(get_default_params())


@app.route("/pipeline-lab/fetch", methods=["POST"])
def pipeline_lab_fetch():
    """
    Sandbox fetch - fetch articles without saving to DB.
    
    Body:
        {
            "params": {...},  // Optional custom params
            "topics": [...]   // Optional list of topics
        }
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.get_json() or {}
        params = {**get_default_params(), **(data.get("params") or {})}
        topics = data.get("topics")
        
        result = sandbox_fetch(params, topics)
        return jsonify(result)
        
    except Exception as e:
        log.error("Pipeline lab fetch error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/pipeline-lab/cluster", methods=["POST"])
def pipeline_lab_cluster():
    """
    Sandbox cluster - cluster provided articles.
    
    Body:
        {
            "articles": [...],  // Articles from fetch step
            "params": {...}     // Optional custom params
        }
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.get_json() or {}
        articles = data.get("articles", [])
        params = {**get_default_params(), **(data.get("params") or {})}
        
        if not articles:
            return jsonify({"error": "No articles provided"}), 400
        
        result = sandbox_cluster(articles, params)
        return jsonify(result)
        
    except Exception as e:
        log.error("Pipeline lab cluster error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/pipeline-lab/select", methods=["POST"])
def pipeline_lab_select():
    """
    Sandbox select - select segments from clusters.
    
    Body:
        {
            "clusters": [...],   // Clusters from cluster step
            "articles": [...],   // Original articles (for fallback)
            "params": {...},     // Optional custom params
            "format": "flash"    // "flash" or "digest"
        }
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.get_json() or {}
        clusters = data.get("clusters", [])
        articles = data.get("articles", [])
        params = {**get_default_params(), **(data.get("params") or {})}
        format_type = data.get("format", "flash")
        
        result = sandbox_select(clusters, articles, params, format_type)
        return jsonify(result)
        
    except Exception as e:
        log.error("Pipeline lab select error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/pipeline-lab/run", methods=["POST"])
def pipeline_lab_run():
    """
    Run full pipeline in sandbox mode.
    
    Body:
        {
            "params": {...},     // Optional custom params
            "format": "flash",   // "flash" or "digest"
            "topics": [...]      // Optional list of topics
        }
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.get_json() or {}
        params = {**get_default_params(), **(data.get("params") or {})}
        format_type = data.get("format", "flash")
        topics = data.get("topics")
        
        result = sandbox_full_pipeline(params, format_type, topics)
        return jsonify(result)
        
    except Exception as e:
        log.error("Pipeline lab run error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/pipeline-lab/generate-script", methods=["POST"])
def pipeline_lab_generate_script():
    """
    Generate script from selected segments (connects to Prompt Lab).
    
    Body:
        {
            "segments": [...],   // Segments from select step
            "format": "flash",   // "flash" or "digest"
            "prompt_id": "..."   // Optional: use specific prompt from Prompt Lab
        }
    """
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.get_json() or {}
        segments = data.get("segments", [])
        format_type = data.get("format", "flash")
        prompt_id = data.get("prompt_id")
        
        if not segments:
            return jsonify({"error": "No segments provided"}), 400
        
        # Get prompt (from DB or default)
        if prompt_id:
            prompt_result = supabase.table("prompts") \
                .select("*") \
                .eq("id", prompt_id) \
                .single() \
                .execute()
            prompt_template = prompt_result.data.get("template", "") if prompt_result.data else None
        else:
            prompt_template = None
        
        # Build articles list from segments
        all_articles = []
        for seg in segments:
            all_articles.extend(seg.get("articles", []))
        
        # Generate script using existing stitcher logic
        from stitcher_v2 import generate_intro_script
        
        script = generate_intro_script(
            all_articles,
            format_type=format_type,
            custom_prompt=prompt_template
        )
        
        return jsonify({
            "script": script,
            "segments_used": len(segments),
            "articles_used": len(all_articles)
        })
        
    except Exception as e:
        log.error("Pipeline lab generate script error", error=str(e))
        return jsonify({"error": str(e)}), 500


# ============================================
# V16: PROMPT LAB - Text-only generation
# ============================================

@app.route("/prompt-lab/queue", methods=["GET"])
def prompt_lab_queue():
    """
    Get all articles in queue grouped by topic.
    V17: Global queue, no user_id filter.
    """
    try:
        # V17: Global queue - no user_id filter
        result = supabase.table("content_queue") \
            .select("id, title, url, source_name, keyword, source") \
            .eq("status", "pending") \
            .order("keyword") \
            .execute()
        
        # Group by topic
        by_topic = {}
        for article in (result.data or []):
            topic = article.get("keyword", "general")
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append({
                "id": article["id"],
                "title": article.get("title", "Sans titre"),
                "source_name": article.get("source_name", article.get("source", "Unknown")),
                "url": article.get("url", ""),
                "keyword": topic
            })
        
        return jsonify({
            "success": True,
            "total_count": len(result.data or []),
            "topics": by_topic
        })
    except Exception as e:
        log.error("Prompt lab queue error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/prompt-lab/prompts", methods=["GET"])
def prompt_lab_get_prompts():
    """
    Get main prompt and all topic intentions.
    """
    try:
        from stitcher_v2 import (
            DIALOGUE_SEGMENT_PROMPT, 
            DIALOGUE_MULTI_SOURCE_PROMPT,
            TOPIC_INTENTIONS,
            get_prompt_from_db
        )
        
        # Get main prompts (from DB or default)
        dialogue_segment = get_prompt_from_db("dialogue_segment", DIALOGUE_SEGMENT_PROMPT)
        dialogue_multi = get_prompt_from_db("dialogue_multi_source", DIALOGUE_MULTI_SOURCE_PROMPT)
        
        # Get topic intentions from DB
        topic_intentions = {}
        try:
            result = supabase.table("topics").select("keyword, editorial_intention").execute()
            for t in (result.data or []):
                if t.get("editorial_intention"):
                    topic_intentions[t["keyword"]] = t["editorial_intention"]
        except:
            pass
        
        # Merge with hardcoded defaults
        for slug, intention in TOPIC_INTENTIONS.items():
            if slug not in topic_intentions:
                topic_intentions[slug] = intention
        
        return jsonify({
            "success": True,
            "prompts": {
                "dialogue_segment": dialogue_segment,
                "dialogue_multi_source": dialogue_multi
            },
            "topic_intentions": topic_intentions
        })
    except Exception as e:
        log.error("Prompt lab get prompts error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/prompt-lab/prompts", methods=["POST"])
def prompt_lab_save_prompts():
    """
    Save prompts and topic intentions.
    """
    try:
        data = request.get_json() or {}
        
        # Save main prompt if provided
        prompt_name = data.get("prompt_name")
        prompt_content = data.get("prompt_content")
        
        if prompt_name and prompt_content:
            try:
                supabase.table("prompts").upsert({
                    "name": prompt_name,
                    "content": prompt_content
                }).execute()
                log.info(f"✅ Saved prompt: {prompt_name}")
            except Exception as e:
                log.warning(f"Could not save prompt to DB: {e}")
        
        # Save topic intention if provided
        topic_slug = data.get("topic_slug")
        topic_intention = data.get("topic_intention")
        
        if topic_slug and topic_intention is not None:
            try:
                result = supabase.table("topics") \
                    .update({"editorial_intention": topic_intention}) \
                    .eq("keyword", topic_slug) \
                    .execute()
                
                if not result.data:
                    supabase.table("topics").insert({
                        "keyword": topic_slug,
                        "name": topic_slug.replace("_", " ").title(),
                        "editorial_intention": topic_intention
                    }).execute()
                
                log.info(f"✅ Saved topic intention: {topic_slug}")
            except Exception as e:
                log.warning(f"Could not save topic intention to DB: {e}")
        
        return jsonify({"success": True})
    except Exception as e:
        log.error("Prompt lab save error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/prompt-lab/generate", methods=["POST"])
def prompt_lab_generate():
    """
    Generate TEXT ONLY (no audio) for testing prompts.
    Uses content already in database when available, falls back to extraction only if needed.
    """
    import time
    start_time = time.time()
    
    try:
        data = request.get_json() or {}
        article_ids = data.get("article_ids", [])
        topic = data.get("topic", "general")
        custom_prompt = data.get("custom_prompt")
        custom_intention = data.get("custom_intention")
        use_enrichment = data.get("use_enrichment", False)
        
        # NEW: Accept articles directly from frontend (from pipeline results)
        articles_data = data.get("articles", [])
        
        if not article_ids and not articles_data:
            return jsonify({"error": "article_ids or articles required"}), 400
        
        # If articles provided directly, use them
        if articles_data:
            articles = articles_data
        else:
            # Get articles from queue
            result = supabase.table("content_queue") \
                .select("*") \
                .in_("id", article_ids) \
                .execute()
            
            if not result.data:
                return jsonify({"error": "No articles found"}), 404
            
            articles = result.data
        
        from stitcher_v2 import (
            enrich_content_with_perplexity,
            get_topic_intention,
            FORMAT_CONFIG,
            DIALOGUE_SEGMENT_PROMPT,
            DIALOGUE_MULTI_SOURCE_PROMPT,
            get_prompt_from_db
        )
        from groq import Groq
        
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return jsonify({"error": "GROQ_API_KEY not configured"}), 500
        
        groq_client = Groq(api_key=groq_api_key)
        
        # Build content from articles - EXTRACT IF NEEDED
        combined_content = ""
        combined_title = ""
        source_names = []
        
        log.info(f"📝 Processing {len(articles)} articles for generation")
        
        for article in articles:
            title = article.get("title", "Sans titre")
            source_name = article.get("source_name", article.get("source", "Unknown"))
            url = article.get("url", "")
            
            if not combined_title:
                combined_title = title
            
            source_names.append(source_name)
            
            # Use content already available (from pipeline or DB)
            content = article.get("processed_content") or article.get("content") or article.get("description") or ""
            
            log.info(f"  📄 Article: {title[:50]}...")
            log.info(f"    - content available: {len(content)} chars")
            
            # Extract if content is missing OR too short (less than 200 chars)
            if (not content or len(content) < 200) and url:
                log.info(f"⚡ Extracting content from URL: {url[:60]}...")
                from extractor import extract_content
                extraction = extract_content(url)
                if extraction:
                    _, extracted_title, extracted_content = extraction
                    if extracted_content and len(extracted_content) > len(content):
                        content = extracted_content
                        log.info(f"  ✅ Extracted {len(content)} chars")
                    if not combined_title and extracted_title:
                        combined_title = extracted_title
                else:
                    log.warning(f"  ❌ Extraction failed for {url[:60]}")
            
            if content:
                combined_content += f"\n\n--- SOURCE: {source_name} ---\n{title}\n{content[:2000]}"
        
        log.info(f"📊 Total content for LLM: {len(combined_content)} chars from {len(source_names)} sources")
        
        if not combined_content:
            return jsonify({"error": "No content available for articles"}), 400
        
        # Get topic intention
        if custom_intention:
            topic_intention = f"\n{custom_intention}\n"
        else:
            topic_intention = get_topic_intention(topic)
        
        # Perplexity enrichment
        # FIX: enrich_content_with_perplexity returns a single string, not a tuple
        enriched_context = None
        perplexity_citations = []
        
        if use_enrichment:
            enriched_context = enrich_content_with_perplexity(
                combined_title, 
                combined_content[:2000], 
                source_names[0] if source_names else "Unknown"
            )
            # Note: perplexity_citations stays empty as the function doesn't return citations
        
        # Build full content for LLM
        if enriched_context:
            full_content = f"""ARTICLE PRINCIPAL:
{combined_content[:3000]}

CONTEXTE ENRICHI (sources additionnelles):
{enriched_context}"""
        else:
            full_content = combined_content[:4000]
        
        # Get prompt template
        # Use higher word count for full script (not just one segment)
        config = FORMAT_CONFIG["flash"]
        target_word_count = 300  # Full script, not just one segment
        
        # Common template variables
        template_vars = {
            "word_count": target_word_count,
            "topic_intention": topic_intention,
            "topic": topic,
            "theme": topic,  # Alias for topic
            "style": config["style"],
            "previous_segment_rule": "",
            "previous_segment_context": "",
            "source_count": len(articles),
            "sources_content": full_content,
            "title": combined_title,
            "source_label": f"Source: {source_names[0]}" if source_names else "Source inconnue",
            "content": full_content,
            "attribution_instruction": f'"Selon {source_names[0]}..."' if source_names else '"Selon les sources..."',
        }
        
        if len(articles) > 1:
            if custom_prompt:
                prompt_template = custom_prompt
            else:
                prompt_template = get_prompt_from_db("dialogue_multi_source", DIALOGUE_MULTI_SOURCE_PROMPT)
        else:
            if custom_prompt:
                prompt_template = custom_prompt
            else:
                prompt_template = get_prompt_from_db("dialogue_segment", DIALOGUE_SEGMENT_PROMPT)
        
        # Safe format - ignore missing variables
        try:
            prompt = prompt_template.format(**template_vars)
        except KeyError as e:
            log.warning(f"⚠️ Missing template variable: {e}, using partial format")
            # Use partial formatting for unknown variables
            import re
            prompt = prompt_template
            for key, value in template_vars.items():
                prompt = prompt.replace("{" + key + "}", str(value))
        
        # Call Groq for script generation
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Tu es un scripteur de podcast expert. Tu écris des dialogues naturels et informatifs."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        script = response.choices[0].message.content.strip()
        
        word_count = len(script.split())
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        return jsonify({
            "success": True,
            "script": script,
            "enriched_context": enriched_context,
            "perplexity_citations": perplexity_citations,
            "word_count": word_count,
            "generation_time_ms": generation_time_ms,
            "topic": topic,
            "topic_intention": topic_intention,
            "sources": source_names,
            "prompt_used": prompt[:500] + "..." if len(prompt) > 500 else prompt
        })
        
    except Exception as e:
        log.error("Prompt lab generate error", error=str(e))
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ============================================
# PIPELINE V2 - B2B Intelligence Platform
# ============================================

@app.route("/cron/daily", methods=["POST", "GET"])
def cron_daily():
    """
    Daily CRON endpoint - runs the full intelligence pipeline.
    
    Should be triggered at 6h Paris time via Render Cron.
    
    Query params:
    - topics: Comma-separated topics (default: ia,macro,asia)
    - dry_run: Don't store to DB (default: false)
    - with_podcast: Also generate podcast (default: false)
    """
    try:
        # Parse params
        topics_str = request.args.get("topics") or "ia,macro,asia"
        topics = [t.strip() for t in topics_str.split(",")]
        dry_run = request.args.get("dry_run", "false").lower() == "true"
        with_podcast = request.args.get("with_podcast", "false").lower() == "true"
        
        log.info(f"🌅 Daily CRON triggered", topics=topics, dry_run=dry_run)
        
        from daily_cron import run_daily_cron
        
        results = run_daily_cron(
            topics=topics,
            generate_podcast=with_podcast,
            dry_run=dry_run
        )
        
        return jsonify({
            "success": True,
            "message": "Daily CRON completed",
            "results": results
        })
        
    except ImportError as e:
        log.error("Daily CRON import error", error=str(e))
        return jsonify({
            "success": False,
            "error": f"Import error: {str(e)}",
            "hint": "Make sure daily_cron.py is deployed"
        }), 500
        
    except Exception as e:
        log.error("Daily CRON error", error=str(e))
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


@app.route("/api/intelligence/today", methods=["GET"])
def intelligence_today():
    """
    Get today's intelligence briefings.
    
    Query params:
    - topics: Comma-separated topics (default: ia,macro,asia)
    """
    try:
        topics_str = request.args.get("topics") or "ia,macro,asia"
        topics = [t.strip() for t in topics_str.split(",")]
        
        from daily_cron import get_todays_summaries
        
        summaries = get_todays_summaries(topics)
        
        return jsonify({
            "success": True,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "topics": topics,
            "summaries": summaries,
            "count": len(summaries)
        })
        
    except Exception as e:
        log.error("Intelligence today error", error=str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/intelligence/archive", methods=["GET"])
def intelligence_archive():
    """
    Get archive of past briefings.
    
    Query params:
    - date: Specific date (YYYY-MM-DD)
    - limit: Number of dates to return (default: 30)
    """
    try:
        date = request.args.get("date")
        limit = int(request.args.get("limit") or 30)
        
        from daily_cron import get_summaries_by_date, get_archive_dates
        
        if date:
            # Get summaries for specific date
            summaries = get_summaries_by_date(date)
            return jsonify({
                "success": True,
                "date": date,
                "summaries": summaries,
                "count": len(summaries)
            })
        else:
            # Get list of available dates
            dates = get_archive_dates(limit)
            return jsonify({
                "success": True,
                "dates": dates
            })
        
    except Exception as e:
        log.error("Intelligence archive error", error=str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/favorites/toggle", methods=["POST"])
def toggle_favorite():
    """
    Toggle favorite status for an item.
    
    Body:
    - user_id: UUID
    - item_type: 'summary' | 'cluster' | 'episode' | 'article'
    - item_id: UUID
    - note: Optional note
    """
    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        item_type = data.get("item_type")
        item_id = data.get("item_id")
        note = data.get("note")
        
        if not all([user_id, item_type, item_id]):
            return jsonify({"error": "Missing required fields"}), 400
        
        from db import supabase
        
        # Check if already favorited
        existing = supabase.table("user_favorites") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("item_type", item_type) \
            .eq("item_id", item_id) \
            .execute()
        
        if existing.data:
            # Remove favorite
            supabase.table("user_favorites") \
                .delete() \
                .eq("id", existing.data[0]["id"]) \
                .execute()
            
            return jsonify({
                "success": True,
                "action": "removed",
                "is_favorited": False
            })
        else:
            # Add favorite
            supabase.table("user_favorites").insert({
                "user_id": user_id,
                "item_type": item_type,
                "item_id": item_id,
                "note": note
            }).execute()
            
            return jsonify({
                "success": True,
                "action": "added",
                "is_favorited": True
            })
        
    except Exception as e:
        log.error("Toggle favorite error", error=str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/favorites", methods=["GET"])
def get_favorites():
    """
    Get user's favorites.
    
    Query params:
    - user_id: UUID (required)
    - item_type: Filter by type (optional)
    """
    try:
        user_id = request.args.get("user_id")
        item_type = request.args.get("item_type")
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        from db import supabase
        
        query = supabase.table("user_favorites") \
            .select("*, cluster_summaries(title, topic, summary_markdown)") \
            .eq("user_id", user_id)
        
        if item_type:
            query = query.eq("item_type", item_type)
        
        result = query.order("created_at", desc=True).execute()
        
        return jsonify({
            "success": True,
            "favorites": result.data if result.data else []
        })
        
    except Exception as e:
        log.error("Get favorites error", error=str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/pipeline/v2/test", methods=["GET", "POST"])
def pipeline_v2_test():
    """
    Test Pipeline V2 - fetches, classifies, clusters, scores articles.
    
    Query params:
    - topics: Comma-separated topics (default: ia,macro,asia)
    - dry_run: Don't store to DB (default: true)
    - limit: Max articles per source (default: 5)
    """
    try:
        # Parse params
        if request.method == "POST":
            data = request.get_json() or {}
        else:
            data = {}
        
        topics_str = request.args.get("topics") or data.get("topics") or "ia,macro,asia"
        topics = [t.strip() for t in topics_str.split(",")]
        dry_run = request.args.get("dry_run", "true").lower() == "true"
        limit = int(request.args.get("limit") or data.get("limit") or 5)
        
        log.info(f"🚀 Pipeline V2 test started", topics=topics, dry_run=dry_run, limit=limit)
        
        # Import pipeline V2
        from pipeline_v2 import run_pipeline
        
        # Run pipeline
        results = run_pipeline(
            topics=topics,
            mvp_only=True,
            do_fetch=True,
            do_classify=True,
            do_cluster=True,
            do_score=True,
            do_store=not dry_run,
        )
        
        return jsonify({
            "success": True,
            "message": "Pipeline V2 completed",
            "dry_run": dry_run,
            "results": results
        })
        
    except ImportError as e:
        log.error("Pipeline V2 import error", error=str(e))
        return jsonify({
            "success": False,
            "error": f"Import error: {str(e)}",
            "hint": "Make sure pipeline_v2.py, sourcing_v2.py, classifier.py, scoring.py are deployed"
        }), 500
        
    except Exception as e:
        log.error("Pipeline V2 error", error=str(e))
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


@app.route("/api/pipeline/v2/sources", methods=["GET"])
def pipeline_v2_sources():
    """
    Get source library stats from GSheet.
    """
    try:
        from sourcing_v2 import SourceLibrary
        
        library = SourceLibrary()
        stats = library.get_stats()
        
        # Get sample sources
        mvp_sources = library.get_mvp_sources()
        sample = mvp_sources[:10] if mvp_sources else []
        
        # Clean sample for JSON (remove row_index, etc.)
        sample_clean = []
        for s in sample:
            sample_clean.append({
                "topic": s["topic"],
                "source_name": s["source_name"],
                "tier": s["tier"],
                "score": s["score"],
            })
        
        return jsonify({
            "success": True,
            "stats": stats,
            "sample_sources": sample_clean
        })
        
    except Exception as e:
        log.error("Sources endpoint error", error=str(e))
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


@app.route("/api/pipeline/v2/fetch", methods=["GET", "POST"])
def pipeline_v2_fetch():
    """
    Fetch articles only (no classification/clustering).
    
    Query params:
    - topics: Comma-separated topics
    - limit: Max articles per source
    """
    try:
        topics_str = request.args.get("topics") or "ia"
        topics = [t.strip() for t in topics_str.split(",")]
        limit = int(request.args.get("limit") or 3)
        
        from sourcing_v2 import SourceLibrary, fetch_all_sources
        
        library = SourceLibrary()
        articles = fetch_all_sources(
            library,
            topics=topics,
            mvp_only=True,
            max_articles_per_source=limit
        )
        
        # Clean for JSON
        articles_clean = []
        for a in articles[:50]:  # Limit response size
            articles_clean.append({
                "title": a.get("title", "")[:100],
                "url": a.get("url", ""),
                "source_name": a.get("source_name", ""),
                "source_tier": a.get("source_tier", ""),
                "topic": a.get("topic", ""),
            })
        
        return jsonify({
            "success": True,
            "topics": topics,
            "total_fetched": len(articles),
            "articles": articles_clean
        })
        
    except Exception as e:
        log.error("Fetch endpoint error", error=str(e))
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


# ============================================
# PROMPT LAB V2 - Full Pipeline Control
# ============================================

@app.route("/api/lab/v2/config", methods=["GET"])
def lab_v2_config():
    """Get Prompt Lab configuration (models, prompts, params)."""
    try:
        from prompt_lab_v2 import get_lab_config
        config = get_lab_config()
        return jsonify({"success": True, **config})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/lab/v2/fetch", methods=["POST"])
def lab_v2_fetch():
    """Step 1: Fetch articles from sources."""
    try:
        from prompt_lab_v2 import lab_fetch, MVP_TOPICS
        
        data = request.get_json() or {}
        topics = data.get("topics", MVP_TOPICS)
        max_per_source = data.get("max_per_source", 10)
        
        result = lab_fetch(topics=topics, max_per_source=max_per_source)
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/classify", methods=["POST"])
def lab_v2_classify():
    """Step 2: Classify articles by topic."""
    try:
        from prompt_lab_v2 import lab_classify, MVP_TOPICS
        
        data = request.get_json() or {}
        articles = data.get("articles", [])
        topics = data.get("topics", MVP_TOPICS)
        model = data.get("model", "llama-3.3-70b-versatile")
        prompt_template = data.get("prompt_template")
        
        result = lab_classify(
            articles=articles,
            topics=topics,
            model=model,
            prompt_template=prompt_template
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/embed", methods=["POST"])
def lab_v2_embed():
    """Step 3: Generate embeddings."""
    try:
        from prompt_lab_v2 import lab_embed
        
        data = request.get_json() or {}
        articles = data.get("articles", [])
        
        result = lab_embed(articles=articles)
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/cluster", methods=["POST"])
def lab_v2_cluster():
    """Step 4: Cluster articles."""
    try:
        from prompt_lab_v2 import lab_cluster
        
        data = request.get_json() or {}
        articles = data.get("articles", [])
        eps = data.get("eps", 0.65)
        min_samples = data.get("min_samples", 2)
        
        result = lab_cluster(articles=articles, eps=eps, min_samples=min_samples)
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/score", methods=["POST"])
def lab_v2_score():
    """Step 5: Score clusters."""
    try:
        from prompt_lab_v2 import lab_score
        
        data = request.get_json() or {}
        clusters = data.get("clusters", {})
        params = data.get("params")
        
        # Convert string keys back to int
        clusters_int = {int(k): v for k, v in clusters.items()}
        
        result = lab_score(clusters=clusters_int, params=params)
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/enrich", methods=["POST"])
def lab_v2_enrich():
    """Step 6: Enrich cluster with Perplexity."""
    try:
        from prompt_lab_v2 import lab_enrich
        
        data = request.get_json() or {}
        cluster = data.get("cluster", {})
        
        result = lab_enrich(cluster=cluster)
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/summarize", methods=["POST"])
def lab_v2_summarize():
    """Step 7: Generate cluster summary."""
    try:
        from prompt_lab_v2 import lab_summarize
        
        data = request.get_json() or {}
        cluster = data.get("cluster", {})
        context = data.get("context", "")
        model = data.get("model", "llama-3.3-70b-versatile")
        prompt_template = data.get("prompt_template")
        
        result = lab_summarize(
            cluster=cluster,
            context=context,
            model=model,
            prompt_template=prompt_template
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/script", methods=["POST"])
def lab_v2_script():
    """Step 8: Generate podcast script."""
    try:
        from prompt_lab_v2 import lab_script
        
        data = request.get_json() or {}
        summary = data.get("summary", {})
        context = data.get("context", "")
        enrichment = data.get("enrichment", {})
        model = data.get("model", "llama-3.3-70b-versatile")
        prompt_template = data.get("prompt_template")
        word_count = data.get("word_count", 375)
        
        result = lab_script(
            summary=summary,
            enrichment=enrichment,
            model=model,
            prompt_template=prompt_template,
            word_count=word_count
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/store", methods=["POST"])
def lab_v2_store():
    """Step 9: Store results to database."""
    try:
        from prompt_lab_v2 import lab_store
        
        data = request.get_json() or {}
        articles = data.get("articles")
        clusters = data.get("clusters")
        summaries = data.get("summaries")
        dry_run = data.get("dry_run", True)
        
        result = lab_store(
            articles=articles,
            clusters=clusters,
            summaries=summaries,
            dry_run=dry_run
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/v2/prompts", methods=["GET", "POST"])
def lab_v2_prompts():
    """Get or save prompts."""
    try:
        from prompt_lab_v2 import get_prompts, save_prompt
        
        if request.method == "GET":
            prompts = get_prompts()
            return jsonify({"success": True, "prompts": prompts})
        else:
            data = request.get_json() or {}
            name = data.get("name")
            template = data.get("template")
            
            if not name or not template:
                return jsonify({"success": False, "error": "name and template required"}), 400
            
            result = save_prompt(name, template)
            return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/lab/v2/params", methods=["GET", "POST"])
def lab_v2_params():
    """Get or save parameters."""
    try:
        from prompt_lab_v2 import get_params, save_params
        
        if request.method == "GET":
            params = get_params()
            return jsonify({"success": True, "params": params})
        else:
            data = request.get_json() or {}
            params = data.get("params")
            
            if not params:
                return jsonify({"success": False, "error": "params required"}), 400
            
            result = save_params(params)
            return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================
# SIGNAL DETECTION API
# ============================================

@app.route("/api/signals", methods=["GET"])
def get_signals():
    """Get signals list with filters."""
    try:
        topic = request.args.get("topic")
        status = request.args.get("status")
        severity = request.args.get("severity")
        limit = int(request.args.get("limit", 20))
        
        query = supabase.table("signals").select(
            "*, clusters(name, article_count, source_names)"
        ).order("detected_at", desc=True).limit(limit)
        
        if topic:
            query = query.eq("topic", topic)
        if status:
            query = query.eq("status", status)
        if severity:
            query = query.eq("severity", severity)
        
        result = query.execute()
        
        return jsonify({
            "success": True,
            "signals": result.data or [],
            "count": len(result.data or [])
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/signals/<signal_id>", methods=["GET"])
def get_signal(signal_id: str):
    """Get single signal with full details."""
    try:
        result = supabase.table("signals").select(
            "*, clusters(*)"
        ).eq("id", signal_id).single().execute()
        
        if not result.data:
            return jsonify({"success": False, "error": "Signal not found"}), 404
        
        signal = result.data
        cluster_id = signal.get("cluster_id")
        
        # Get articles for this cluster
        articles = []
        if cluster_id:
            articles_result = supabase.table("articles").select(
                "id, title, url, source_name, source_tier, published_at"
            ).eq("cluster_id", cluster_id).order("published_at", desc=True).execute()
            articles = articles_result.data or []
        
        return jsonify({
            "success": True,
            "signal": signal,
            "articles": articles
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/signals/detect", methods=["POST"])
def trigger_detection():
    """Trigger signal detection manually."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from signal_detector import run_detection_cycle
        
        data = request.get_json() or {}
        topic = data.get("topic")
        
        results = run_detection_cycle(topic)
        
        return jsonify({
            "success": True,
            **results
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/signals/<signal_id>/feedback", methods=["POST"])
def signal_feedback(signal_id: str):
    """Record feedback on a signal."""
    try:
        from signal_detector import record_feedback
        
        data = request.get_json() or {}
        rating = data.get("rating")  # useful, not_useful, acted_on
        comment = data.get("comment")
        
        if rating not in ["useful", "not_useful", "acted_on"]:
            return jsonify({"success": False, "error": "Invalid rating"}), 400
        
        result = record_feedback(supabase, signal_id, rating, comment)
        
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/signals/stats", methods=["GET"])
def signal_stats():
    """Get signal statistics."""
    try:
        from datetime import timedelta
        
        # Get signals from last 30 days
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        
        signals_result = supabase.table("signals").select(
            "id, topic, severity, status, total_score"
        ).gte("detected_at", thirty_days_ago).execute()
        
        signals = signals_result.data or []
        
        # Get feedback
        feedback_result = supabase.table("signal_feedback").select(
            "signal_id, rating"
        ).execute()
        
        feedbacks = feedback_result.data or []
        feedback_by_signal = {}
        for f in feedbacks:
            feedback_by_signal[f["signal_id"]] = f["rating"]
        
        # Calculate stats
        stats = {
            "total_signals": len(signals),
            "by_topic": {},
            "by_severity": {},
            "feedback": {
                "useful": 0,
                "not_useful": 0,
                "acted_on": 0,
                "no_feedback": 0
            },
            "precision": 0
        }
        
        for s in signals:
            # By topic
            topic = s["topic"]
            if topic not in stats["by_topic"]:
                stats["by_topic"][topic] = 0
            stats["by_topic"][topic] += 1
            
            # By severity
            severity = s["severity"]
            if severity not in stats["by_severity"]:
                stats["by_severity"][severity] = 0
            stats["by_severity"][severity] += 1
            
            # Feedback
            fb = feedback_by_signal.get(s["id"])
            if fb:
                stats["feedback"][fb] += 1
            else:
                stats["feedback"]["no_feedback"] += 1
        
        # Calculate precision
        total_rated = stats["feedback"]["useful"] + stats["feedback"]["not_useful"] + stats["feedback"]["acted_on"]
        if total_rated > 0:
            useful = stats["feedback"]["useful"] + stats["feedback"]["acted_on"]
            stats["precision"] = round(useful / total_rated * 100, 1)
        
        # Get thresholds
        thresholds_result = supabase.table("signal_thresholds").select("*").execute()
        stats["thresholds"] = thresholds_result.data or []
        
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/signals/thresholds", methods=["GET", "POST"])
def signal_thresholds():
    """Get or update signal thresholds."""
    try:
        if request.method == "GET":
            result = supabase.table("signal_thresholds").select("*").execute()
            return jsonify({"success": True, "thresholds": result.data or []})
        else:
            if not verify_auth():
                return jsonify({"error": "Unauthorized"}), 401
            
            data = request.get_json() or {}
            topic = data.get("topic")
            updates = {k: v for k, v in data.items() if k != "topic" and k in [
                "min_velocity", "min_score", "min_authority_sources", "min_total_sources"
            ]}
            
            if not topic or not updates:
                return jsonify({"success": False, "error": "topic and updates required"}), 400
            
            supabase.table("signal_thresholds").update(updates).eq("topic", topic).execute()
            
            return jsonify({"success": True, "message": f"Thresholds updated for {topic}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/signals/recalibrate", methods=["POST"])
def recalibrate():
    """Recalibrate thresholds based on feedback."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from signal_detector import recalibrate_thresholds, apply_recommendations
        
        data = request.get_json() or {}
        topic = data.get("topic")
        apply_now = data.get("apply", False)
        
        if not topic:
            return jsonify({"success": False, "error": "topic required"}), 400
        
        result = recalibrate_thresholds(supabase, topic)
        
        if apply_now and result.get("recommended_velocity"):
            apply_result = apply_recommendations(supabase, topic)
            result["applied"] = apply_result
        
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================
# PIPELINE OBSERVER API (Lab)
# ============================================

@app.route("/api/lab/pipeline/run", methods=["POST"])
def lab_pipeline_run():
    """Run full pipeline and return all intermediate steps."""
    try:
        from prompt_lab_v2 import lab_fetch, lab_classify, lab_cluster, lab_score
        from alternative_sources import fetch_alternative_sources
        import time
        import httpx
        import os
        
        data = request.get_json() or {}
        topics = data.get("topics", ["ia", "macro", "asia"])
        max_age_days = data.get("max_age_days", 3)
        include_alternative = data.get("include_alternative", True)
        
        pipeline_result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "steps": {}
        }
        
        # Step 1: Fetch RSS sources
        step1_start = time.time()
        fetch_result = lab_fetch(topics=topics, max_age_days_generalist=max_age_days)
        articles = fetch_result.get("articles", [])
        
        # Step 1b: Fetch alternative sources (ArXiv, SEC, GitHub, Reddit)
        alt_articles = []
        alt_stats = {}
        if include_alternative:
            alt_articles, alt_stats = fetch_alternative_sources(
                include_arxiv=True,
                include_sec=True,
                include_github=True,
                include_reddit=True
            )
            articles.extend(alt_articles)
        
        pipeline_result["steps"]["fetch"] = {
            "duration_ms": int((time.time() - step1_start) * 1000),
            "total_articles": len(articles),
            "rss_articles": len(fetch_result.get("articles", [])),
            "alternative_articles": len(alt_articles),
            "alternative_stats": alt_stats,
            "by_topic": {},
            "by_tier": {"authority": 0, "generalist": 0, "corporate": 0},
            "by_source_type": {},
            "articles": [
                {
                    "title": a.get("title", "")[:80],
                    "url": a.get("url", ""),
                    "source_name": a.get("source_name", ""),
                    "source_tier": a.get("source_tier", "generalist"),
                    "topic": a.get("topic", "unknown"),
                    "source_type": a.get("source_type", "rss")
                }
                for a in articles[:50]
            ],
            "failed_sources": fetch_result.get("failed_sources", []),
            "failed_count": fetch_result.get("failed_count", 0)
        }
        
        for a in articles:
            topic = a.get("topic", "unknown")
            tier = a.get("source_tier", "generalist")
            source_type = a.get("source_type", "rss")
            
            if topic not in pipeline_result["steps"]["fetch"]["by_topic"]:
                pipeline_result["steps"]["fetch"]["by_topic"][topic] = 0
            pipeline_result["steps"]["fetch"]["by_topic"][topic] += 1
            
            if tier in pipeline_result["steps"]["fetch"]["by_tier"]:
                pipeline_result["steps"]["fetch"]["by_tier"][tier] += 1
            
            if source_type not in pipeline_result["steps"]["fetch"]["by_source_type"]:
                pipeline_result["steps"]["fetch"]["by_source_type"][source_type] = 0
            pipeline_result["steps"]["fetch"]["by_source_type"][source_type] += 1
        
        # Step 2: Embedding
        step2_start = time.time()
        openai_key = os.getenv("OPENAI_API_KEY")
        embedded_count = 0
        
        if openai_key and articles:
            # Batch embed (max 50 articles to save cost/time)
            articles_to_embed = articles[:50]
            texts_to_embed = []
            
            for a in articles_to_embed:
                text = f"{a.get('title', '')}\n\n{a.get('description', '')}"
                texts_to_embed.append(text[:2000])  # Limit text length
            
            try:
                response = httpx.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "text-embedding-3-small",
                        "input": texts_to_embed
                    },
                    timeout=60
                )
                response.raise_for_status()
                embeddings_data = response.json()
                
                for i, emb_data in enumerate(embeddings_data.get("data", [])):
                    if i < len(articles_to_embed):
                        articles_to_embed[i]["embedding"] = emb_data["embedding"]
                        embedded_count += 1
                
            except Exception as e:
                log.error(f"Embedding error: {e}")
        
        pipeline_result["steps"]["embedding"] = {
            "duration_ms": int((time.time() - step2_start) * 1000),
            "embedded_count": embedded_count,
            "total_articles": len(articles)
        }
        
        # Step 3: Clustering
        step3_start = time.time()
        cluster_result = lab_cluster(
            articles=articles,
            eps=data.get("dbscan_eps", 0.65),
            min_samples=data.get("dbscan_min_samples", 2)
        )
        
        # Extract cluster info for display
        cluster_info = cluster_result.get("cluster_info", [])
        clusters_dict = cluster_result.get("clusters", {})
        
        # Build displayable clusters
        display_clusters = []
        for info in cluster_info:
            if info.get("cluster_id") != -1:  # Skip noise
                cluster_articles = clusters_dict.get(info["cluster_id"], [])
                display_clusters.append({
                    "id": str(info["cluster_id"]),
                    "name": info.get("name", f"Cluster {info['cluster_id']}"),
                    "topic": cluster_articles[0].get("topic", "unknown") if cluster_articles else "unknown",
                    "article_count": info.get("count", 0),
                    "sources": info.get("sources", []),
                    "articles": info.get("articles", [])[:15]  # Show more articles
                })
        
        pipeline_result["steps"]["cluster"] = {
            "duration_ms": int((time.time() - step3_start) * 1000),
            "total_clusters": cluster_result.get("cluster_count", 0),
            "noise_count": cluster_result.get("noise_count", 0),
            "clusters": display_clusters
        }
        
        # Step 4: Velocity (simulated since no history yet)
        step4_start = time.time()
        velocity_data = []
        
        for cluster in display_clusters:
            article_count = cluster.get("article_count", 0)
            # Simulate baseline as 1/3 of current (meaning 3x velocity)
            baseline = max(0.5, article_count / 3)
            velocity = article_count / baseline
            
            velocity_data.append({
                "cluster_id": cluster.get("id"),
                "cluster_name": cluster.get("name", "Unknown"),
                "topic": cluster.get("topic", "unknown"),
                "article_count": article_count,
                "baseline": round(baseline, 2),
                "current": article_count,
                "velocity": round(velocity, 2)
            })
        
        velocity_data.sort(key=lambda x: x["velocity"], reverse=True)
        
        pipeline_result["steps"]["velocity"] = {
            "duration_ms": int((time.time() - step4_start) * 1000),
            "data": velocity_data
        }
        
        # Step 5: Scoring
        step5_start = time.time()
        
        # Get thresholds from DB
        thresholds_result = supabase.table("signal_thresholds").select("*").execute()
        thresholds_by_topic = {t["topic"]: t for t in (thresholds_result.data or [])}
        
        scoring_data = []
        for i, cluster in enumerate(display_clusters):
            topic = cluster.get("topic", "ia")
            thresholds = thresholds_by_topic.get(topic, {
                "min_velocity": 5.0,
                "min_score": 60,
                "min_authority_sources": 1,
                "min_total_sources": 3
            })
            
            vel_info = velocity_data[i] if i < len(velocity_data) else {"velocity": 1}
            velocity = vel_info.get("velocity", 1)
            
            # Get articles for this cluster
            cluster_id_int = int(cluster.get("id", -1))
            cluster_articles = clusters_dict.get(cluster_id_int, [])
            
            # Count by tier
            authority = len([a for a in cluster_articles if a.get("source_tier") == "authority"])
            generalist = len([a for a in cluster_articles if a.get("source_tier") == "generalist"])
            corporate = len([a for a in cluster_articles if a.get("source_tier") == "corporate"])
            
            # Calculate score components
            velocity_points = min(30, velocity * 6)
            source_points = min(15, authority * 10) + min(10, generalist * 2)
            
            sources = cluster.get("sources", [])
            diversity_points = min(15, len(sources) * 3)
            novelty_points = 15  # Default for new clusters
            volume_points = min(10, cluster.get("article_count", 0) * 2)
            
            total = min(100, velocity_points + source_points + diversity_points + novelty_points + volume_points)
            
            # Check validity
            is_valid = False
            min_auth = thresholds.get("min_authority_sources", 1)
            min_vel = thresholds.get("min_velocity", 5.0)
            min_total = thresholds.get("min_total_sources", 3)
            
            if authority >= min_auth and velocity >= min_vel * 0.6:
                is_valid = True
            elif len(sources) >= min_total and velocity >= min_vel:
                is_valid = True
            
            passes_threshold = total >= thresholds.get("min_score", 60) and is_valid
            
            # Determine severity
            if total >= 85:
                severity = "breaking"
            elif total >= 70:
                severity = "alert"
            elif total >= 60:
                severity = "digest"
            else:
                severity = "log"
            
            scoring_data.append({
                "cluster_id": cluster.get("id"),
                "cluster_name": cluster.get("name", "Unknown"),
                "topic": topic,
                "breakdown": {
                    "velocity": round(velocity_points, 1),
                    "sources": round(source_points, 1),
                    "diversity": round(diversity_points, 1),
                    "novelty": novelty_points,
                    "volume": volume_points
                },
                "source_mix": {
                    "authority": authority,
                    "generalist": generalist,
                    "corporate": corporate
                },
                "total_score": round(total),
                "is_valid": is_valid,
                "passes_threshold": passes_threshold,
                "severity": severity,
                "threshold_used": thresholds.get("min_score", 60)
            })
        
        scoring_data.sort(key=lambda x: x["total_score"], reverse=True)
        
        pipeline_result["steps"]["scoring"] = {
            "duration_ms": int((time.time() - step5_start) * 1000),
            "data": scoring_data
        }
        
        # Step 6: Signals
        signals_generated = [s for s in scoring_data if s["passes_threshold"]]
        signals_rejected = [s for s in scoring_data if not s["passes_threshold"]]
        
        pipeline_result["steps"]["signals"] = {
            "generated": signals_generated,
            "rejected": signals_rejected,
            "generated_count": len(signals_generated),
            "rejected_count": len(signals_rejected)
        }
        
        # Add thresholds info
        pipeline_result["thresholds"] = thresholds_result.data or []
        
        return jsonify({"success": True, "pipeline": pipeline_result})
    
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/cluster/<cluster_id>", methods=["GET"])
def lab_cluster_detail(cluster_id: str):
    """Get detailed info about a specific cluster."""
    try:
        # Get cluster
        cluster_result = supabase.table("clusters").select("*").eq("id", cluster_id).single().execute()
        
        if not cluster_result.data:
            return jsonify({"success": False, "error": "Cluster not found"}), 404
        
        cluster = cluster_result.data
        
        # Get articles
        articles_result = supabase.table("articles").select(
            "id, title, url, source_name, source_tier, description, published_at, first_seen_at"
        ).eq("cluster_id", cluster_id).order("published_at", desc=True).execute()
        
        articles = articles_result.data or []
        
        # Calculate velocity
        from signal_detector import calculate_velocity
        velocity = calculate_velocity(supabase, cluster_id)
        
        # Get thresholds for this topic
        topic = cluster.get("topic", "ia")
        thresholds_result = supabase.table("signal_thresholds").select("*").eq("topic", topic).single().execute()
        thresholds = thresholds_result.data or {}
        
        return jsonify({
            "success": True,
            "cluster": cluster,
            "articles": articles,
            "velocity": velocity,
            "thresholds": thresholds
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/lab/force-signal", methods=["POST"])
def lab_force_signal():
    """Force create a signal from a cluster (manual override)."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.get_json() or {}
        cluster_id = data.get("cluster_id")
        
        if not cluster_id:
            return jsonify({"success": False, "error": "cluster_id required"}), 400
        
        # Get cluster
        cluster_result = supabase.table("clusters").select("*").eq("id", cluster_id).single().execute()
        cluster = cluster_result.data
        
        if not cluster:
            return jsonify({"success": False, "error": "Cluster not found"}), 404
        
        # Create signal manually
        signal = {
            "topic": cluster.get("topic"),
            "title": cluster.get("name", "Manual Signal"),
            "slug": f"manual-{cluster_id[:8]}-{int(time.time())}",
            "cluster_id": cluster_id,
            "velocity_score": 0,
            "velocity_details": {"manual": True},
            "source_quality_score": 0,
            "source_mix": {
                "authority": cluster.get("authority_count", 0),
                "generalist": cluster.get("generalist_count", 0),
                "corporate": cluster.get("corporate_count", 0)
            },
            "total_score": 100,
            "score_breakdown": {"manual_override": 100},
            "status": "detected",
            "severity": "alert",
            "detected_at": datetime.now(timezone.utc).isoformat()
        }
        
        result = supabase.table("signals").insert(signal).execute()
        
        return jsonify({"success": True, "signal": result.data[0] if result.data else None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================
# RSS HEALTH CHECK API
# ============================================

@app.route("/api/health-check/rss", methods=["POST"])
def api_rss_health_check():
    """
    Run RSS health check and update GSheet colors.
    Red = error, Green = OK
    """
    try:
        from rss_health_check import run_health_check
        
        data = request.get_json() or {}
        only_mvp = data.get("only_mvp", True)
        update_sheet = data.get("update_sheet", True)
        
        results = run_health_check(only_mvp=only_mvp, update_sheet=update_sheet)
        
        return jsonify({
            "success": True,
            "ok_count": len(results.get("ok", [])),
            "error_count": len(results.get("error", [])),
            "skipped_count": len(results.get("skipped", [])),
            "errors": results.get("error", [])[:20]  # Limit to 20 for response size
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/health-check/rss/status", methods=["GET"])
def api_rss_health_status():
    """Get last health check status (if stored)."""
    # For now, just return that it needs to be run
    return jsonify({
        "success": True,
        "message": "Use POST /api/health-check/rss to run a health check",
        "last_run": None
    })


def run_server(port: int = 8080):
    """Run the Flask server."""
    log.info("Starting HTTP server", port=port)
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    run_server(port)
