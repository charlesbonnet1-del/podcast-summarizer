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
    errors = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Keernel/2.0; +https://keernel.com)",
        "Accept": "application/atom+xml, application/xml, text/xml, */*"
    }
    
    for category in categories:
        try:
            # ArXiv API - use HTTPS
            url = f"https://export.arxiv.org/api/query?search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending&max_results={max_results // len(categories)}"
            
            response = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
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
            
        except httpx.HTTPStatusError as e:
            errors.append(f"{category}: HTTP {e.response.status_code}")
            log.warning(f"ArXiv HTTP error for {category}: {e.response.status_code}")
        except Exception as e:
            errors.append(f"{category}: {str(e)[:30]}")
            log.warning(f"ArXiv fetch error for {category}: {e}")
    
    error_msg = None
    if not articles:
        error_msg = "; ".join(errors) if errors else "No papers found"
    
    log.info(f"📚 ArXiv: Fetched {len(articles)} papers")
    return articles, error_msg


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
    
    Uses multiple fallback APIs since unofficial APIs often go down.
    
    Returns:
        (articles, error_message)
    """
    articles = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Keernel/2.0)",
        "Accept": "application/json"
    }
    
    # Try multiple APIs in order
    apis = [
        f"https://api.gitterapp.com/repositories?since={since}&spoken_language_code=en",
        f"https://gh-trending-api.herokuapp.com/repositories?since={since}",
        f"https://github-trending-api.de-f.ast.workers.dev/?since={since}",
    ]
    
    repos = None
    last_error = None
    
    for api_url in apis:
        try:
            response = httpx.get(api_url, headers=headers, timeout=15, follow_redirects=True)
            if response.status_code == 200:
                repos = response.json()
                if repos:
                    break
        except Exception as e:
            last_error = str(e)[:50]
            continue
    
    if not repos:
        # Final fallback: scrape GitHub directly (simplified)
        try:
            scrape_url = f"https://github.com/trending?since={since}"
            response = httpx.get(scrape_url, headers=headers, timeout=15, follow_redirects=True)
            if response.status_code == 200:
                # Simple regex extraction
                import re
                pattern = r'href="/([^/]+/[^/]+)"[^>]*class="[^"]*Link[^"]*"'
                matches = re.findall(pattern, response.text)
                repos = []
                seen = set()
                for match in matches[:max_results * 2]:
                    if '/' in match and match not in seen and not match.startswith('topics/'):
                        parts = match.split('/')
                        if len(parts) == 2:
                            seen.add(match)
                            repos.append({
                                "author": parts[0],
                                "name": parts[1],
                                "url": f"https://github.com/{match}",
                                "description": "",
                                "language": "",
                                "stars": 0,
                                "currentPeriodStars": 0
                            })
        except Exception as e:
            last_error = f"Scrape failed: {str(e)[:30]}"
    
    if repos:
        for repo in repos[:max_results]:
            description = repo.get("description", "") or ""
            language = repo.get("language", "") or ""
            name = repo.get("name", "") or repo.get("repo", "") or ""
            author = repo.get("author", "") or repo.get("username", "") or ""
            
            # Check if AI/ML related
            keywords = ["ai", "ml", "llm", "gpt", "transformer", "neural", "deep", "machine learning", "langchain", "llama", "model", "agent"]
            is_relevant = any(kw in description.lower() or kw in name.lower() for kw in keywords)
            
            # Also check language
            ml_languages = ["Python", "Jupyter Notebook", "C++", "Rust", "TypeScript", "Go"]
            is_ml_language = language in ml_languages
            
            if is_relevant or is_ml_language or not language:  # Include if no language filter possible
                stars_today = repo.get("currentPeriodStars", 0) or repo.get("stars_today", 0) or 0
                total_stars = repo.get("stars", 0) or repo.get("stargazers_count", 0) or 0
                
                title = f"🔥 {author}/{name}"
                if stars_today:
                    title += f" (+{stars_today} ⭐ today)"
                
                articles.append({
                    "title": title,
                    "url": repo.get("url", f"https://github.com/{author}/{name}"),
                    "description": f"{description[:300]}" + (f" | {language}" if language else "") + (f" | {total_stars}⭐" if total_stars else ""),
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
        error_msg = last_error or "All APIs failed"
        log.warning(f"GitHub trending failed: {error_msg}")
        return [], error_msg


# ============================================
# REDDIT
# ============================================

def fetch_reddit(
    subreddits: list[str] = None,
    sort: str = "hot",  # hot, new, top
    max_per_sub: int = 10,
    min_score: int = 20
) -> tuple[list[dict], str | None]:
    """
    Fetch posts from Reddit subreddits via JSON API (more reliable than RSS).
    
    Returns:
        (articles, error_message)
    """
    subreddits = subreddits or REDDIT_SUBREDDITS
    articles = []
    errors = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for subreddit in subreddits:
        try:
            # Try JSON API first (more reliable than RSS)
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={max_per_sub}"
            
            response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            
            if response.status_code == 200:
                data = response.json()
                posts = data.get("data", {}).get("children", [])
                
                for post in posts:
                    post_data = post.get("data", {})
                    score = post_data.get("score", 0)
                    
                    # Filter by minimum score
                    if score >= min_score or sort == "new":
                        title = post_data.get("title", "")
                        selftext = post_data.get("selftext", "")[:300] if post_data.get("selftext") else ""
                        
                        articles.append({
                            "title": f"[r/{subreddit}] {title}",
                            "url": f"https://reddit.com{post_data.get('permalink', '')}",
                            "description": selftext or f"Score: {score} | Comments: {post_data.get('num_comments', 0)}",
                            "published_at": datetime.fromtimestamp(post_data.get("created_utc", 0), tz=timezone.utc).isoformat(),
                            "source_name": f"Reddit r/{subreddit}",
                            "source_tier": "generalist",
                            "topic": "ia",
                            "language": "en",
                            "score": score,
                            "subreddit": subreddit,
                            "source_type": "reddit",
                        })
            elif response.status_code == 403:
                errors.append(f"r/{subreddit}: Access denied")
            else:
                errors.append(f"r/{subreddit}: HTTP {response.status_code}")
            
            time.sleep(1.0)  # Reddit rate limiting is strict
            
        except Exception as e:
            errors.append(f"r/{subreddit}: {str(e)[:30]}")
            log.warning(f"Reddit fetch error for r/{subreddit}: {e}")
    
    error_msg = None
    if not articles:
        error_msg = "; ".join(errors) if errors else "No posts found"
    
    log.info(f"🤖 Reddit: Fetched {len(articles)} posts")
    return articles, error_msg


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
