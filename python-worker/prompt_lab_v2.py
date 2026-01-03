"""
Keernel Prompt Lab V2

Full control over each pipeline step:
1. FETCH - Get articles from sources
2. CLASSIFY - LLM classification by topic
3. EMBED - Generate embeddings
4. CLUSTER - DBSCAN clustering
5. SCORE - Radar + Loupe scoring
6. ENRICH - Perplexity context
7. SUMMARIZE - Structured cluster summary
8. SCRIPT - Podcast script generation
9. STORE - Save to database

Each step can be run independently with full visibility.
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, asdict

import httpx
import numpy as np
import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

MVP_TOPICS = ["ia", "macro", "asia"]

GROQ_MODELS = [
    {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "context": 128000},
    {"id": "llama-3.1-70b-versatile", "name": "Llama 3.1 70B", "context": 128000},
    {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B (Fast)", "context": 128000},
    {"id": "llama3-70b-8192", "name": "Llama 3 70B", "context": 8192},
    {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "context": 32768},
]

# Default parameters
DEFAULT_PARAMS = {
    "max_articles_per_source": 10,
    "dbscan_eps": 0.65,
    "dbscan_min_samples": 2,
    "min_authority_sources": 1,
    "min_generalist_sources": 5,
    "max_corporate_per_cluster": 1,
    "tier_multipliers": {
        "authority": 2.0,
        "corporate": 1.5,
        "generalist": 1.0
    },
    "cluster_bonus_per_source": 20,
    "mixed_tier_bonus": 50,
}

# Default prompts
DEFAULT_PROMPTS = {
    "classification": """You are a news classifier. Classify this article into ONE of these topics, or "discard" if not relevant.

TOPICS:
- ia: Artificial Intelligence, Machine Learning, LLMs, AI companies, AI research
- macro: Geopolitics, Economics, Finance, Markets, Central banks, Trade
- asia: News specifically about Asia (China, Japan, Korea, India, Southeast Asia)

ARTICLE:
Title: {title}
Description: {description}
Source: {source_name}

Respond with ONLY the topic ID (ia, macro, asia) or "discard". Nothing else.""",

    "summary": """You are a professional intelligence analyst writing a briefing.

TOPIC: {topic}

ARTICLES:
{articles}

ADDITIONAL CONTEXT:
{context}

Write a structured briefing in this EXACT format:

## [Write a compelling headline that captures the main story]

**Key Points:**
• [First key insight - be specific with names, numbers, dates]
• [Second key insight]
• [Third key insight]
• [Fourth key insight if relevant]

**Why It Matters:**
[One paragraph explaining the significance and implications]

**Sources:**
{sources}

Rules:
- Be factual and specific (names, numbers, dates)
- No speculation or opinion
- Professional tone
- Write in the same language as the articles (French if articles are in French)""",

    "script": """You are a podcast host delivering an intelligence briefing.

TOPIC: {topic}
CLUSTER SUMMARY:
{summary}

ADDITIONAL CONTEXT:
{context}

Write a podcast script segment (60-90 seconds when read aloud) that:
1. Opens with a hook that grabs attention
2. Delivers the key insights conversationally
3. Explains why this matters to the listener
4. Transitions smoothly to the next topic

Style:
- Conversational but authoritative
- No filler words or clichés
- Speak directly to the listener ("you")
- Include specific details (names, numbers)

Write ONLY the script, no stage directions or notes."""
}


# ============================================
# GROQ LLM HELPER
# ============================================

def call_groq(
    prompt: str,
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 1000,
    temperature: float = 0.5
) -> dict:
    """Call Groq API and return response with metadata."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"error": "GROQ_API_KEY not set", "content": None}
    
    start_time = time.time()
    
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature
            },
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        
        return {
            "content": content,
            "model": model,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "latency_ms": int((time.time() - start_time) * 1000),
            "error": None
        }
        
    except Exception as e:
        return {
            "content": None,
            "model": model,
            "error": str(e),
            "latency_ms": int((time.time() - start_time) * 1000)
        }


# ============================================
# PERPLEXITY HELPER
# ============================================

def call_perplexity(query: str, max_tokens: int = 500) -> dict:
    """Call Perplexity API for context enrichment."""
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return {"context": "", "citations": [], "error": "PERPLEXITY_API_KEY not set"}
    
    start_time = time.time()
    
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
                "max_tokens": max_tokens,
                "temperature": 0.3
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        citations = data.get("citations", [])
        
        return {
            "context": content,
            "citations": citations,
            "latency_ms": int((time.time() - start_time) * 1000),
            "error": None
        }
        
    except Exception as e:
        return {
            "context": "",
            "citations": [],
            "latency_ms": int((time.time() - start_time) * 1000),
            "error": str(e)
        }


# ============================================
# STEP 1: FETCH
# ============================================

def lab_fetch(
    topics: list[str] = MVP_TOPICS,
    max_per_source: int = 10
) -> dict:
    """Fetch articles from sources."""
    from sourcing_v2 import SourceLibrary, fetch_all_sources
    
    start_time = time.time()
    
    library = SourceLibrary()
    stats = library.get_stats()
    
    articles = fetch_all_sources(
        library,
        topics=topics,
        mvp_only=True,
        max_articles_per_source=max_per_source
    )
    
    # Group by source for display
    by_source = {}
    for a in articles:
        source = a.get("source_name", "Unknown")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append({
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "description": a.get("description", "")[:200] if a.get("description") else "",
            "topic": a.get("topic", ""),
            "tier": a.get("source_tier", ""),
        })
    
    return {
        "step": "fetch",
        "articles": articles,
        "count": len(articles),
        "by_source": by_source,
        "source_count": len(by_source),
        "library_stats": stats,
        "duration_ms": int((time.time() - start_time) * 1000)
    }


# ============================================
# STEP 2: CLASSIFY
# ============================================

def lab_classify(
    articles: list[dict],
    topics: list[str] = MVP_TOPICS,
    model: str = "llama-3.3-70b-versatile",
    prompt_template: str = None
) -> dict:
    """Classify articles by topic using LLM."""
    start_time = time.time()
    prompt_template = prompt_template or DEFAULT_PROMPTS["classification"]
    
    results = []
    classified = []
    discarded = []
    
    for article in articles:
        # Skip if already has topic from authority source
        if article.get("source_tier") == "authority" and article.get("topic") in topics:
            article["classified_topic"] = article["topic"]
            article["classification_source"] = "authority_passthrough"
            classified.append(article)
            results.append({
                "title": article.get("title", "")[:60],
                "source": article.get("source_name", ""),
                "original_topic": article.get("topic"),
                "classified_topic": article["topic"],
                "method": "authority_passthrough",
                "llm_response": None
            })
            continue
        
        # Classify with LLM
        prompt = prompt_template.format(
            title=article.get("title", ""),
            description=article.get("description", "")[:500],
            source_name=article.get("source_name", "")
        )
        
        llm_result = call_groq(prompt, model=model, max_tokens=50, temperature=0.1)
        
        if llm_result["content"]:
            topic = llm_result["content"].strip().lower()
            
            result_entry = {
                "title": article.get("title", "")[:60],
                "source": article.get("source_name", ""),
                "original_topic": article.get("topic"),
                "classified_topic": topic,
                "method": "llm",
                "llm_response": llm_result
            }
            results.append(result_entry)
            
            if topic in topics:
                article["classified_topic"] = topic
                article["classification_source"] = "llm"
                classified.append(article)
            else:
                article["classified_topic"] = "discard"
                discarded.append(article)
        else:
            results.append({
                "title": article.get("title", "")[:60],
                "source": article.get("source_name", ""),
                "error": llm_result.get("error"),
                "classified_topic": "error"
            })
            discarded.append(article)
    
    return {
        "step": "classify",
        "model": model,
        "prompt_template": prompt_template,
        "results": results,
        "classified_articles": classified,
        "discarded_articles": discarded,
        "classified_count": len(classified),
        "discarded_count": len(discarded),
        "duration_ms": int((time.time() - start_time) * 1000)
    }


# ============================================
# STEP 3: EMBED
# ============================================

def lab_embed(articles: list[dict]) -> dict:
    """Generate embeddings for articles."""
    start_time = time.time()
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"step": "embed", "error": "OPENAI_API_KEY not set"}
    
    # Prepare texts
    texts = []
    for a in articles:
        text = f"{a.get('title', '')} {a.get('description', '')}"
        texts.append(text[:8000])  # Limit length
    
    try:
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "text-embedding-3-small",
                "input": texts
            },
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        
        # Add embeddings to articles
        for i, article in enumerate(articles):
            article["embedding"] = embeddings[i]
        
        return {
            "step": "embed",
            "model": "text-embedding-3-small",
            "articles": articles,
            "count": len(embeddings),
            "dimensions": len(embeddings[0]) if embeddings else 0,
            "duration_ms": int((time.time() - start_time) * 1000)
        }
        
    except Exception as e:
        return {
            "step": "embed",
            "error": str(e),
            "duration_ms": int((time.time() - start_time) * 1000)
        }


# ============================================
# STEP 4: CLUSTER
# ============================================

def lab_cluster(
    articles: list[dict],
    eps: float = 0.65,
    min_samples: int = 2
) -> dict:
    """Cluster articles using DBSCAN."""
    from sklearn.cluster import DBSCAN
    from sklearn.metrics.pairwise import cosine_distances
    
    start_time = time.time()
    
    # Extract embeddings
    embeddings = []
    valid_articles = []
    for a in articles:
        if a.get("embedding"):
            embeddings.append(a["embedding"])
            valid_articles.append(a)
    
    if len(embeddings) < 2:
        return {
            "step": "cluster",
            "error": "Not enough articles with embeddings",
            "count": len(embeddings)
        }
    
    # Compute distance matrix
    embeddings_array = np.array(embeddings)
    distance_matrix = cosine_distances(embeddings_array)
    
    # DBSCAN clustering
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed")
    labels = clustering.fit_predict(distance_matrix)
    
    # Group articles by cluster
    clusters = {}
    for i, label in enumerate(labels):
        label_int = int(label)
        if label_int not in clusters:
            clusters[label_int] = []
        valid_articles[i]["cluster_id"] = label_int
        clusters[label_int].append(valid_articles[i])
    
    # Prepare display data
    cluster_info = []
    for cluster_id, cluster_articles in clusters.items():
        if cluster_id == -1:
            cluster_info.append({
                "cluster_id": -1,
                "label": "Noise (unclustered)",
                "count": len(cluster_articles),
                "articles": [{"title": a.get("title", "")[:60], "source": a.get("source_name", "")} for a in cluster_articles]
            })
        else:
            sources = list(set(a.get("source_name", "") for a in cluster_articles))
            tiers = list(set(a.get("source_tier", "") for a in cluster_articles))
            cluster_info.append({
                "cluster_id": cluster_id,
                "label": f"Cluster {cluster_id}",
                "count": len(cluster_articles),
                "sources": sources,
                "tiers": tiers,
                "articles": [{"title": a.get("title", "")[:60], "source": a.get("source_name", ""), "tier": a.get("source_tier", "")} for a in cluster_articles]
            })
    
    # Sort: valid clusters first, then noise
    cluster_info.sort(key=lambda x: (x["cluster_id"] == -1, -x["count"]))
    
    return {
        "step": "cluster",
        "params": {"eps": eps, "min_samples": min_samples},
        "clusters": clusters,
        "cluster_info": cluster_info,
        "cluster_count": len([c for c in clusters.keys() if c != -1]),
        "noise_count": len(clusters.get(-1, [])),
        "duration_ms": int((time.time() - start_time) * 1000)
    }


# ============================================
# STEP 5: SCORE
# ============================================

def lab_score(
    clusters: dict[int, list[dict]],
    params: dict = None
) -> dict:
    """Score clusters using Radar + Loupe strategy."""
    start_time = time.time()
    params = params or DEFAULT_PARAMS
    
    scored_clusters = []
    
    for cluster_id, articles in clusters.items():
        if cluster_id == -1:
            continue  # Skip noise
        
        # Count by tier
        authority_count = sum(1 for a in articles if a.get("source_tier") == "authority")
        generalist_count = sum(1 for a in articles if a.get("source_tier") == "generalist")
        corporate_count = sum(1 for a in articles if a.get("source_tier") == "corporate")
        source_count = len(set(a.get("source_name", "") for a in articles))
        
        # Calculate base score with tier multipliers
        multipliers = params.get("tier_multipliers", DEFAULT_PARAMS["tier_multipliers"])
        base_score = 0
        for a in articles:
            tier = a.get("source_tier", "generalist")
            source_score = a.get("source_score", 50)
            base_score += source_score * multipliers.get(tier, 1.0)
        
        # Bonuses
        source_bonus = (source_count - 1) * params.get("cluster_bonus_per_source", 20)
        mixed_bonus = params.get("mixed_tier_bonus", 50) if (authority_count > 0 and generalist_count > 0) else 0
        
        # Corporate penalty
        corporate_penalty = max(0, corporate_count - params.get("max_corporate_per_cluster", 1)) * 50
        
        total_score = base_score + source_bonus + mixed_bonus - corporate_penalty
        
        # Validation rules
        is_valid = False
        reason = ""
        
        if authority_count >= params.get("min_authority_sources", 1):
            is_valid = True
            reason = f"Radar: {authority_count} authority source(s)"
        elif generalist_count >= params.get("min_generalist_sources", 5):
            is_valid = True
            reason = f"Loupe: {generalist_count} generalist sources"
        else:
            reason = f"Insufficient: {authority_count} authority, {generalist_count} generalist"
        
        scored_clusters.append({
            "cluster_id": cluster_id,
            "articles": articles,
            "authority_count": authority_count,
            "generalist_count": generalist_count,
            "corporate_count": corporate_count,
            "source_count": source_count,
            "base_score": round(base_score, 1),
            "source_bonus": source_bonus,
            "mixed_bonus": mixed_bonus,
            "corporate_penalty": corporate_penalty,
            "total_score": round(total_score, 1),
            "is_valid": is_valid,
            "reason": reason
        })
    
    # Sort by score
    scored_clusters.sort(key=lambda x: x["total_score"], reverse=True)
    
    valid_clusters = [c for c in scored_clusters if c["is_valid"]]
    invalid_clusters = [c for c in scored_clusters if not c["is_valid"]]
    
    return {
        "step": "score",
        "params": params,
        "scored_clusters": scored_clusters,
        "valid_clusters": valid_clusters,
        "invalid_clusters": invalid_clusters,
        "valid_count": len(valid_clusters),
        "invalid_count": len(invalid_clusters),
        "duration_ms": int((time.time() - start_time) * 1000)
    }


# ============================================
# STEP 6: ENRICH
# ============================================

def lab_enrich(cluster: dict) -> dict:
    """Enrich cluster with Perplexity context."""
    start_time = time.time()
    
    articles = cluster.get("articles", [])
    titles = [a.get("title", "") for a in articles[:5]]
    
    # Determine topic
    topic = articles[0].get("classified_topic") or articles[0].get("topic", "unknown") if articles else "unknown"
    
    # Build query
    articles_text = "\n".join([f"- {t}" for t in titles])
    query = f"""I'm researching these news stories about {topic}:

{articles_text}

Please provide:
1. Brief background context (2-3 sentences) that helps understand why this matters
2. Any important recent developments related to these stories
3. Key stakeholders or companies involved

Be concise and factual."""

    result = call_perplexity(query)
    
    return {
        "step": "enrich",
        "cluster_id": cluster.get("cluster_id"),
        "topic": topic,
        "query": query,
        "context": result.get("context", ""),
        "citations": result.get("citations", []),
        "error": result.get("error"),
        "duration_ms": int((time.time() - start_time) * 1000)
    }


# ============================================
# STEP 7: SUMMARIZE
# ============================================

def lab_summarize(
    cluster: dict,
    context: str = "",
    model: str = "llama-3.3-70b-versatile",
    prompt_template: str = None
) -> dict:
    """Generate structured summary for cluster."""
    start_time = time.time()
    prompt_template = prompt_template or DEFAULT_PROMPTS["summary"]
    
    articles = cluster.get("articles", [])
    topic = articles[0].get("classified_topic") or articles[0].get("topic", "unknown") if articles else "unknown"
    
    # Build articles text
    articles_text = ""
    for a in articles[:5]:
        articles_text += f"**{a.get('source_name', 'Unknown')}**: {a.get('title', '')}\n"
        if a.get('description'):
            articles_text += f"{a['description'][:200]}...\n"
        articles_text += "\n"
    
    # Build sources text
    sources_text = ""
    for a in articles[:5]:
        sources_text += f"- [{a.get('source_name', 'Unknown')}]({a.get('url', '')})\n"
    
    prompt = prompt_template.format(
        topic=topic.upper(),
        articles=articles_text,
        context=context or "No additional context available.",
        sources=sources_text
    )
    
    result = call_groq(prompt, model=model, max_tokens=1000, temperature=0.5)
    
    # Parse summary
    summary_text = result.get("content", "")
    parsed = parse_summary(summary_text)
    
    return {
        "step": "summarize",
        "cluster_id": cluster.get("cluster_id"),
        "topic": topic,
        "model": model,
        "prompt": prompt,
        "prompt_template": prompt_template,
        "summary_markdown": summary_text,
        "title": parsed.get("title", ""),
        "key_points": parsed.get("key_points", []),
        "why_it_matters": parsed.get("why_it_matters", ""),
        "llm_result": result,
        "duration_ms": int((time.time() - start_time) * 1000)
    }


def parse_summary(text: str) -> dict:
    """Parse generated summary."""
    result = {"title": "", "key_points": [], "why_it_matters": ""}
    
    lines = text.strip().split("\n")
    
    # Extract title
    for line in lines:
        if line.startswith("## "):
            result["title"] = line[3:].strip()
            break
    
    # Extract key points
    in_key_points = False
    for line in lines:
        if "Key Points:" in line or "Points clés:" in line:
            in_key_points = True
            continue
        if in_key_points:
            if line.startswith("•") or line.startswith("-") or line.startswith("*"):
                point = line.lstrip("•-* ").strip()
                if point:
                    result["key_points"].append(point)
            elif line.startswith("**") or line.strip() == "":
                if result["key_points"]:
                    in_key_points = False
    
    # Extract why it matters
    in_why = False
    why_lines = []
    for line in lines:
        if "Why It Matters:" in line or "Pourquoi c'est important:" in line:
            in_why = True
            continue
        if in_why:
            if line.startswith("**Sources") or line.startswith("**Source"):
                break
            why_lines.append(line)
    
    result["why_it_matters"] = " ".join(why_lines).strip()
    
    return result


# ============================================
# STEP 8: SCRIPT
# ============================================

def lab_script(
    summary: dict,
    context: str = "",
    model: str = "llama-3.3-70b-versatile",
    prompt_template: str = None
) -> dict:
    """Generate podcast script for cluster."""
    start_time = time.time()
    prompt_template = prompt_template or DEFAULT_PROMPTS["script"]
    
    topic = summary.get("topic", "unknown")
    summary_text = summary.get("summary_markdown", "")
    
    prompt = prompt_template.format(
        topic=topic.upper(),
        summary=summary_text,
        context=context or "No additional context."
    )
    
    result = call_groq(prompt, model=model, max_tokens=800, temperature=0.7)
    
    script_text = result.get("content", "")
    word_count = len(script_text.split()) if script_text else 0
    estimated_duration = int(word_count / 2.5)  # ~150 words per minute
    
    return {
        "step": "script",
        "cluster_id": summary.get("cluster_id"),
        "topic": topic,
        "model": model,
        "prompt": prompt,
        "prompt_template": prompt_template,
        "script": script_text,
        "word_count": word_count,
        "estimated_duration_seconds": estimated_duration,
        "llm_result": result,
        "duration_ms": int((time.time() - start_time) * 1000)
    }


# ============================================
# STEP 9: STORE
# ============================================

def lab_store(
    articles: list[dict] = None,
    clusters: list[dict] = None,
    summaries: list[dict] = None,
    dry_run: bool = True
) -> dict:
    """Store results to database."""
    start_time = time.time()
    
    if dry_run:
        return {
            "step": "store",
            "dry_run": True,
            "would_store": {
                "articles": len(articles) if articles else 0,
                "clusters": len(clusters) if clusters else 0,
                "summaries": len(summaries) if summaries else 0
            },
            "duration_ms": int((time.time() - start_time) * 1000)
        }
    
    try:
        from db import supabase
        
        stored = {"articles": 0, "clusters": 0, "summaries": 0}
        
        # Store articles
        if articles:
            for a in articles:
                try:
                    record = {
                        "url": a.get("url"),
                        "title": a.get("title"),
                        "description": a.get("description"),
                        "source_name": a.get("source_name"),
                        "source_tier": a.get("source_tier"),
                        "topic": a.get("topic"),
                        "classified_topic": a.get("classified_topic"),
                        "cluster_id": a.get("cluster_id"),
                        "status": "processed"
                    }
                    supabase.table("articles").upsert(record, on_conflict="url").execute()
                    stored["articles"] += 1
                except Exception as e:
                    log.warning("Failed to store article", error=str(e))
        
        # Store clusters
        if clusters:
            for c in clusters:
                try:
                    record = {
                        "id": c.get("cluster_id"),
                        "topic": c.get("articles", [{}])[0].get("topic", "unknown"),
                        "total_score": c.get("total_score"),
                        "authority_count": c.get("authority_count"),
                        "generalist_count": c.get("generalist_count"),
                        "corporate_count": c.get("corporate_count"),
                        "source_count": c.get("source_count"),
                        "is_valid": c.get("is_valid"),
                        "validation_reason": c.get("reason")
                    }
                    supabase.table("clusters").upsert(record, on_conflict="id").execute()
                    stored["clusters"] += 1
                except Exception as e:
                    log.warning("Failed to store cluster", error=str(e))
        
        # Store summaries
        if summaries:
            today = datetime.now(timezone.utc).date().isoformat()
            for s in summaries:
                try:
                    record = {
                        "cluster_id": s.get("cluster_id"),
                        "topic": s.get("topic"),
                        "title": s.get("title"),
                        "summary_markdown": s.get("summary_markdown"),
                        "key_points": s.get("key_points", []),
                        "why_it_matters": s.get("why_it_matters"),
                        "date": today
                    }
                    supabase.table("cluster_summaries").upsert(
                        record, on_conflict="cluster_id,date"
                    ).execute()
                    stored["summaries"] += 1
                except Exception as e:
                    log.warning("Failed to store summary", error=str(e))
        
        return {
            "step": "store",
            "dry_run": False,
            "stored": stored,
            "duration_ms": int((time.time() - start_time) * 1000)
        }
        
    except Exception as e:
        return {
            "step": "store",
            "error": str(e),
            "duration_ms": int((time.time() - start_time) * 1000)
        }


# ============================================
# PROMPT MANAGEMENT
# ============================================

def get_prompts() -> dict:
    """Get current prompts (from DB or defaults)."""
    try:
        from db import supabase
        result = supabase.table("prompt_templates").select("*").execute()
        
        if result.data:
            prompts = {}
            for row in result.data:
                prompts[row["name"]] = row["template"]
            return prompts
    except:
        pass
    
    return DEFAULT_PROMPTS.copy()


def save_prompt(name: str, template: str) -> dict:
    """Save a prompt template."""
    try:
        from db import supabase
        
        supabase.table("prompt_templates").upsert({
            "name": name,
            "template": template,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }, on_conflict="name").execute()
        
        return {"success": True, "name": name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_params() -> dict:
    """Get current parameters."""
    try:
        from db import supabase
        result = supabase.table("pipeline_params").select("*").order("created_at", desc=True).limit(1).execute()
        
        if result.data:
            return result.data[0].get("params", DEFAULT_PARAMS)
    except:
        pass
    
    return DEFAULT_PARAMS.copy()


def save_params(params: dict) -> dict:
    """Save parameters."""
    try:
        from db import supabase
        
        supabase.table("pipeline_params").insert({
            "params": params,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# CONFIG ENDPOINT
# ============================================

def get_lab_config() -> dict:
    """Get all configuration for the Prompt Lab."""
    return {
        "topics": MVP_TOPICS,
        "models": GROQ_MODELS,
        "prompts": get_prompts(),
        "params": get_params(),
        "default_prompts": DEFAULT_PROMPTS,
        "default_params": DEFAULT_PARAMS
    }
