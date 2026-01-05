"""
Alternative Sources - ArXiv, SEC EDGAR, GitHub Trending, Reddit

Ces sources ne sont pas des RSS classiques et nécessitent un traitement spécial.
Elles sont intégrées au pipeline de fetch via fetch_alternative_sources().
"""
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import xml.etree.ElementTree as ET

import httpx
import structlog

log = structlog.get_logger()


# ============================================
# CONFIGURATION
# ============================================

# ArXiv categories to monitor
ARXIV_CATEGORIES = [
    "cs.AI",   # Artificial Intelligence
    "cs.LG",   # Machine Learning
    "cs.CL",   # Computation and Language (NLP)
    "cs.CV",   # Computer Vision
    "cs.NE",   # Neural and Evolutionary Computing
]

# SEC: Companies to monitor (tickers)
SEC_TICKERS = [
    "NVDA", "MSFT", "GOOGL", "GOOG", "META", "AMZN", "AAPL",  # Big Tech
    "TSLA", "AMD", "INTC", "AVGO", "CRM", "ORCL",  # Tech
    "PLTR", "SNOW", "AI", "PATH",  # AI companies
]

# SEC: Filing types to monitor
SEC_FILING_TYPES = ["8-K", "10-K", "10-Q", "4"]  # 8-K = material events, 4 = insider trading

# GitHub: Languages/topics to monitor
GITHUB_TOPICS = ["machine-learning", "deep-learning", "llm", "ai", "gpt", "langchain", "llama"]

# Reddit: Subreddits to monitor
REDDIT_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA", 
    "artificial",
    "singularity",
    "OpenAI",
]


# ============================================
# ARXIV
# ============================================

def fetch_arxiv(
    categories: list[str] = None,
    max_results: int = 50,
    max_age_days: int = 7
) -> tuple[list[dict], str | None]:
    """
    Fetch recent papers from ArXiv.
    
    Returns:
        (articles, error_message)
    """
    categories = categories or ARXIV_CATEGORIES
    articles = []
    
    for category in categories:
        try:
            # ArXiv API
            url = f"http://export.arxiv.org/api/query?search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending&max_results={max_results // len(categories)}"
            
            response = httpx.get(url, timeout=30)
            response.raise_for_status()
            
            # Parse Atom feed
            root = ET.fromstring(response.text)
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
            
            entries = root.findall("atom:entry", ns)
            
            for entry in entries:
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                published = entry.find("atom:published", ns)
                link = entry.find("atom:id", ns)
                
                # Get authors
                authors = entry.findall("atom:author/atom:name", ns)
                author_names = [a.text for a in authors[:3]] if authors else []
                
                # Get categories
                cats = entry.findall("arxiv:primary_category", ns)
                primary_cat = cats[0].get("term") if cats else category
                
                if title is not None and link is not None:
                    articles.append({
                        "title": title.text.strip().replace("\n", " "),
                        "url": link.text.strip(),
                        "description": summary.text.strip()[:500] if summary is not None and summary.text else "",
                        "published_at": published.text if published is not None else None,
                        "source_name": f"ArXiv [{primary_cat}]",
                        "source_tier": "authority",
                        "topic": "ia",
                        "language": "en",
                        "authors": author_names,
                        "source_type": "arxiv",
                    })
            
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            log.warning(f"ArXiv fetch error for {category}: {e}")
    
    log.info(f"📚 ArXiv: Fetched {len(articles)} papers")
    return articles, None if articles else "No papers found"


# ============================================
# SEC EDGAR
# ============================================

def fetch_sec_edgar(
    filing_types: list[str] = None,
    max_results: int = 50
) -> tuple[list[dict], str | None]:
    """
    Fetch recent SEC filings.
    
    Returns:
        (articles, error_message)
    """
    filing_types = filing_types or SEC_FILING_TYPES
    articles = []
    
    try:
        # SEC RSS feed for recent filings
        headers = {
            "User-Agent": "Keernel Intelligence research@keernel.com",
            "Accept": "application/atom+xml"
        }
        
        for filing_type in filing_types:
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={filing_type}&company=&dateb=&owner=include&count=40&output=atom"
            
            try:
                response = httpx.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                root = ET.fromstring(response.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                
                entries = root.findall("atom:entry", ns)
                
                for entry in entries:
                    title_elem = entry.find("atom:title", ns)
                    link_elem = entry.find("atom:link", ns)
                    summary_elem = entry.find("atom:summary", ns)
                    updated_elem = entry.find("atom:updated", ns)
                    
                    if title_elem is not None and title_elem.text:
                        title = title_elem.text.strip()
                        
                        # Extract company name and ticker from title
                        # Format: "8-K - NVIDIA CORP (0001045810) (Filer)"
                        company_match = re.search(r'- (.+?) \(', title)
                        company_name = company_match.group(1) if company_match else "Unknown"
                        
                        articles.append({
                            "title": f"[{filing_type}] {company_name}: {title[:100]}",
                            "url": link_elem.get("href") if link_elem is not None else "",
                            "description": summary_elem.text[:500] if summary_elem is not None and summary_elem.text else "",
                            "published_at": updated_elem.text if updated_elem is not None else None,
                            "source_name": f"SEC EDGAR [{filing_type}]",
                            "source_tier": "authority",
                            "topic": "macro",
                            "language": "en",
                            "filing_type": filing_type,
                            "company": company_name,
                            "source_type": "sec",
                        })
                
                time.sleep(0.3)
                
            except Exception as e:
                log.warning(f"SEC fetch error for {filing_type}: {e}")
        
        log.info(f"📊 SEC EDGAR: Fetched {len(articles)} filings")
        return articles, None if articles else "No filings found"
        
    except Exception as e:
        log.error(f"SEC EDGAR error: {e}")
        return [], str(e)


# ============================================
# GITHUB TRENDING
# ============================================

def fetch_github_trending(
    since: str = "daily",  # daily, weekly, monthly
    max_results: int = 25
) -> tuple[list[dict], str | None]:
    """
    Fetch trending GitHub repositories.
    
    Note: GitHub doesn't have an official API for trending.
    We use the unofficial github-trending-api or scrape.
    
    Returns:
        (articles, error_message)
    """
    articles = []
    
    try:
        # Use unofficial trending API
        url = f"https://api.gitterapp.com/repositories?since={since}&spoken_language_code=en"
        
        headers = {
            "User-Agent": "Keernel/2.0",
            "Accept": "application/json"
        }
        
        response = httpx.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            # Fallback: try alternative API
            url = f"https://gh-trending-api.herokuapp.com/repositories?since={since}"
            response = httpx.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            repos = response.json()
            
            for repo in repos[:max_results]:
                # Filter by relevant topics
                description = repo.get("description", "") or ""
                language = repo.get("language", "") or ""
                name = repo.get("name", "") or ""
                
                # Check if AI/ML related
                keywords = ["ai", "ml", "llm", "gpt", "transformer", "neural", "deep", "machine learning", "langchain", "llama", "model"]
                is_relevant = any(kw in description.lower() or kw in name.lower() for kw in keywords)
                
                # Also check language
                ml_languages = ["Python", "Jupyter Notebook", "C++", "Rust", "TypeScript"]
                is_ml_language = language in ml_languages
                
                if is_relevant or is_ml_language:
                    stars_today = repo.get("currentPeriodStars", 0) or repo.get("stars_today", 0)
                    total_stars = repo.get("stars", 0) or repo.get("stargazers_count", 0)
                    
                    articles.append({
                        "title": f"🔥 {repo.get('author', '')}/{name} (+{stars_today} ⭐ today)",
                        "url": repo.get("url", f"https://github.com/{repo.get('author', '')}/{name}"),
                        "description": f"{description[:300]} | Language: {language} | Total: {total_stars}⭐",
                        "published_at": datetime.now(timezone.utc).isoformat(),
                        "source_name": "GitHub Trending",
                        "source_tier": "generalist",
                        "topic": "ia",
                        "language": "en",
                        "stars_today": stars_today,
                        "total_stars": total_stars,
                        "repo_language": language,
                        "source_type": "github",
                    })
            
            log.info(f"💻 GitHub: Fetched {len(articles)} trending repos")
            return articles, None
        else:
            return [], f"HTTP {response.status_code}"
            
    except Exception as e:
        log.warning(f"GitHub trending error: {e}")
        
        # Fallback: Just return empty with warning
        return [], str(e)


# ============================================
# REDDIT
# ============================================

def fetch_reddit(
    subreddits: list[str] = None,
    sort: str = "hot",  # hot, new, top
    max_per_sub: int = 10,
    min_score: int = 50
) -> tuple[list[dict], str | None]:
    """
    Fetch posts from Reddit subreddits via RSS.
    
    Returns:
        (articles, error_message)
    """
    subreddits = subreddits or REDDIT_SUBREDDITS
    articles = []
    
    headers = {
        "User-Agent": "Keernel/2.0 Intelligence Platform"
    }
    
    for subreddit in subreddits:
        try:
            # Reddit RSS
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.rss?limit={max_per_sub}"
            
            response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            entries = root.findall("atom:entry", ns)
            
            for entry in entries:
                title = entry.find("atom:title", ns)
                link = entry.find("atom:link", ns)
                content = entry.find("atom:content", ns)
                updated = entry.find("atom:updated", ns)
                
                if title is not None and title.text:
                    # Extract score from content if available
                    score = 0
                    if content is not None and content.text:
                        score_match = re.search(r'(\d+)\s*points?', content.text)
                        if score_match:
                            score = int(score_match.group(1))
                    
                    # Filter by minimum score
                    if score >= min_score or sort == "new":
                        # Clean up HTML content
                        description = ""
                        if content is not None and content.text:
                            description = re.sub(r'<[^>]+>', '', content.text)[:400]
                        
                        articles.append({
                            "title": f"[r/{subreddit}] {title.text.strip()}",
                            "url": link.get("href") if link is not None else "",
                            "description": description,
                            "published_at": updated.text if updated is not None else None,
                            "source_name": f"Reddit r/{subreddit}",
                            "source_tier": "generalist",
                            "topic": "ia",
                            "language": "en",
                            "score": score,
                            "subreddit": subreddit,
                            "source_type": "reddit",
                        })
            
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            log.warning(f"Reddit fetch error for r/{subreddit}: {e}")
    
    log.info(f"🤖 Reddit: Fetched {len(articles)} posts")
    return articles, None if articles else "No posts found"


# ============================================
# PATENTS (USPTO) - Simplified
# ============================================

def fetch_patents(
    keywords: list[str] = None,
    max_results: int = 20
) -> tuple[list[dict], str | None]:
    """
    Fetch recent patent applications.
    
    Note: This is a simplified version using Google Patents RSS.
    For full USPTO access, consider their official API.
    
    Returns:
        (articles, error_message)
    """
    keywords = keywords or ["artificial intelligence", "machine learning", "neural network", "large language model"]
    articles = []
    
    try:
        # Google Patents doesn't have a public RSS, so we use USPTO's simpler feed
        # For now, return empty - full implementation would require USPTO API key
        log.info("📝 Patents: USPTO API not configured (optional)")
        return [], "USPTO API not configured"
        
    except Exception as e:
        log.warning(f"Patents fetch error: {e}")
        return [], str(e)


# ============================================
# MAIN FETCH FUNCTION
# ============================================

def fetch_alternative_sources(
    include_arxiv: bool = True,
    include_sec: bool = True,
    include_github: bool = True,
    include_reddit: bool = True,
    include_patents: bool = False
) -> tuple[list[dict], dict]:
    """
    Fetch all alternative sources.
    
    Returns:
        (all_articles, stats_dict)
    """
    all_articles = []
    stats = {
        "arxiv": {"count": 0, "error": None},
        "sec": {"count": 0, "error": None},
        "github": {"count": 0, "error": None},
        "reddit": {"count": 0, "error": None},
        "patents": {"count": 0, "error": None},
    }
    
    if include_arxiv:
        articles, error = fetch_arxiv()
        stats["arxiv"]["count"] = len(articles)
        stats["arxiv"]["error"] = error
        all_articles.extend(articles)
    
    if include_sec:
        articles, error = fetch_sec_edgar()
        stats["sec"]["count"] = len(articles)
        stats["sec"]["error"] = error
        all_articles.extend(articles)
    
    if include_github:
        articles, error = fetch_github_trending()
        stats["github"]["count"] = len(articles)
        stats["github"]["error"] = error
        all_articles.extend(articles)
    
    if include_reddit:
        articles, error = fetch_reddit()
        stats["reddit"]["count"] = len(articles)
        stats["reddit"]["error"] = error
        all_articles.extend(articles)
    
    if include_patents:
        articles, error = fetch_patents()
        stats["patents"]["count"] = len(articles)
        stats["patents"]["error"] = error
        all_articles.extend(articles)
    
    log.info(f"📦 Alternative sources: {len(all_articles)} total articles")
    return all_articles, stats


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":
    import json
    
    print("=" * 60)
    print("🔍 Testing Alternative Sources")
    print("=" * 60)
    
    articles, stats = fetch_alternative_sources()
    
    print(f"\n📊 Stats:")
    for source, data in stats.items():
        status = "✅" if data["count"] > 0 else "❌"
        print(f"  {status} {source}: {data['count']} articles")
        if data["error"]:
            print(f"     Error: {data['error']}")
    
    print(f"\n📰 Sample articles:")
    for a in articles[:10]:
        print(f"  [{a['source_type']}] {a['title'][:60]}...")
