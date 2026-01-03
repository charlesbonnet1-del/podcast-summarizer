"""
Keernel Scoring System - Radar + Loupe

Scoring strategy for B2B Intelligence Platform:

RADAR (Authority sources):
- Early detection of important signals
- High trust, niche expertise
- Score boost for authority sources

LOUPE (Generalist sources):
- Validation of mainstream coverage
- Require multiple sources for confirmation
- Lower individual weight but strong when clustered

SCORING FORMULA:
Base score = source_score (from library)
Tier multiplier:
- Authority: x2.0
- Corporate: x1.5 (capped at 1 per cluster)
- Generalist: x1.0

Cluster bonus:
- Multi-source cluster: +20 per additional source
- Mixed tier cluster (authority + generalist): +50 bonus

Selection rules:
- ≥1 authority source: INCLUDE (potential scoop)
- ≥5 generalist sources: INCLUDE (validated mainstream)
- Otherwise: EXCLUDE
"""
import structlog
from typing import Optional
from dataclasses import dataclass, field

log = structlog.get_logger()


# ============================================
# SCORING CONSTANTS
# ============================================

# Tier multipliers
TIER_MULTIPLIERS = {
    "authority": 2.0,
    "corporate": 1.5,
    "generalist": 1.0,
}

# Cluster bonuses
MULTI_SOURCE_BONUS = 20  # Per additional source
MIXED_TIER_BONUS = 50    # Authority + Generalist together

# Selection thresholds
MIN_AUTHORITY_SOURCES = 1   # At least 1 authority = include
MIN_GENERALIST_SOURCES = 5  # At least 5 generalist = include
MAX_CORPORATE_PER_CLUSTER = 1  # Cap corporate sources


# ============================================
# ARTICLE SCORING
# ============================================

def score_article(article: dict) -> float:
    """
    Calculate relevance score for a single article.
    
    Uses:
    - source_score from library (0-100)
    - source_tier for multiplier
    - topic_relevance (if available)
    
    Returns:
        Score (0-200+)
    """
    base_score = article.get("source_score", 50)
    tier = article.get("source_tier", "generalist")
    multiplier = TIER_MULTIPLIERS.get(tier, 1.0)
    
    # Apply tier multiplier
    score = base_score * multiplier
    
    # Add relevance bonus if classified
    if article.get("topic_relevance"):
        score += article["topic_relevance"] * 20
    
    return score


def score_articles(articles: list[dict]) -> list[dict]:
    """
    Score all articles and sort by score.
    
    Adds 'relevance_score' field to each article.
    """
    for article in articles:
        article["relevance_score"] = score_article(article)
    
    # Sort by score descending
    articles.sort(key=lambda x: x["relevance_score"], reverse=True)
    
    return articles


# ============================================
# CLUSTER SCORING
# ============================================

@dataclass
class ClusterScore:
    """Scoring details for a cluster."""
    cluster_id: int
    total_score: float = 0.0
    authority_count: int = 0
    generalist_count: int = 0
    corporate_count: int = 0
    source_count: int = 0
    unique_sources: set = field(default_factory=set)
    topics: set = field(default_factory=set)
    is_valid: bool = False
    reason: str = ""


def score_cluster(articles: list[dict], cluster_id: int = 0) -> ClusterScore:
    """
    Score a cluster of related articles.
    
    Args:
        articles: List of articles in the cluster
        cluster_id: Cluster identifier
    
    Returns:
        ClusterScore with details
    """
    cs = ClusterScore(cluster_id=cluster_id)
    
    if not articles:
        cs.reason = "Empty cluster"
        return cs
    
    # Count by tier
    corporate_articles = []
    
    for article in articles:
        tier = article.get("source_tier", "generalist")
        source_name = article.get("source_name", "unknown")
        topic = article.get("topic") or article.get("classified_topic", "unknown")
        
        cs.unique_sources.add(source_name)
        cs.topics.add(topic)
        
        if tier == "authority":
            cs.authority_count += 1
        elif tier == "corporate":
            cs.corporate_count += 1
            corporate_articles.append(article)
        else:
            cs.generalist_count += 1
    
    cs.source_count = len(cs.unique_sources)
    
    # Cap corporate sources
    effective_corporate = min(cs.corporate_count, MAX_CORPORATE_PER_CLUSTER)
    
    # Calculate base score (sum of article scores)
    base_score = sum(score_article(a) for a in articles)
    
    # Apply corporate cap penalty
    if cs.corporate_count > MAX_CORPORATE_PER_CLUSTER:
        # Remove excess corporate contribution
        excess = cs.corporate_count - MAX_CORPORATE_PER_CLUSTER
        corporate_articles_sorted = sorted(
            corporate_articles, 
            key=lambda x: score_article(x)
        )
        for a in corporate_articles_sorted[:excess]:
            base_score -= score_article(a)
    
    # Multi-source bonus
    if cs.source_count > 1:
        base_score += (cs.source_count - 1) * MULTI_SOURCE_BONUS
    
    # Mixed tier bonus (authority + generalist)
    if cs.authority_count > 0 and cs.generalist_count > 0:
        base_score += MIXED_TIER_BONUS
    
    cs.total_score = base_score
    
    # Determine validity
    effective_authority = cs.authority_count + effective_corporate
    
    if effective_authority >= MIN_AUTHORITY_SOURCES:
        cs.is_valid = True
        if cs.generalist_count > 0:
            cs.reason = f"Authority ({effective_authority}) + Generalist ({cs.generalist_count}) = Strong signal"
        else:
            cs.reason = f"Authority-only ({effective_authority}) = Potential scoop"
    elif cs.generalist_count >= MIN_GENERALIST_SOURCES:
        cs.is_valid = True
        cs.reason = f"Generalist ({cs.generalist_count}) = Validated mainstream"
    else:
        cs.is_valid = False
        cs.reason = f"Insufficient: {effective_authority} authority, {cs.generalist_count} generalist"
    
    return cs


def score_clusters(clusters: dict[int, list[dict]]) -> list[ClusterScore]:
    """
    Score all clusters.
    
    Args:
        clusters: Dict mapping cluster_id to list of articles
    
    Returns:
        List of ClusterScore sorted by total_score descending
    """
    scores = []
    
    for cluster_id, articles in clusters.items():
        if cluster_id == -1:  # Skip noise cluster
            continue
        cs = score_cluster(articles, cluster_id)
        scores.append(cs)
    
    # Sort by score
    scores.sort(key=lambda x: x.total_score, reverse=True)
    
    return scores


# ============================================
# CLUSTER SELECTION
# ============================================

def select_valid_clusters(
    clusters: dict[int, list[dict]],
    max_clusters: int = 10
) -> list[tuple[int, list[dict], ClusterScore]]:
    """
    Select valid clusters for inclusion.
    
    Args:
        clusters: Dict mapping cluster_id to articles
        max_clusters: Maximum clusters to select
    
    Returns:
        List of (cluster_id, articles, score) tuples
    """
    scores = score_clusters(clusters)
    
    valid = []
    for cs in scores:
        if cs.is_valid:
            valid.append((cs.cluster_id, clusters[cs.cluster_id], cs))
            if len(valid) >= max_clusters:
                break
    
    log.info(f"📊 Cluster selection: {len(valid)}/{len(scores)} valid clusters")
    
    # Log details
    for cluster_id, articles, cs in valid:
        log.info(
            f"  ✅ Cluster {cluster_id}: score={cs.total_score:.0f}, "
            f"auth={cs.authority_count}, gen={cs.generalist_count}, corp={cs.corporate_count} "
            f"({cs.reason})"
        )
    
    return valid


def select_best_articles_per_topic(
    articles: list[dict],
    topics: list[str],
    max_per_topic: int = 5
) -> dict[str, list[dict]]:
    """
    Select best articles for each topic.
    
    For use when clustering is not applied.
    
    Args:
        articles: All scored articles
        topics: List of topics to select for
        max_per_topic: Maximum articles per topic
    
    Returns:
        Dict mapping topic to selected articles
    """
    # Group by topic
    by_topic = {t: [] for t in topics}
    
    for article in articles:
        topic = article.get("topic") or article.get("classified_topic")
        if topic in by_topic:
            by_topic[topic].append(article)
    
    # Select best per topic
    selected = {}
    
    for topic, topic_articles in by_topic.items():
        # Sort by relevance_score
        sorted_articles = sorted(
            topic_articles,
            key=lambda x: x.get("relevance_score", 0),
            reverse=True
        )
        
        # Apply selection rules
        valid = []
        authority_seen = 0
        generalist_seen = 0
        
        for article in sorted_articles:
            tier = article.get("source_tier", "generalist")
            
            if tier in ["authority", "corporate"]:
                authority_seen += 1
                valid.append(article)
            else:
                generalist_seen += 1
                # Only include if we have enough generalist OR have authority backup
                if generalist_seen >= MIN_GENERALIST_SOURCES or authority_seen >= MIN_AUTHORITY_SOURCES:
                    valid.append(article)
            
            if len(valid) >= max_per_topic:
                break
        
        selected[topic] = valid
        log.info(f"  [{topic}] Selected {len(valid)} articles (auth={authority_seen}, gen={generalist_seen})")
    
    return selected


# ============================================
# SUMMARY STATS
# ============================================

def get_scoring_summary(articles: list[dict]) -> dict:
    """Get summary statistics for scored articles."""
    if not articles:
        return {"total": 0}
    
    authority = [a for a in articles if a.get("source_tier") == "authority"]
    corporate = [a for a in articles if a.get("source_tier") == "corporate"]
    generalist = [a for a in articles if a.get("source_tier") == "generalist"]
    
    scores = [a.get("relevance_score", 0) for a in articles]
    
    return {
        "total": len(articles),
        "authority": len(authority),
        "corporate": len(corporate),
        "generalist": len(generalist),
        "avg_score": sum(scores) / len(scores) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "min_score": min(scores) if scores else 0,
        "topics": list(set(a.get("topic", "unknown") for a in articles)),
    }


# ============================================
# MAIN (for testing)
# ============================================

if __name__ == "__main__":
    # Test scoring
    test_articles = [
        {
            "title": "OpenAI GPT-5",
            "source_name": "AI Snake Oil",
            "source_tier": "authority",
            "source_score": 95,
            "topic": "ia"
        },
        {
            "title": "OpenAI announces GPT-5",
            "source_name": "TechCrunch",
            "source_tier": "generalist",
            "source_score": 80,
            "topic": "ia"
        },
        {
            "title": "GPT-5 released by OpenAI",
            "source_name": "The Verge",
            "source_tier": "generalist",
            "source_score": 75,
            "topic": "ia"
        },
        {
            "title": "Introducing GPT-5",
            "source_name": "OpenAI",
            "source_tier": "corporate",
            "source_score": 90,
            "topic": "ia"
        },
    ]
    
    print("=== ARTICLE SCORING ===")
    scored = score_articles(test_articles)
    for a in scored:
        print(f"  [{a['source_tier']}] {a['source_name']}: {a['relevance_score']:.0f}")
    
    print("\n=== CLUSTER SCORING ===")
    clusters = {0: test_articles}
    cs = score_cluster(test_articles, cluster_id=0)
    print(f"  Score: {cs.total_score:.0f}")
    print(f"  Valid: {cs.is_valid}")
    print(f"  Reason: {cs.reason}")
    
    print("\n=== SUMMARY ===")
    summary = get_scoring_summary(scored)
    print(f"  Total: {summary['total']}")
    print(f"  Avg score: {summary['avg_score']:.0f}")
