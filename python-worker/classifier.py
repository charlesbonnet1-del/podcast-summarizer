"""
Keernel Article Classifier

Uses LLM to classify articles from generalist sources.
Determines if article belongs to a specific topic or should be discarded.

Uses Groq (free tier) with Llama 3.3 70B for classification.
Fallback to OpenAI if Groq unavailable.
"""
import os
import json
from typing import Optional

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger()


# ============================================
# TOPIC DEFINITIONS (for LLM context)
# ============================================

TOPIC_DEFINITIONS = {
    "ia": """
        Artificial Intelligence, Machine Learning, Deep Learning, LLMs, GPT, Claude, 
        AI chips, Neural networks, Computer vision, NLP, Robotics, Automation,
        AI companies (OpenAI, Anthropic, Google DeepMind, Mistral, etc.)
    """,
    "macro": """
        Macroeconomics, Central banks, Interest rates, Inflation, GDP, 
        Geopolitics, Trade wars, Sanctions, Currency markets, Bonds,
        Economic policy, Fed, ECB, Global economy, Recession, Growth
    """,
    "asia": """
        Asian markets, China, Japan, Korea, Taiwan, India, Southeast Asia,
        Asian tech companies, Asian politics, Belt and Road, ASEAN,
        China-US relations, Asian startups, Asian economy
    """,
}

# Classification prompt template
CLASSIFICATION_PROMPT = """You are a news article classifier for a professional intelligence platform.

Given an article's title and description, determine which topic it belongs to.

TOPICS:
{topics_list}

ARTICLE:
Title: {title}
Description: {description}

INSTRUCTIONS:
1. If the article clearly belongs to one of the topics above, respond with that topic ID
2. If the article doesn't fit any topic well, respond with "discard"
3. Only respond with a single word: the topic ID or "discard"

YOUR CLASSIFICATION:"""


# ============================================
# GROQ CLIENT (Free tier - Llama 3.3 70B)
# ============================================

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


def classify_with_groq(title: str, description: str, topics: list[str]) -> str | None:
    """
    Classify article using Groq API (free tier).
    
    Returns:
        Topic ID or "discard", None on error
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        log.warning("GROQ_API_KEY not set")
        return None
    
    # Build topics list for prompt
    topics_list = "\n".join([
        f"- {topic}: {TOPIC_DEFINITIONS.get(topic, topic)}"
        for topic in topics
    ])
    
    prompt = CLASSIFICATION_PROMPT.format(
        topics_list=topics_list,
        title=title,
        description=description[:500]
    )
    
    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 20,
                "temperature": 0
            },
            timeout=10
        )
        response.raise_for_status()
        
        result = response.json()
        classification = result["choices"][0]["message"]["content"].strip().lower()
        
        # Validate response
        if classification in topics or classification == "discard":
            return classification
        
        # Try to extract topic from response
        for topic in topics:
            if topic in classification:
                return topic
        
        return "discard"
        
    except Exception as e:
        log.warning("Groq classification failed", error=str(e))
        return None


# ============================================
# OPENAI FALLBACK
# ============================================

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"


def classify_with_openai(title: str, description: str, topics: list[str]) -> str | None:
    """
    Classify article using OpenAI API (fallback).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY not set")
        return None
    
    topics_list = "\n".join([
        f"- {topic}: {TOPIC_DEFINITIONS.get(topic, topic)}"
        for topic in topics
    ])
    
    prompt = CLASSIFICATION_PROMPT.format(
        topics_list=topics_list,
        title=title,
        description=description[:500]
    )
    
    try:
        response = httpx.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 20,
                "temperature": 0
            },
            timeout=10
        )
        response.raise_for_status()
        
        result = response.json()
        classification = result["choices"][0]["message"]["content"].strip().lower()
        
        if classification in topics or classification == "discard":
            return classification
        
        for topic in topics:
            if topic in classification:
                return topic
        
        return "discard"
        
    except Exception as e:
        log.warning("OpenAI classification failed", error=str(e))
        return None


# ============================================
# BATCH CLASSIFICATION
# ============================================

def classify_article(
    title: str, 
    description: str, 
    topics: list[str],
    prefer_groq: bool = True
) -> str:
    """
    Classify a single article.
    
    Args:
        title: Article title
        description: Article description/summary
        topics: List of valid topic IDs
        prefer_groq: Use Groq first (free tier)
    
    Returns:
        Topic ID or "discard"
    """
    if prefer_groq:
        result = classify_with_groq(title, description, topics)
        if result:
            return result
        # Fallback to OpenAI
        result = classify_with_openai(title, description, topics)
        if result:
            return result
    else:
        result = classify_with_openai(title, description, topics)
        if result:
            return result
        result = classify_with_groq(title, description, topics)
        if result:
            return result
    
    # If all fails, discard
    return "discard"


def classify_articles_batch(
    articles: list[dict],
    topics: list[str],
    title_key: str = "title",
    description_key: str = "description"
) -> list[dict]:
    """
    Classify a batch of articles.
    
    Adds 'classified_topic' field to each article:
    - Topic ID if article belongs to that topic
    - "discard" if article doesn't fit any topic
    - Original topic if article is from authority source (no LLM needed)
    
    Args:
        articles: List of article dicts
        topics: List of valid topic IDs
        title_key: Key for article title
        description_key: Key for article description
    
    Returns:
        Same list with 'classified_topic' added
    """
    classified = 0
    discarded = 0
    skipped = 0
    
    for article in articles:
        # Skip if already has classification
        if article.get("classified_topic"):
            skipped += 1
            continue
        
        # Authority sources don't need classification
        if article.get("source_is_authority", False):
            article["classified_topic"] = article.get("topic", "discard")
            skipped += 1
            continue
        
        # Classify generalist sources
        title = article.get(title_key, "")
        description = article.get(description_key, "")
        
        if not title:
            article["classified_topic"] = "discard"
            discarded += 1
            continue
        
        result = classify_article(title, description, topics)
        article["classified_topic"] = result
        
        if result == "discard":
            discarded += 1
        else:
            classified += 1
    
    log.info(f"📊 Classification: {classified} matched, {discarded} discarded, {skipped} skipped")
    
    return articles


def filter_classified_articles(
    articles: list[dict],
    include_discarded: bool = False
) -> list[dict]:
    """
    Filter articles after classification.
    
    Args:
        articles: List of classified articles
        include_discarded: Whether to include discarded articles
    
    Returns:
        Filtered list
    """
    if include_discarded:
        return articles
    
    return [
        a for a in articles 
        if a.get("classified_topic") and a["classified_topic"] != "discard"
    ]


# ============================================
# TOPIC RELEVANCE SCORING
# ============================================

def score_topic_relevance(
    title: str,
    description: str,
    topic: str
) -> float:
    """
    Score how relevant an article is to a topic (0-1).
    
    Uses keyword matching for speed (no LLM call).
    Used for secondary ranking after classification.
    """
    text = f"{title} {description}".lower()
    
    # Topic-specific keywords
    TOPIC_KEYWORDS = {
        "ia": [
            "ai", "artificial intelligence", "machine learning", "deep learning",
            "neural", "gpt", "llm", "chatgpt", "claude", "openai", "anthropic",
            "mistral", "robot", "automation", "computer vision", "nlp"
        ],
        "macro": [
            "economy", "gdp", "inflation", "interest rate", "fed", "central bank",
            "recession", "growth", "trade", "tariff", "sanction", "geopolit",
            "currency", "bond", "fiscal", "monetary"
        ],
        "asia": [
            "china", "chinese", "japan", "japanese", "korea", "korean", "taiwan",
            "india", "indian", "vietnam", "indonesia", "singapore", "asia",
            "beijing", "tokyo", "seoul", "asean", "belt and road"
        ],
    }
    
    keywords = TOPIC_KEYWORDS.get(topic, [])
    if not keywords:
        return 0.5  # Neutral score for unknown topics
    
    matches = sum(1 for kw in keywords if kw in text)
    
    # Normalize to 0-1 (max score at 5+ matches)
    return min(1.0, matches / 5)


# ============================================
# MAIN (for testing)
# ============================================

if __name__ == "__main__":
    # Test classification
    test_articles = [
        {
            "title": "OpenAI releases GPT-5 with breakthrough reasoning capabilities",
            "description": "The new model shows significant improvements in math and coding tasks.",
            "source_is_authority": False,
            "topic": "general"
        },
        {
            "title": "Fed signals potential rate cut in March meeting",
            "description": "Federal Reserve officials discussed easing monetary policy amid cooling inflation.",
            "source_is_authority": False,
            "topic": "general"
        },
        {
            "title": "Taiwan semiconductor exports hit record high",
            "description": "TSMC leads surge in chip exports as AI demand continues to grow.",
            "source_is_authority": False,
            "topic": "general"
        },
        {
            "title": "Local bakery wins best croissant award",
            "description": "A small Paris bakery has been recognized for its exceptional pastries.",
            "source_is_authority": False,
            "topic": "general"
        },
    ]
    
    print("=== CLASSIFICATION TEST ===")
    topics = ["ia", "macro", "asia"]
    
    classified = classify_articles_batch(test_articles, topics)
    
    for article in classified:
        print(f"\n{article['title'][:50]}...")
        print(f"  -> {article['classified_topic']}")
