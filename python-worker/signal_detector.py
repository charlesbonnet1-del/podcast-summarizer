"""
KEERNEL Signal Detector
Detects velocity spikes and generates signals from article clusters.
"""

import os
import time
import json
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
import httpx
import numpy as np
from supabase import create_client, Client

# ============================================
# SUPABASE CLIENT
# ============================================

def get_supabase() -> Client:
    """Get Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


# ============================================
# EMBEDDING
# ============================================

def create_embedding_text(article: dict) -> str:
    """Build text to embed from article."""
    parts = []
    
    # Title (important)
    if article.get("title"):
        parts.append(article["title"])
    
    # Description
    if article.get("description"):
        parts.append(article["description"])
    
    # Full content if available (truncate to 6000 chars)
    if article.get("content"):
        content = article["content"][:6000]
        parts.append(content)
    
    # Source context
    if article.get("source_name"):
        parts.append(f"Source: {article['source_name']}")
    
    return "\n\n".join(parts)


def get_embedding(text: str) -> Optional[list[float]]:
    """Get embedding from OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    
    try:
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "text-embedding-3-small",
                "input": text[:8000]  # Token limit safety
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"Embedding error: {e}")
        return None


# ============================================
# CLUSTERING
# ============================================

def cosine_distance(a: list[float], b: list[float]) -> float:
    """Calculate cosine distance between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def find_or_create_cluster(
    supabase: Client,
    article: dict,
    embedding: list[float],
    threshold: float = 0.35
) -> str:
    """Find existing cluster or create new one."""
    
    topic = article.get("topic") or article.get("classified_topic")
    
    # Get recent clusters for this topic
    result = supabase.table("clusters").select("id, centroid, name").eq(
        "topic", topic
    ).gte(
        "last_article_at", (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    ).execute()
    
    clusters = result.data or []
    
    # Find nearest cluster
    best_cluster = None
    best_distance = float('inf')
    
    for cluster in clusters:
        if cluster.get("centroid"):
            # Centroid is stored as string, parse it
            centroid = cluster["centroid"]
            if isinstance(centroid, str):
                centroid = json.loads(centroid.replace("(", "[").replace(")", "]"))
            
            dist = cosine_distance(embedding, centroid)
            if dist < best_distance:
                best_distance = dist
                best_cluster = cluster
    
    # If close enough, return existing cluster
    if best_cluster and best_distance < threshold:
        return best_cluster["id"]
    
    # Create new cluster
    cluster_name = generate_cluster_name([article])
    
    new_cluster = supabase.table("clusters").insert({
        "topic": topic,
        "name": cluster_name,
        "centroid": embedding,
        "article_count": 1,
        "source_names": [article.get("source_name", "")],
        "first_seen_at": datetime.now(timezone.utc).isoformat(),
        "last_article_at": datetime.now(timezone.utc).isoformat()
    }).execute()
    
    return new_cluster.data[0]["id"]


def generate_cluster_name(articles: list[dict]) -> str:
    """Generate a descriptive name for a cluster."""
    titles = [a.get("title", "") for a in articles[:3]]
    words = []
    for t in titles:
        words.extend(t.lower().split())
    
    # Filter stopwords
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "for", 
        "on", "with", "at", "by", "from", "as", "et", "le", "la", "les", "de", 
        "du", "des", "un", "une", "en", "est", "sont", "pour", "sur", "dans",
        "par", "au", "aux", "ce", "cette", "ces", "qui", "que", "dont", "où",
        "how", "why", "what", "when", "new", "will", "can", "could", "would"
    }
    meaningful = [w for w in words if len(w) > 3 and w not in stopwords]
    
    # Count frequencies
    from collections import Counter
    freq = Counter(meaningful)
    top_words = [w for w, _ in freq.most_common(4)]
    
    if top_words:
        return " ".join(top_words).title()
    elif titles:
        return " ".join(titles[0].split()[:5])
    else:
        return "New Cluster"


def update_cluster_stats(supabase: Client, cluster_id: str, article: dict, embedding: list[float]):
    """Update cluster statistics after adding an article."""
    
    # Get current cluster
    result = supabase.table("clusters").select("*").eq("id", cluster_id).single().execute()
    cluster = result.data
    
    if not cluster:
        return
    
    # Update counts
    tier = article.get("source_tier", "generalist")
    updates = {
        "article_count": cluster["article_count"] + 1,
        "last_article_at": datetime.now(timezone.utc).isoformat(),
    }
    
    if tier == "authority":
        updates["authority_count"] = cluster.get("authority_count", 0) + 1
    elif tier == "generalist":
        updates["generalist_count"] = cluster.get("generalist_count", 0) + 1
    elif tier == "corporate":
        updates["corporate_count"] = cluster.get("corporate_count", 0) + 1
    
    # Update source names
    source_names = cluster.get("source_names", []) or []
    if article.get("source_name") and article["source_name"] not in source_names:
        source_names.append(article["source_name"])
        updates["source_names"] = source_names
    
    # Update centroid (running average)
    old_centroid = cluster.get("centroid")
    if old_centroid:
        if isinstance(old_centroid, str):
            old_centroid = json.loads(old_centroid.replace("(", "[").replace(")", "]"))
        n = cluster["article_count"]
        new_centroid = [
            (old_centroid[i] * n + embedding[i]) / (n + 1)
            for i in range(len(embedding))
        ]
        updates["centroid"] = new_centroid
    
    # Update history
    history = cluster.get("article_count_history", {}) or {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history[today] = history.get(today, 0) + 1
    updates["article_count_history"] = history
    
    supabase.table("clusters").update(updates).eq("id", cluster_id).execute()


# ============================================
# VELOCITY CALCULATION
# ============================================

def calculate_velocity(supabase: Client, cluster_id: str, window_hours: int = 24) -> dict:
    """Calculate velocity for a specific cluster."""
    
    # Get cluster
    result = supabase.table("clusters").select("*").eq("id", cluster_id).single().execute()
    cluster = result.data
    
    if not cluster:
        return {"velocity": 0, "baseline": 0, "current": 0}
    
    history = cluster.get("article_count_history", {}) or {}
    
    # Current count (today)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current = history.get(today, 0)
    
    # Baseline: average of last 7 days (excluding today)
    baseline_days = []
    for i in range(1, 8):
        day = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        if day in history:
            baseline_days.append(history[day])
    
    if baseline_days:
        baseline = sum(baseline_days) / len(baseline_days)
    else:
        # New cluster, use 0.5 as baseline (anything > 0 is notable)
        baseline = 0.5
    
    # Avoid division by zero
    baseline = max(baseline, 0.1)
    
    velocity = current / baseline
    
    return {
        "velocity": round(velocity, 2),
        "baseline": round(baseline, 2),
        "current": current,
        "window_hours": window_hours,
        "history_days": len(baseline_days)
    }


def calculate_topic_velocity(supabase: Client, topic: str, window_hours: int = 24) -> dict:
    """Calculate overall velocity for a topic."""
    
    # Get velocity stats
    result = supabase.table("article_velocity").select("*").eq(
        "topic", topic
    ).order("date", desc=True).limit(8).execute()
    
    stats = result.data or []
    
    if not stats:
        return {"velocity": 0, "baseline": 0, "current": 0}
    
    # Today's count
    today_stat = next((s for s in stats if s["date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")), None)
    current = today_stat["article_count"] if today_stat else 0
    
    # Baseline from previous days
    baseline_counts = [s["article_count"] for s in stats[1:] if s["article_count"] > 0]
    baseline = sum(baseline_counts) / len(baseline_counts) if baseline_counts else 1
    baseline = max(baseline, 0.1)
    
    velocity = current / baseline
    
    return {
        "velocity": round(velocity, 2),
        "baseline": round(baseline, 2),
        "current": current
    }


# ============================================
# SIGNAL SCORING
# ============================================

def score_signal(cluster: dict, velocity_data: dict, thresholds: dict) -> dict:
    """Calculate signal score for a cluster."""
    
    score_breakdown = {}
    total = 0
    
    # 1. Velocity score (30% weight, max 30 points)
    velocity = velocity_data.get("velocity", 0)
    velocity_points = min(30, velocity * 6)  # 5x velocity = 30 points
    score_breakdown["velocity"] = round(velocity_points, 1)
    total += velocity_points
    
    # 2. Source quality (25% weight, max 25 points)
    authority = cluster.get("authority_count", 0)
    generalist = cluster.get("generalist_count", 0)
    
    # Authority sources are gold
    authority_points = min(15, authority * 10)
    generalist_points = min(10, generalist * 2)
    
    source_quality = authority_points + generalist_points
    score_breakdown["source_quality"] = round(source_quality, 1)
    total += source_quality
    
    # 3. Source diversity (15% weight, max 15 points)
    source_names = cluster.get("source_names", []) or []
    diversity_points = min(15, len(source_names) * 3)
    score_breakdown["source_diversity"] = round(diversity_points, 1)
    total += diversity_points
    
    # 4. Novelty (20% weight, max 20 points)
    # New clusters get bonus
    first_seen = cluster.get("first_seen_at")
    if first_seen:
        if isinstance(first_seen, str):
            first_seen = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - first_seen).total_seconds() / 3600
        
        if age_hours < 6:
            novelty_points = 20  # Brand new cluster
        elif age_hours < 24:
            novelty_points = 15
        elif age_hours < 48:
            novelty_points = 10
        else:
            novelty_points = 5
    else:
        novelty_points = 10
    
    score_breakdown["novelty"] = novelty_points
    total += novelty_points
    
    # 5. Volume bonus (10% weight, max 10 points)
    article_count = cluster.get("article_count", 0)
    volume_points = min(10, article_count * 2)
    score_breakdown["volume"] = volume_points
    total += volume_points
    
    # Normalize to 0-100
    total = min(100, total)
    
    # Determine severity
    if total >= 85:
        severity = "breaking"
    elif total >= 70:
        severity = "alert"
    elif total >= thresholds.get("min_score", 60):
        severity = "digest"
    else:
        severity = "log"
    
    # Validation check
    is_valid = False
    reason = ""
    
    min_authority = thresholds.get("min_authority_sources", 1)
    min_velocity = thresholds.get("min_velocity", 5.0)
    min_total = thresholds.get("min_total_sources", 3)
    
    if authority >= min_authority and velocity >= min_velocity * 0.6:
        is_valid = True
        reason = f"Authority signal: {authority} authority source(s), {velocity:.1f}x velocity"
    elif len(source_names) >= min_total and velocity >= min_velocity:
        is_valid = True
        reason = f"Volume signal: {len(source_names)} sources, {velocity:.1f}x velocity"
    else:
        reason = f"Below threshold: {authority} auth, {len(source_names)} sources, {velocity:.1f}x velocity"
    
    return {
        "total_score": round(total),
        "score_breakdown": score_breakdown,
        "severity": severity,
        "is_valid": is_valid,
        "reason": reason,
        "source_mix": {
            "authority": authority,
            "generalist": generalist,
            "corporate": cluster.get("corporate_count", 0)
        }
    }


# ============================================
# SIGNAL DETECTION
# ============================================

def detect_signals(supabase: Client, topic: str = None) -> list[dict]:
    """Detect signals from recent clusters."""
    
    topics = [topic] if topic else ["ia", "macro", "asia"]
    detected_signals = []
    
    for t in topics:
        # Get thresholds for this topic
        threshold_result = supabase.table("signal_thresholds").select("*").eq("topic", t).single().execute()
        thresholds = threshold_result.data or {
            "min_velocity": 5.0,
            "min_score": 60,
            "min_authority_sources": 1,
            "min_total_sources": 3
        }
        
        # Get active clusters (articles in last 24h)
        clusters_result = supabase.table("clusters").select("*").eq(
            "topic", t
        ).gte(
            "last_article_at", (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        ).execute()
        
        clusters = clusters_result.data or []
        
        for cluster in clusters:
            # Skip tiny clusters
            if cluster.get("article_count", 0) < 2:
                continue
            
            # Calculate velocity
            velocity_data = calculate_velocity(supabase, cluster["id"])
            
            # Score the cluster
            score_result = score_signal(cluster, velocity_data, thresholds)
            
            # Only create signal if valid and above threshold
            if score_result["is_valid"] and score_result["total_score"] >= thresholds.get("min_score", 60):
                
                # Check if signal already exists for this cluster today
                existing = supabase.table("signals").select("id").eq(
                    "cluster_id", cluster["id"]
                ).gte(
                    "detected_at", datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
                ).execute()
                
                if existing.data:
                    continue  # Already have a signal for this cluster today
                
                # Create signal
                signal = {
                    "topic": t,
                    "title": cluster.get("name", "New Signal"),
                    "slug": generate_slug(cluster.get("name", "")),
                    "cluster_id": cluster["id"],
                    "velocity_score": velocity_data["velocity"],
                    "velocity_details": velocity_data,
                    "source_quality_score": score_result["score_breakdown"].get("source_quality", 0),
                    "source_mix": score_result["source_mix"],
                    "novelty_score": score_result["score_breakdown"].get("novelty", 0),
                    "total_score": score_result["total_score"],
                    "score_breakdown": score_result["score_breakdown"],
                    "status": "detected",
                    "severity": score_result["severity"],
                    "detected_at": datetime.now(timezone.utc).isoformat()
                }
                
                result = supabase.table("signals").insert(signal).execute()
                
                if result.data:
                    detected_signals.append({
                        **result.data[0],
                        "cluster": cluster,
                        "reason": score_result["reason"]
                    })
    
    return detected_signals


def generate_slug(title: str) -> str:
    """Generate URL-safe slug from title."""
    import re
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    slug = slug.strip('-')[:50]
    
    # Add timestamp hash for uniqueness
    hash_suffix = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:6]
    return f"{slug}-{hash_suffix}"


# ============================================
# ENRICHMENT
# ============================================

def enrich_signal(supabase: Client, signal_id: str) -> dict:
    """Enrich signal with Perplexity analysis."""
    
    # Get signal with cluster
    signal_result = supabase.table("signals").select("*, clusters(*)").eq("id", signal_id).single().execute()
    signal = signal_result.data
    
    if not signal:
        return {"error": "Signal not found"}
    
    cluster = signal.get("clusters")
    if not cluster:
        return {"error": "Cluster not found"}
    
    # Get articles for this cluster
    articles_result = supabase.table("articles").select(
        "title, source_name, url"
    ).eq("cluster_id", cluster["id"]).limit(5).execute()
    
    articles = articles_result.data or []
    
    # Build Perplexity query
    articles_text = "\n".join([
        f"- {a['title']} ({a['source_name']})"
        for a in articles
    ])
    
    query = f"""Analyse ces articles d'actualité sur le thème "{signal['topic']}":

{articles_text}

Réponds en JSON avec cette structure:
{{
  "hook": "Une phrase d'accroche percutante (max 20 mots)",
  "thesis": "Le fait principal / la thèse centrale (2-3 phrases)",
  "antithesis": "Les nuances, contre-arguments ou perspectives alternatives (2-3 phrases)",
  "key_data": "Les chiffres clés, dates, noms importants (liste)",
  "analysis": "Contexte et implications (2-3 phrases)"
}}

Sois factuel et précis."""

    # Call Perplexity
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return {"error": "PERPLEXITY_API_KEY not set"}
    
    try:
        response = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 800,
                "temperature": 0.3
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # Parse JSON response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            enrichment = json.loads(json_match.group())
        else:
            enrichment = {"analysis": content}
        
        # Update signal
        update_data = {
            "hook": enrichment.get("hook", ""),
            "thesis": enrichment.get("thesis", ""),
            "antithesis": enrichment.get("antithesis", ""),
            "key_data": enrichment.get("key_data", ""),
            "analysis": enrichment.get("analysis", ""),
            "summary": f"{enrichment.get('hook', '')}\n\n{enrichment.get('thesis', '')}"
        }
        
        supabase.table("signals").update(update_data).eq("id", signal_id).execute()
        
        return {"success": True, "enrichment": enrichment}
        
    except Exception as e:
        return {"error": str(e)}


# ============================================
# FEEDBACK & LEARNING
# ============================================

def record_feedback(supabase: Client, signal_id: str, rating: str, comment: str = None) -> dict:
    """Record user feedback on a signal."""
    
    # Get signal
    signal_result = supabase.table("signals").select("detected_at").eq("id", signal_id).single().execute()
    signal = signal_result.data
    
    if not signal:
        return {"error": "Signal not found"}
    
    # Calculate hours since signal
    detected_at = datetime.fromisoformat(signal["detected_at"].replace("Z", "+00:00"))
    hours_after = (datetime.now(timezone.utc) - detected_at).total_seconds() / 3600
    
    # Insert feedback
    feedback = {
        "signal_id": signal_id,
        "rating": rating,
        "comment": comment,
        "hours_after_signal": round(hours_after, 2)
    }
    
    result = supabase.table("signal_feedback").insert(feedback).execute()
    
    return {"success": True, "feedback_id": result.data[0]["id"]}


def recalibrate_thresholds(supabase: Client, topic: str) -> dict:
    """Recalibrate thresholds based on feedback."""
    
    # Get feedback for this topic (last 30 days)
    feedback_result = supabase.rpc(
        "get_topic_feedback",
        {"p_topic": topic, "p_days": 30}
    ).execute()
    
    # Alternative: manual query if RPC doesn't exist
    signals_result = supabase.table("signals").select(
        "id, velocity_score, total_score, source_mix"
    ).eq("topic", topic).gte(
        "detected_at", (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    ).execute()
    
    signals = {s["id"]: s for s in (signals_result.data or [])}
    
    feedback_result = supabase.table("signal_feedback").select("*").in_(
        "signal_id", list(signals.keys())
    ).execute()
    
    feedbacks = feedback_result.data or []
    
    if len(feedbacks) < 10:
        return {"message": "Not enough feedback data", "count": len(feedbacks)}
    
    # Analyze patterns
    useful = []
    not_useful = []
    
    for f in feedbacks:
        signal = signals.get(f["signal_id"])
        if not signal:
            continue
        
        data = {
            "velocity": signal.get("velocity_score", 0),
            "score": signal.get("total_score", 0),
            "authority": signal.get("source_mix", {}).get("authority", 0)
        }
        
        if f["rating"] == "useful" or f["rating"] == "acted_on":
            useful.append(data)
        elif f["rating"] == "not_useful":
            not_useful.append(data)
    
    if not useful:
        return {"message": "No useful signals to learn from"}
    
    # Calculate optimal thresholds
    avg_useful_velocity = sum(d["velocity"] for d in useful) / len(useful)
    avg_useful_score = sum(d["score"] for d in useful) / len(useful)
    
    avg_not_useful_velocity = sum(d["velocity"] for d in not_useful) / len(not_useful) if not_useful else 0
    
    # New thresholds: midpoint between useful and not_useful
    if not_useful:
        recommended_velocity = (avg_useful_velocity + avg_not_useful_velocity) / 2
    else:
        recommended_velocity = avg_useful_velocity * 0.8  # 20% below average useful
    
    recommended_score = int(avg_useful_score * 0.9)  # 10% below average useful
    
    # Confidence based on sample size
    confidence = min(1.0, len(feedbacks) / 50)
    
    # Calculate precision
    precision = len(useful) / len(feedbacks) if feedbacks else 0
    
    # Update thresholds
    supabase.table("signal_thresholds").update({
        "recommended_velocity": round(recommended_velocity, 2),
        "recommended_score": recommended_score,
        "recommendation_confidence": round(confidence, 2),
        "precision_30d": round(precision, 2),
        "signals_sent_30d": len(feedbacks),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).eq("topic", topic).execute()
    
    return {
        "topic": topic,
        "feedback_count": len(feedbacks),
        "precision": round(precision * 100, 1),
        "recommended_velocity": round(recommended_velocity, 2),
        "recommended_score": recommended_score,
        "confidence": round(confidence * 100, 1)
    }


def apply_recommendations(supabase: Client, topic: str) -> dict:
    """Apply recommended thresholds."""
    
    result = supabase.table("signal_thresholds").select("*").eq("topic", topic).single().execute()
    thresholds = result.data
    
    if not thresholds:
        return {"error": "Topic not found"}
    
    if not thresholds.get("recommended_velocity"):
        return {"error": "No recommendations available"}
    
    if thresholds.get("recommendation_confidence", 0) < 0.5:
        return {"error": "Confidence too low", "confidence": thresholds.get("recommendation_confidence")}
    
    # Apply recommendations
    supabase.table("signal_thresholds").update({
        "min_velocity": thresholds["recommended_velocity"],
        "min_score": thresholds["recommended_score"],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).eq("topic", topic).execute()
    
    return {
        "success": True,
        "new_velocity": thresholds["recommended_velocity"],
        "new_score": thresholds["recommended_score"]
    }


# ============================================
# MAIN DETECTION LOOP
# ============================================

def run_detection_cycle(topic: str = None) -> dict:
    """Run a full detection cycle."""
    
    start_time = time.time()
    supabase = get_supabase()
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals_detected": [],
        "errors": []
    }
    
    try:
        # 1. Update velocity stats
        supabase.rpc("update_velocity_stats").execute()
    except Exception as e:
        results["errors"].append(f"Velocity stats update failed: {e}")
    
    try:
        # 2. Detect signals
        signals = detect_signals(supabase, topic)
        results["signals_detected"] = signals
        
        # 3. Enrich high-score signals
        for signal in signals:
            if signal.get("total_score", 0) >= 70:
                try:
                    enrich_signal(supabase, signal["id"])
                except Exception as e:
                    results["errors"].append(f"Enrichment failed for {signal['id']}: {e}")
        
    except Exception as e:
        results["errors"].append(f"Detection failed: {e}")
    
    results["duration_ms"] = int((time.time() - start_time) * 1000)
    
    return results


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "detect":
            topic = sys.argv[2] if len(sys.argv) > 2 else None
            results = run_detection_cycle(topic)
            print(json.dumps(results, indent=2, default=str))
        
        elif command == "recalibrate":
            topic = sys.argv[2] if len(sys.argv) > 2 else "ia"
            supabase = get_supabase()
            results = recalibrate_thresholds(supabase, topic)
            print(json.dumps(results, indent=2))
        
        else:
            print(f"Unknown command: {command}")
            print("Usage: python signal_detector.py [detect|recalibrate] [topic]")
    else:
        print("Running detection cycle...")
        results = run_detection_cycle()
        print(json.dumps(results, indent=2, default=str))
