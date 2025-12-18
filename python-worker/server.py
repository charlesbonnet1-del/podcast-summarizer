"""
HTTP Server for triggering podcast generation from the Dashboard.
"""
import os
import threading
from flask import Flask, request, jsonify
import structlog
from dotenv import load_dotenv

from worker import process_user_queue
from db import supabase

load_dotenv()
log = structlog.get_logger()

app = Flask(__name__)

# Simple auth token (set in environment)
WORKER_SECRET = os.getenv("WORKER_SECRET", "")


def verify_auth():
    """Verify the request is authorized."""
    if not WORKER_SECRET:
        return True  # No auth configured
    
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return token == WORKER_SECRET
    return False


@app.route("/", methods=["GET"])
def root():
    """Root endpoint."""
    return jsonify({"service": "singular-daily-worker", "status": "running"})


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "singular-daily-worker"})


@app.route("/generate", methods=["POST"])
def generate():
    """Trigger podcast generation for a user."""
    if not verify_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    log.info("Generation request received", user_id=user_id)
    
    # Run generation in background thread
    def run_generation():
        try:
            episode = process_user_queue(user_id)
            if episode:
                log.info("Episode generated via HTTP", episode_id=episode["id"])
            else:
                log.warning("Generation failed via HTTP", user_id=user_id)
        except Exception as e:
            log.error("Generation error", user_id=user_id, error=str(e))
    
    thread = threading.Thread(target=run_generation)
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Generation started",
        "user_id": user_id
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


def run_server(port: int = 8080):
    """Run the Flask server."""
    log.info("Starting HTTP server", port=port)
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    run_server(port)
