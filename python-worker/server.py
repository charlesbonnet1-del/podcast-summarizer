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
        pending = supabase.table("content_queue") \
            .select("*") \
            .eq("user_id", user_id) \
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
# V16: ADMIN DASHBOARD ENDPOINTS
# ============================================

@app.route("/admin/queue", methods=["GET"])
def admin_queue():
    """
    Get all items in content_queue for admin dashboard.
    Returns full list with source names, titles, topics.
    """
    try:
        result = supabase.table("content_queue") \
            .select("id, url, title, source_name, keyword, created_at, source_type") \
            .eq("status", "pending") \
            .order("created_at", desc=True) \
            .limit(500) \
            .execute()
        
        return jsonify({
            "items": result.data or [],
            "count": len(result.data) if result.data else 0
        })
    except Exception as e:
        log.error("Admin queue error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/admin/topics", methods=["GET"])
def admin_topics():
    """
    Get all topics with their editorial intentions and article counts.
    """
    try:
        from stitcher_v2 import TOPIC_INTENTIONS, VALID_TOPICS
        
        # Get article counts by topic from queue
        queue_result = supabase.table("content_queue") \
            .select("keyword") \
            .eq("status", "pending") \
            .execute()
        
        # Count by topic
        topic_counts = {}
        for item in (queue_result.data or []):
            topic = item.get("keyword", "unknown")
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        # Try to get DB overrides for editorial intentions
        db_intentions = {}
        try:
            topics_result = supabase.table("topics") \
                .select("slug, name, editorial_intention") \
                .execute()
            for t in (topics_result.data or []):
                db_intentions[t["slug"]] = t.get("editorial_intention", "")
        except:
            pass
        
        # Build topics list
        topics = []
        for slug in VALID_TOPICS:
            # DB intention takes precedence, then hardcoded
            intention = db_intentions.get(slug) or TOPIC_INTENTIONS.get(slug, "")
            topics.append({
                "slug": slug,
                "name": slug.replace("_", " ").title(),
                "editorial_intention": intention,
                "article_count": topic_counts.get(slug, 0)
            })
        
        # Sort by article count
        topics.sort(key=lambda t: t["article_count"], reverse=True)
        
        return jsonify({"topics": topics})
    except Exception as e:
        log.error("Admin topics error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/admin/prompts/<prompt_name>", methods=["GET"])
def admin_get_prompt(prompt_name: str):
    """
    Get a specific prompt from DB or default.
    """
    try:
        from stitcher_v2 import DIALOGUE_SEGMENT_PROMPT, DIALOGUE_CLUSTER_PROMPT, get_prompt_from_db
        
        # Map prompt names to defaults
        defaults = {
            "dialogue_segment": DIALOGUE_SEGMENT_PROMPT,
            "dialogue_cluster": DIALOGUE_CLUSTER_PROMPT,
        }
        
        default = defaults.get(prompt_name, "")
        content = get_prompt_from_db(prompt_name, default)
        
        return jsonify({
            "name": prompt_name,
            "content": content,
            "is_default": content == default
        })
    except Exception as e:
        log.error("Admin get prompt error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/admin/prompts", methods=["POST"])
def admin_update_prompt():
    """
    Update a prompt in the database.
    Body: { "name": "prompt_name", "content": "new content" }
    """
    try:
        data = request.get_json() or {}
        name = data.get("name")
        content = data.get("content")
        
        if not name or not content:
            return jsonify({"error": "name and content required"}), 400
        
        # Check if it's a topic intention update
        if name.startswith("topic_"):
            topic_slug = name[6:]  # Remove "topic_" prefix
            
            # Try to update existing topic
            result = supabase.table("topics") \
                .update({"editorial_intention": content}) \
                .eq("slug", topic_slug) \
                .execute()
            
            # If no rows updated, insert new
            if not result.data:
                supabase.table("topics").insert({
                    "slug": topic_slug,
                    "name": topic_slug.replace("_", " ").title(),
                    "editorial_intention": content
                }).execute()
            
            return jsonify({"success": True, "updated": f"topic:{topic_slug}"})
        
        # Otherwise update prompts table
        result = supabase.table("prompts") \
            .update({"content": content}) \
            .eq("name", name) \
            .execute()
        
        # If no rows updated, insert new
        if not result.data:
            supabase.table("prompts").insert({
                "name": name,
                "content": content
            }).execute()
        
        return jsonify({"success": True, "updated": name})
    except Exception as e:
        log.error("Admin update prompt error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/admin/generate-preview", methods=["POST"])
def admin_generate_preview():
    """
    Generate a preview segment for testing prompts.
    Body: {
        "topic": "ia",
        "article_ids": ["uuid1", "uuid2"],
        "custom_prompt": "optional override"
    }
    Returns: { "script": "...", "audio_url": "...", "duration": 60 }
    """
    try:
        data = request.get_json() or {}
        topic = data.get("topic")
        article_ids = data.get("article_ids", [])
        custom_prompt = data.get("custom_prompt")
        
        if not topic or not article_ids:
            return jsonify({"error": "topic and article_ids required"}), 400
        
        from stitcher_v2 import (
            generate_dialogue_segment_script, 
            generate_dialogue_audio,
            FORMAT_CONFIG,
            get_topic_intention
        )
        from extractor import extract_content
        import tempfile
        import os as os_module
        
        # Get articles from queue
        result = supabase.table("content_queue") \
            .select("*") \
            .in_("id", article_ids) \
            .execute()
        
        if not result.data:
            return jsonify({"error": "No articles found"}), 404
        
        articles = result.data
        
        # Get config for flash format
        config = FORMAT_CONFIG["flash"]
        
        # Build combined content
        combined_content = ""
        combined_title = ""
        source_names = []
        
        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "Sans titre")
            source_name = article.get("source_name", "Unknown")
            
            if not combined_title:
                combined_title = title
            
            source_names.append(source_name)
            
            # Extract content
            extraction = extract_content(url)
            if extraction:
                _, _, content = extraction
                combined_content += f"\n\n--- SOURCE: {source_name} ---\n{title}\n{content[:2000]}"
        
        if not combined_content:
            return jsonify({"error": "Could not extract content from articles"}), 400
        
        # Get topic intention
        topic_intention = get_topic_intention(topic)
        
        # Generate script
        script, citations = generate_dialogue_segment_script(
            title=combined_title,
            content=combined_content,
            source_name=", ".join(source_names),
            word_count=config["words_per_article"],
            style=config["style"],
            use_enrichment=False,  # No Perplexity for preview
            topic_slug=topic
        )
        
        if not script:
            return jsonify({"error": "Script generation failed"}), 500
        
        # Generate audio (optional, for full preview)
        audio_url = None
        duration = 0
        
        try:
            temp_path = os_module.path.join(tempfile.gettempdir(), f"preview_{topic}.mp3")
            audio_path = generate_dialogue_audio(script, temp_path)
            
            if audio_path:
                # Upload to Supabase for preview
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                remote_path = f"previews/{topic}_{timestamp}.mp3"
                
                with open(audio_path, 'rb') as f:
                    audio_data = f.read()
                
                supabase.storage.from_("audio").upload(
                    remote_path, audio_data,
                    {"content-type": "audio/mpeg", "upsert": "true"}
                )
                
                audio_url = supabase.storage.from_("audio").get_public_url(remote_path)
                
                # Get duration
                from pydub import AudioSegment
                audio = AudioSegment.from_mp3(audio_path)
                duration = len(audio) // 1000
                
                # Cleanup
                os_module.remove(audio_path)
        except Exception as e:
            log.warning(f"Audio preview generation failed: {e}")
        
        return jsonify({
            "script": script,
            "audio_url": audio_url,
            "duration": duration,
            "topic_intention": topic_intention,
            "sources": source_names
        })
        
    except Exception as e:
        log.error("Admin generate preview error", error=str(e))
        return jsonify({"error": str(e)}), 500


def run_server(port: int = 8080):
    """Run the Flask server."""
    log.info("Starting HTTP server", port=port)
    app.run(host="0.0.0.0", port=port, threaded=True)


# ============================================
# V16: PROMPT LAB - Text-only generation
# ============================================

@app.route("/prompt-lab/queue", methods=["GET"])
def prompt_lab_queue():
    """
    Get all articles in queue grouped by topic.
    Returns articles with title, source, url, published_at.
    """
    try:
        user_id = request.args.get("user_id")
        
        # Get all pending articles
        query = supabase.table("content_queue") \
            .select("id, title, url, source_name, keyword, published_at, source") \
            .eq("status", "pending")
        
        if user_id:
            query = query.eq("user_id", user_id)
        
        result = query.order("keyword").order("published_at", desc=True).execute()
        
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
                "published_at": article.get("published_at"),
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
    Body: {
        "prompt_name": "dialogue_segment",  # or "dialogue_multi_source"
        "prompt_content": "...",
        "topic_slug": "ia",  # optional
        "topic_intention": "..."  # optional
    }
    """
    try:
        data = request.get_json() or {}
        
        # Save main prompt if provided
        prompt_name = data.get("prompt_name")
        prompt_content = data.get("prompt_content")
        
        if prompt_name and prompt_content:
            # Upsert to prompts table
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
                # Try update first
                result = supabase.table("topics") \
                    .update({"editorial_intention": topic_intention}) \
                    .eq("keyword", topic_slug) \
                    .execute()
                
                # If no rows updated, insert
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
    
    Body: {
        "article_ids": ["uuid1", "uuid2"],
        "topic": "ia",
        "custom_prompt": "optional override for main prompt",
        "custom_intention": "optional override for topic intention",
        "use_enrichment": true  # Use Perplexity
    }
    
    Returns: {
        "script": "dialogue text",
        "enriched_context": "perplexity context if used",
        "perplexity_citations": [...],
        "word_count": 250,
        "generation_time_ms": 1234
    }
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
        
        if not article_ids:
            return jsonify({"error": "article_ids required"}), 400
        
        # Get articles from queue
        result = supabase.table("content_queue") \
            .select("*") \
            .in_("id", article_ids) \
            .execute()
        
        if not result.data:
            return jsonify({"error": "No articles found"}), 404
        
        articles = result.data
        
        from extractor import extract_content
        from stitcher_v2 import (
            enrich_content_with_perplexity,
            get_topic_intention,
            FORMAT_CONFIG,
            DIALOGUE_SEGMENT_PROMPT,
            DIALOGUE_MULTI_SOURCE_PROMPT,
            get_prompt_from_db
        )
        import os as os_module
        from openai import OpenAI
        from groq import Groq
        
        # Get Groq client
        groq_api_key = os_module.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return jsonify({"error": "GROQ_API_KEY not configured"}), 500
        
        groq_client = Groq(api_key=groq_api_key)
        
        # Extract content from all articles
        combined_content = ""
        combined_title = ""
        source_names = []
        
        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "Sans titre")
            source_name = article.get("source_name", article.get("source", "Unknown"))
            
            if not combined_title:
                combined_title = title
            
            source_names.append(source_name)
            
            # Extract content
            extraction = extract_content(url)
            if extraction:
                _, extracted_title, content = extraction
                if not combined_title and extracted_title:
                    combined_title = extracted_title
                combined_content += f"\n\n--- SOURCE: {source_name} ---\n{title}\n{content[:2000]}"
        
        if not combined_content:
            return jsonify({"error": "Could not extract content from articles"}), 400
        
        # Get topic intention
        if custom_intention:
            topic_intention = f"\n{custom_intention}\n"
        else:
            topic_intention = get_topic_intention(topic)
        
        # Perplexity enrichment
        enriched_context = None
        perplexity_citations = []
        
        if use_enrichment:
            enriched_context, perplexity_citations = enrich_content_with_perplexity(
                combined_title, 
                combined_content[:2000], 
                source_names[0] if source_names else "Unknown"
            )
        
        # Build full content for LLM
        if enriched_context:
            full_content = f"""ARTICLE PRINCIPAL:
{combined_content[:3000]}

CONTEXTE ENRICHI (sources additionnelles):
{enriched_context}"""
        else:
            full_content = combined_content[:4000]
        
        # Get prompt template
        config = FORMAT_CONFIG["flash"]
        
        if len(articles) > 1:
            # Multi-source prompt
            if custom_prompt:
                prompt_template = custom_prompt
            else:
                prompt_template = get_prompt_from_db("dialogue_multi_source", DIALOGUE_MULTI_SOURCE_PROMPT)
            
            prompt = prompt_template.format(
                word_count=config["words_per_article"],
                topic_intention=topic_intention,
                source_count=len(articles),
                sources_content=full_content,
                style=config["style"]
            )
        else:
            # Single source prompt
            if custom_prompt:
                prompt_template = custom_prompt
            else:
                prompt_template = get_prompt_from_db("dialogue_segment", DIALOGUE_SEGMENT_PROMPT)
            
            prompt = prompt_template.format(
                word_count=config["words_per_article"],
                topic_intention=topic_intention,
                title=combined_title,
                source_label=f"Source: {source_names[0]}" if source_names else "Source inconnue",
                content=full_content,
                attribution_instruction=f'"Selon {source_names[0]}..."' if source_names else '"Selon les sources..."',
                previous_segment_rule="",
                previous_segment_context="",
                style=config["style"]
            )
        
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
        
        # Calculate stats
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    run_server(port)
