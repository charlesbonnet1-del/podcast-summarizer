"""
Keernel Summary Generator

Generates structured summaries for clusters using:
1. Perplexity for enrichment/fact-checking
2. LLM for final structured summary

Output format:
- Title (headline)
- Key Points (3-5 bullets)
- Sources (article links)
- Generated at timestamp
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()


# ============================================
# PERPLEXITY ENRICHMENT
# ============================================

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar"  # Fast model for enrichment


def enrich_with_perplexity(
    titles: list[str],
    descriptions: list[str],
    topic: str
) -> dict:
    """
    Use Perplexity to get additional context and verify facts.
    
    Returns:
        {
            "context": str,  # Additional context/background
            "citations": list[str],  # Source URLs from Perplexity
        }
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        log.warning("PERPLEXITY_API_KEY not set, skipping enrichment")
        return {"context": "", "citations": []}
    
    # Build query from titles
    articles_text = "\n".join([f"- {t}" for t in titles[:5]])
    
    prompt = f"""I'm researching these news stories about {topic}:

{articles_text}

Please provide:
1. Brief background context (2-3 sentences) that helps understand why this matters
2. Any important recent developments related to these stories
3. Key stakeholders or companies involved

Be concise and factual."""

    try:
        response = httpx.post(
            PERPLEXITY_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": PERPLEXITY_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.3
            },
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        context = result["choices"][0]["message"]["content"]
        citations = result.get("citations", [])
        
        return {
            "context": context,
            "citations": citations
        }
        
    except Exception as e:
        log.warning("Perplexity enrichment failed", error=str(e))
        return {"context": "", "citations": []}


# ============================================
# SUMMARY GENERATION
# ============================================

SUMMARY_PROMPT = """You are a professional intelligence analyst writing a briefing.

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
- Write in the same language as the articles (French if articles are in French)
"""


def generate_cluster_summary(
    articles: list[dict],
    topic: str,
    enrich: bool = True
) -> dict:
    """
    Generate a structured summary for a cluster of articles.
    
    Args:
        articles: List of articles in the cluster
        topic: Topic name
        enrich: Whether to use Perplexity enrichment
    
    Returns:
        {
            "title": str,
            "summary_html": str,  # Full formatted summary
            "key_points": list[str],
            "why_it_matters": str,
            "sources": list[dict],  # [{name, url}]
            "perplexity_context": str,
            "generated_at": str,
        }
    """
    if not articles:
        return None
    
    # Extract data from articles
    titles = [a.get("title", "") for a in articles]
    descriptions = [a.get("description", "") for a in articles]
    
    # Build sources list
    sources = []
    for a in articles:
        sources.append({
            "name": a.get("source_name", "Unknown"),
            "url": a.get("url", ""),
            "title": a.get("title", "")[:80]
        })
    
    # Perplexity enrichment
    context = ""
    perplexity_citations = []
    if enrich:
        enrichment = enrich_with_perplexity(titles, descriptions, topic)
        context = enrichment.get("context", "")
        perplexity_citations = enrichment.get("citations", [])
    
    # Build articles text for prompt
    articles_text = ""
    for a in articles[:5]:
        articles_text += f"**{a.get('source_name', 'Unknown')}**: {a.get('title', '')}\n"
        if a.get('description'):
            articles_text += f"{a['description'][:200]}...\n"
        articles_text += "\n"
    
    # Build sources text
    sources_text = ""
    for s in sources[:5]:
        sources_text += f"- [{s['name']}]({s['url']})\n"
    
    # Generate summary with LLM
    prompt = SUMMARY_PROMPT.format(
        topic=topic.upper(),
        articles=articles_text,
        context=context or "No additional context available.",
        sources=sources_text
    )
    
    summary_text = call_llm_for_summary(prompt)
    
    if not summary_text:
        return None
    
    # Parse the generated summary
    parsed = parse_summary(summary_text)
    
    return {
        "title": parsed.get("title", f"{topic.upper()} Briefing"),
        "summary_html": summary_text,
        "summary_markdown": summary_text,
        "key_points": parsed.get("key_points", []),
        "why_it_matters": parsed.get("why_it_matters", ""),
        "sources": sources,
        "perplexity_context": context,
        "perplexity_citations": perplexity_citations,
        "topic": topic,
        "article_count": len(articles),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def call_llm_for_summary(prompt: str) -> str:
    """Call LLM (Groq or OpenAI) to generate summary."""
    
    # Try Groq first (free)
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.5
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning("Groq summary failed, trying OpenAI", error=str(e))
    
    # Fallback to OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.5
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.error("OpenAI summary failed", error=str(e))
    
    return None


def parse_summary(text: str) -> dict:
    """Parse the generated summary to extract components."""
    result = {
        "title": "",
        "key_points": [],
        "why_it_matters": ""
    }
    
    lines = text.strip().split("\n")
    
    # Extract title (first ## line)
    for line in lines:
        if line.startswith("## "):
            result["title"] = line[3:].strip()
            break
    
    # Extract key points (bullet points after "Key Points:")
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
    
    # Extract "Why It Matters"
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
# BATCH SUMMARY GENERATION
# ============================================

def generate_summaries_for_clusters(
    clusters: dict[int, list[dict]],
    topic: str
) -> list[dict]:
    """
    Generate summaries for all valid clusters.
    
    Returns list of summary dicts.
    """
    summaries = []
    
    for cluster_id, articles in clusters.items():
        if cluster_id == -1:  # Skip noise
            continue
        
        if len(articles) < 2:  # Skip tiny clusters
            continue
        
        log.info(f"Generating summary for cluster {cluster_id} ({len(articles)} articles)")
        
        summary = generate_cluster_summary(articles, topic, enrich=True)
        
        if summary:
            summary["cluster_id"] = cluster_id
            summaries.append(summary)
        
        # Rate limiting
        time.sleep(0.5)
    
    log.info(f"✅ Generated {len(summaries)} summaries")
    return summaries


# ============================================
# DATABASE STORAGE
# ============================================

def store_summaries(summaries: list[dict], table: str = "cluster_summaries") -> int:
    """Store summaries in Supabase."""
    try:
        from db import supabase
        
        stored = 0
        for s in summaries:
            try:
                record = {
                    "cluster_id": s["cluster_id"],
                    "topic": s["topic"],
                    "title": s["title"],
                    "summary_markdown": s["summary_markdown"],
                    "key_points": s["key_points"],
                    "why_it_matters": s["why_it_matters"],
                    "sources": s["sources"],
                    "article_count": s["article_count"],
                    "perplexity_context": s.get("perplexity_context"),
                    "generated_at": s["generated_at"],
                }
                
                supabase.table(table).insert(record).execute()
                stored += 1
                
            except Exception as e:
                log.warning("Failed to store summary", error=str(e))
        
        return stored
        
    except ImportError:
        log.warning("Supabase not available")
        return 0


# ============================================
# MAIN (for testing)
# ============================================

if __name__ == "__main__":
    # Test with sample articles
    test_articles = [
        {
            "title": "OpenAI releases GPT-5 with breakthrough reasoning capabilities",
            "description": "The new model shows significant improvements in math and coding.",
            "source_name": "TechCrunch",
            "url": "https://techcrunch.com/openai-gpt5"
        },
        {
            "title": "GPT-5 achieves human-level performance on complex benchmarks",
            "description": "Independent researchers confirm the capabilities.",
            "source_name": "MIT Tech Review",
            "url": "https://technologyreview.com/gpt5-benchmarks"
        },
        {
            "title": "Anthropic responds to GPT-5 with Claude 4 announcement",
            "description": "The AI race heats up as competitors respond.",
            "source_name": "The Verge",
            "url": "https://theverge.com/claude-4"
        },
    ]
    
    print("=== GENERATING SUMMARY ===\n")
    summary = generate_cluster_summary(test_articles, "ia", enrich=False)
    
    if summary:
        print(f"Title: {summary['title']}\n")
        print("Key Points:")
        for p in summary['key_points']:
            print(f"  • {p}")
        print(f"\nWhy It Matters: {summary['why_it_matters'][:200]}...")
        print(f"\nSources: {len(summary['sources'])}")
