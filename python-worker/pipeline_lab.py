"""
Pipeline Lab - Sandbox environment for testing the content pipeline.

V17: Allows testing fetcher → clustering → selection with custom parameters
without affecting production data.

Each step returns:
- results: The actual output
- exclusions: Items that were filtered out with reasons
- stats: Metrics about the step
"""

import os
from datetime import datetime, timedelta
from typing import Any
import structlog

from db import supabase
from sourcing import (
    GSheetSourceLibrary,
    fetch_rss_feed,
    fetch_bing_news
)
from cluster_pipeline import (
    embed_articles,
    get_embeddings_batch,
    EMBEDDING_MODEL
)

log = structlog.get_logger()


# ============================================
# DEFAULT PARAMETERS (V17)
# ============================================

DEFAULT_PARAMS = {
    # V19: Single format - 5 segments for 5 minute podcast
    "flash_segment_count": 5,
    "digest_segment_count": 5,  # deprecated - same as flash

    # Clustering - V20: HAC with lower min_cluster_size for small volumes
    "min_cluster_size": 2,  # Lowered from 3 for small article volumes
    "min_articles_fallback": 5,  # If no cluster, need at least this many articles
    "hac_distance_threshold": 0.45,  # Cosine distance threshold for HAC (= similarity > 0.55)

    # Time windows
    "content_queue_days": 3,
    "maturation_window_hours": 72,
    "segment_cache_days": 1,

    # Duration targets (seconds) - V19: ~60s per segment
    "flash_duration_min": 50,
    "flash_duration_max": 70,
    "digest_duration_min": 50,
    "digest_duration_max": 70,

    # Topics (all enabled by default)
    "topics_enabled": {
        "asia": True,
        "attention": True,
        "crypto": True,
        "cyber": True,
        "deals": True,
        "deep_tech": True,
        "energy": True,
        "health": True,
        "ia": True,
        "info": True,
        "macro": True,
        "persuasion": True,
        "regulation": True,
        "resources": True,
        "space": True
    },

    # Bing backup threshold
    "bing_backup_threshold": 5,  # Topics with < N articles get Bing backup

    # RSS limits
    "max_articles_per_rss": 10,
    "rss_timeout_seconds": 10,

    # ========== NEW ARCHITECTURE (V2) ==========
    # Fresh articles window
    "fresh_hours": 48,  # Articles are "fresh" for 48 hours

    # Archive enrichment
    "max_archive_articles": 2,  # Max archive articles per cluster
    "archive_min_similarity": 0.7,  # Min similarity for archive match
    "archive_max_age_days": 90,  # Max age of archive articles

    # Cluster deduplication
    "check_cluster_dedup": True,  # Check if cluster was already used
    "cluster_dedup_days": 7,  # Days to look back for dedup

    # Architecture selection
    "use_v2_architecture": False,  # Set to True to use new articles table
}


def get_default_params() -> dict:
    """Return default pipeline parameters."""
    return DEFAULT_PARAMS.copy()


# ============================================
# NOISE DETECTION
# ============================================

def is_noise_article(title: str, url: str, description: str = "") -> tuple[bool, str]:
    """
    Detect if an article is actually noise (non-article page).
    
    Returns:
        (is_noise: bool, reason: str)
    """
    title_lower = title.lower().strip()
    url_lower = url.lower()
    
    # 1. Title too short (likely navigation page)
    word_count = len(title.split())
    if word_count < 4:
        return True, f"Title too short ({word_count} words)"
    
    # 2. Title matches common non-article patterns
    noise_title_patterns = [
        # Navigation pages
        "home -", "- home", "homepage",
        "contact -", "- contact", "contact us",
        "about -", "- about", "about us",
        "login", "sign in", "sign up", "register",
        "subscribe", "subscription",
        "careers", "jobs", "work with us", "join us",
        "pricing", "plans", "tarifs",
        "terms", "privacy", "legal", "conditions",
        "faq", "help center", "support",
        "404", "page not found", "error",
        # Generic company pages
        "consultant -", "- consultant",
        "global management consulting",
        "who we are", "what we do",
        "our team", "our mission", "our values",
        "press room", "newsroom",  # These are index pages, not articles
    ]
    
    for pattern in noise_title_patterns:
        if pattern in title_lower:
            return True, f"Title matches noise pattern: '{pattern}'"
    
    # 3. Title is just company name + section
    # Pattern: "Section - Company" or "Company | Section" with very short section
    if " - " in title or " | " in title:
        parts = title.replace(" | ", " - ").split(" - ")
        if len(parts) == 2:
            # Both parts are short (likely "Home - Company" or "Company - About")
            if len(parts[0].split()) <= 2 and len(parts[1].split()) <= 3:
                return True, f"Title looks like navigation: '{title}'"
    
    # 4. URL patterns that indicate non-article pages
    noise_url_patterns = [
        "/home", "/index", "/default",
        "/about", "/contact", "/careers", "/jobs",
        "/login", "/signin", "/signup", "/register",
        "/subscribe", "/subscription", "/pricing",
        "/terms", "/privacy", "/legal",
        "/faq", "/help", "/support",
        "/tag/", "/category/", "/author/",  # Index pages
        "/page/", "/p/",  # Pagination
    ]
    
    for pattern in noise_url_patterns:
        if pattern in url_lower:
            return True, f"URL matches noise pattern: '{pattern}'"
    
    # 5. No description and short title = probably not an article
    if not description and word_count < 6:
        return True, "No description and short title"
    
    return False, ""


# ============================================
# SANDBOX FETCH
# ============================================

def sandbox_fetch(params: dict, topics: list[str] = None) -> dict:
    """
    Fetch articles from content_queue (DB) - NOT from RSS directly.
    
    The content_queue should be filled by the Fill Queue cron job.
    This ensures we use high-quality, pre-fetched articles instead of
    falling back to Bing backup.
    
    Args:
        params: Custom parameters
        topics: List of topics to fetch (None = all enabled)
    
    Returns:
        {
            "articles": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    start_time = datetime.now()
    articles = []
    exclusions = []
    stats = {
        "topics_requested": 0,
        "topics_fetched": 0,
        "queue_articles": 0,
        "total_articles": 0,
        "source": "content_queue"
    }
    
    try:
        # Determine which topics to fetch
        topics_enabled = params.get("topics_enabled", DEFAULT_PARAMS["topics_enabled"])
        
        if topics:
            # Use provided list, but filter by enabled
            fetch_topics = [t for t in topics if topics_enabled.get(t, False)]
        else:
            # All enabled topics
            fetch_topics = [t for t, enabled in topics_enabled.items() if enabled]
        
        stats["topics_requested"] = len(fetch_topics)
        
        # ========== READ FROM CONTENT_QUEUE ==========
        # Get articles from the last N days
        content_queue_days = params.get("content_queue_days", 3)
        cutoff_date = (datetime.now() - timedelta(days=content_queue_days)).isoformat()
        
        # Query content_queue for pending articles
        result = supabase.table("content_queue") \
            .select("*") \
            .eq("status", "pending") \
            .gte("created_at", cutoff_date) \
            .execute()
        
        queue_articles = result.data or []
        log.info(f"📦 Found {len(queue_articles)} articles in content_queue")
        
        # Track articles per topic
        articles_by_topic = {t: [] for t in fetch_topics}
        noise_count = 0
        
        for art in queue_articles:
            title = art.get("title", "")
            url = art.get("url", "")
            description = art.get("description", "")
            topic = art.get("keyword", art.get("topic", "general")).lower()
            
            # ========== NOISE FILTER ==========
            is_noise, noise_reason = is_noise_article(title, url, description)
            if is_noise:
                noise_count += 1
                exclusions.append({
                    "type": "noise_filtered",
                    "title": title[:50],
                    "url": url[:80],
                    "reason": noise_reason
                })
                continue
            
            # "general" articles are from generalist sources - they should be included
            # and will be assigned to clusters by embedding similarity
            is_general = (topic == "general")

            # Skip if topic not in our fetch list (but always allow "general")
            if not is_general and topic not in fetch_topics:
                exclusions.append({
                    "type": "topic_not_enabled",
                    "title": title[:50],
                    "topic": topic,
                    "reason": f"Topic '{topic}' not in enabled topics"
                })
                continue

            article = {
                "id": art.get("id"),
                "url": url,
                "title": title,
                "source_type": art.get("source_type", "queue"),
                "source_name": art.get("source_name", art.get("source", "Unknown")),
                "source_country": art.get("source_country", "FR"),
                "topic": topic,  # Keep original topic for reference
                "keyword": topic,
                "description": description,
                "content": art.get("processed_content", art.get("content", "")),
                "published": art.get("published_at", art.get("created_at", "")),
                "fetched_at": art.get("created_at", datetime.now().isoformat()),
                "source_score": art.get("source_score", 50),
                "is_general_source": is_general  # Flag for clustering
            }
            articles.append(article)

            # Track by topic (general articles tracked separately)
            if is_general:
                if "general" not in articles_by_topic:
                    articles_by_topic["general"] = []
                articles_by_topic["general"].append(article)
            else:
                articles_by_topic[topic].append(article)
            stats["queue_articles"] += 1
        
        # Count topics that got articles
        stats["topics_fetched"] = sum(1 for t in fetch_topics if articles_by_topic.get(t))
        stats["total_articles"] = len(articles)
        stats["noise_filtered"] = noise_count
        stats["general_sources"] = len(articles_by_topic.get("general", []))
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()

        if noise_count > 0:
            log.info(f"🗑️ Filtered {noise_count} noise articles (non-article pages)")

        general_count = stats["general_sources"]
        if general_count > 0:
            log.info(f"📰 Including {general_count} articles from generalist sources (will cluster by similarity)")

        # Add per-topic stats
        stats["by_topic"] = {
            topic: len(arts) for topic, arts in articles_by_topic.items()
        }
        
        # Warn if queue is empty
        if len(articles) == 0:
            log.warning("⚠️ content_queue is empty! Run 'Fill Queue' first.")
            exclusions.append({
                "type": "empty_queue",
                "reason": "No articles in content_queue. Click 'Fill Queue' button to fetch articles from RSS sources."
            })
        
    except Exception as e:
        log.error("Sandbox fetch error", error=str(e))
        exclusions.append({
            "type": "fatal_error",
            "reason": str(e)
        })
    
    return {
        "articles": articles,
        "exclusions": exclusions,
        "stats": stats
    }


# ============================================
# TOPIC DESCRIPTIONS FOR INFERENCE (Option B)
# ============================================

# These descriptions are used to generate embeddings for topic inference
# when a cluster only contains "general" source articles
TOPIC_DESCRIPTIONS = {
    "ia": "Intelligence artificielle, machine learning, deep learning, LLM, ChatGPT, GPT-4, Claude, neural networks, AI models, artificial intelligence, OpenAI, Anthropic, Google AI, Microsoft AI, AI startups, generative AI, computer vision, NLP",
    "cyber": "Cybersécurité, hacking, cyberattaques, ransomware, malware, data breach, phishing, security vulnerabilities, zero-day, encryption, privacy, CISO, SOC, penetration testing, threat intelligence, cybercrime",
    "health": "Santé, médecine, biotech, pharmaceutique, clinical trials, FDA approval, drug discovery, healthcare, medical devices, hospitals, epidemiology, cancer research, vaccines, gene therapy, CRISPR, medical AI",
    "deep_tech": "Deep tech, quantum computing, semiconductors, chips, nanotechnology, advanced materials, robotics, fusion energy, space tech, hard science, R&D, patents, scientific breakthroughs, physics, chemistry",
    "space": "Espace, astronomie, satellites, SpaceX, NASA, ESA, rockets, Mars, Moon, space exploration, orbital, astronauts, telescope, cosmic, universe, asteroid, launch",
    "energy": "Énergie, climat, renewable energy, solar, wind, nuclear, oil, gas, electricity, grid, batteries, EV, electric vehicles, carbon, emissions, sustainability, clean energy, fossil fuels",
    "crypto": "Crypto, Bitcoin, Ethereum, blockchain, DeFi, NFT, Web3, cryptocurrency, tokens, mining, exchanges, Binance, Coinbase, stablecoins, smart contracts, decentralized",
    "macro": "Macroéconomie, finance, markets, stocks, bonds, interest rates, inflation, GDP, central banks, Federal Reserve, ECB, economy, recession, growth, unemployment, fiscal policy, monetary policy",
    "deals": "M&A, venture capital, startups, funding, IPO, acquisitions, mergers, private equity, Series A, Series B, unicorn, valuation, investment, fundraising, exit, portfolio",
    "asia": "Asie, Chine, Japan, Korea, India, Southeast Asia, geopolitics, trade, Belt and Road, ASEAN, Pacific, Taiwan, Hong Kong, Singapore, Vietnam, Indonesia, Xi Jinping",
    "regulation": "Régulation, law, legislation, compliance, antitrust, GDPR, EU regulation, FTC, SEC, government policy, legal, courts, lawsuits, enforcement, regulatory framework",
    "resources": "Ressources naturelles, mining, commodities, oil, gas, metals, rare earth, agriculture, water, land, forests, minerals, extraction, supply chain, raw materials",
    "info": "Information, media, journalism, news, press, broadcasting, social media, content, misinformation, fact-checking, editorial, publishing, newspapers, digital media",
    "attention": "Entertainment, media, streaming, Netflix, gaming, movies, music, celebrities, culture, viral, trends, TikTok, YouTube, influencers, content creators",
    "persuasion": "Marketing, advertising, branding, PR, communications, consumer behavior, lifestyle, trends, fashion, luxury, retail, e-commerce, customer experience"
}

# Cache for topic embeddings (computed once)
_topic_embeddings_cache = {}


def get_topic_embeddings() -> dict:
    """
    Get or compute embeddings for all topic descriptions.
    Results are cached for efficiency.
    """
    global _topic_embeddings_cache

    if _topic_embeddings_cache:
        return _topic_embeddings_cache

    log.info("🔤 Computing topic embeddings for inference...")

    topics = list(TOPIC_DESCRIPTIONS.keys())
    descriptions = [TOPIC_DESCRIPTIONS[t] for t in topics]

    embeddings = get_embeddings_batch(descriptions)

    _topic_embeddings_cache = {
        topic: embedding
        for topic, embedding in zip(topics, embeddings)
    }

    log.info(f"✅ Computed {len(_topic_embeddings_cache)} topic embeddings")
    return _topic_embeddings_cache


def infer_topic_from_embeddings(cluster_embeddings: list, topic_embeddings: dict) -> tuple[str, float]:
    """
    Infer the best matching topic for a cluster based on embedding similarity.

    Args:
        cluster_embeddings: List of embeddings for articles in the cluster
        topic_embeddings: Dict of {topic: embedding} for all topics

    Returns:
        (best_topic, similarity_score)
    """
    import numpy as np
    from sklearn.preprocessing import normalize

    # Compute cluster centroid (mean of all article embeddings)
    cluster_array = np.array(cluster_embeddings)
    centroid = np.mean(cluster_array, axis=0)
    centroid_normalized = normalize([centroid])[0]

    # Compare with each topic embedding
    best_topic = None
    best_similarity = -1

    for topic, topic_emb in topic_embeddings.items():
        topic_normalized = normalize([topic_emb])[0]
        similarity = float(np.dot(centroid_normalized, topic_normalized))

        if similarity > best_similarity:
            best_similarity = similarity
            best_topic = topic

    return best_topic, best_similarity


def validate_article_topic_match(article_embedding: list, topic_embedding: list, threshold: float = 0.35) -> tuple[bool, float]:
    """
    Check if an article's embedding matches a topic embedding.

    Args:
        article_embedding: The article's embedding vector
        topic_embedding: The topic's embedding vector
        threshold: Minimum similarity to consider a match

    Returns:
        (is_match, similarity_score)
    """
    import numpy as np
    from sklearn.preprocessing import normalize

    art_norm = normalize([article_embedding])[0]
    topic_norm = normalize([topic_embedding])[0]
    similarity = float(np.dot(art_norm, topic_norm))

    return similarity >= threshold, similarity


# ============================================
# SANDBOX CLUSTER
# ============================================

def sandbox_cluster(articles: list[dict], params: dict) -> dict:
    """
    Cluster articles using OpenAI embeddings + HAC (Hierarchical Agglomerative Clustering).

    V20: Replaced DBSCAN with HAC to avoid chain-linking problem.
    HAC provides better control with distance threshold and works well with small volumes.

    Args:
        articles: List of articles from fetch step
        params: Custom parameters

    Returns:
        {
            "clusters": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import pdist
    from sklearn.preprocessing import normalize
    import numpy as np

    start_time = datetime.now()
    clusters = []
    exclusions = []
    stats = {
        "input_articles": len(articles),
        "clusters_formed": 0,
        "articles_clustered": 0,
        "articles_excluded": 0,
        "embedding_model": EMBEDDING_MODEL,
        "method": "OpenAI embeddings + HAC (Hierarchical Agglomerative Clustering)"
    }

    min_cluster_size = params.get("min_cluster_size", 2)
    distance_threshold = params.get("hac_distance_threshold", 0.45)

    try:
        if len(articles) < min_cluster_size:
            log.warning(f"⚠️ Too few articles ({len(articles)}) for clustering")
            for art in articles:
                exclusions.append({
                    "type": "insufficient_articles",
                    "article": art.get("title", "")[:50],
                    "reason": f"Only {len(articles)} article(s), need at least {min_cluster_size}"
                })
            stats["articles_excluded"] = len(articles)
            stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
            return {"clusters": [], "exclusions": exclusions, "stats": stats}

        # ========== STEP 1: EMBED ARTICLES ==========
        log.info(f"📊 Embedding {len(articles)} articles with OpenAI...")

        # Build text for embedding: description + content (NO title, NO source name)
        texts = []
        for article in articles:
            description = article.get("description") or ""
            content = article.get("content") or article.get("processed_content") or ""
            text = f"{description} {content}".strip()[:1000]
            if not text:
                text = article.get("title") or "No content"
            texts.append(text)

        embeddings = get_embeddings_batch(texts)

        # Attach embeddings to articles
        for article, embedding in zip(articles, embeddings):
            article["embedding"] = embedding

        stats["embeddings_generated"] = len(embeddings)
        log.info(f"✅ Generated {len(embeddings)} embeddings")

        # ========== STEP 2: COMPUTE DISTANCE MATRIX ==========
        embeddings_array = np.array(embeddings)
        embeddings_normalized = normalize(embeddings_array)

        # Compute pairwise cosine distances
        # cosine_distance = 1 - cosine_similarity
        distances = pdist(embeddings_normalized, metric='cosine')

        # ========== DIAGNOSTIC: Similarity distribution ==========
        n_articles = len(embeddings_normalized)
        similarities = 1 - distances  # Convert back to similarities for logging

        log.info(f"📊 SIMILARITY DISTRIBUTION ({len(similarities)} pairs):")
        log.info(f"   Min: {similarities.min():.3f}")
        log.info(f"   Max: {similarities.max():.3f}")
        log.info(f"   Mean: {similarities.mean():.3f}")
        log.info(f"   Median: {np.median(similarities):.3f}")
        log.info(f"   Std: {similarities.std():.3f}")

        # Count pairs above different thresholds
        thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        for thresh in thresholds:
            count = np.sum(similarities >= thresh)
            pct = 100 * count / len(similarities)
            log.info(f"   Pairs with similarity >= {thresh}: {count} ({pct:.1f}%)")

        # Store in stats for frontend display
        stats["similarity_distribution"] = {
            "min": round(float(similarities.min()), 3),
            "max": round(float(similarities.max()), 3),
            "mean": round(float(similarities.mean()), 3),
            "median": round(float(np.median(similarities)), 3),
            "std": round(float(similarities.std()), 3),
            "pairs_above_0.5": int(np.sum(similarities >= 0.5)),
            "pairs_above_0.6": int(np.sum(similarities >= 0.6)),
            "pairs_above_0.7": int(np.sum(similarities >= 0.7)),
            "total_pairs": len(similarities)
        }

        # Find top similar pairs for logging
        from scipy.spatial.distance import squareform
        sim_matrix = squareform(similarities)
        top_pairs = []
        for i in range(n_articles):
            for j in range(i + 1, n_articles):
                sim = sim_matrix[i, j]
                if sim > 0.5:
                    top_pairs.append({
                        "similarity": round(sim, 3),
                        "article_1": articles[i].get("title", "")[:50],
                        "article_2": articles[j].get("title", "")[:50]
                    })
        top_pairs.sort(key=lambda x: x["similarity"], reverse=True)
        stats["top_similar_pairs"] = top_pairs[:10]

        if top_pairs:
            log.info(f"🔝 TOP {min(5, len(top_pairs))} SIMILAR PAIRS:")
            for pair in top_pairs[:5]:
                log.info(f"   {pair['similarity']}: '{pair['article_1']}' <-> '{pair['article_2']}'")

        # ========== STEP 3: HAC CLUSTERING ==========
        log.info(f"🔬 Clustering with HAC (distance_threshold={distance_threshold}, min_size={min_cluster_size})...")

        # Hierarchical clustering with average linkage (less sensitive to outliers)
        Z = linkage(distances, method='average')

        # Cut the dendrogram at the distance threshold
        # distance_threshold=0.45 means cosine_similarity > 0.55
        labels = fcluster(Z, t=distance_threshold, criterion='distance')

        # Labels are 1-indexed, convert to 0-indexed
        labels = labels - 1

        stats["hac_distance_threshold"] = distance_threshold
        stats["hac_linkage_method"] = "average"

        # ========== STEP 4: GROUP BY CLUSTER ==========
        cluster_groups = {}

        for idx, label in enumerate(labels):
            if label not in cluster_groups:
                cluster_groups[label] = []
            cluster_groups[label].append(articles[idx])

        # Filter clusters by minimum size and collect singletons
        valid_cluster_groups = {}
        singleton_articles = []

        for label, cluster_articles in cluster_groups.items():
            if len(cluster_articles) >= min_cluster_size:
                valid_cluster_groups[label] = cluster_articles
            else:
                singleton_articles.extend(cluster_articles)

        log.info(f"📊 HAC produced {len(cluster_groups)} raw clusters, {len(valid_cluster_groups)} valid (>= {min_cluster_size} articles)")

        # ========== STEP 5: BUILD CLUSTER OBJECTS WITH CONTENT-BASED TOPIC ==========
        # Get topic embeddings for inference (cached)
        topic_embeddings = get_topic_embeddings()

        # Track stats for new validations
        stats["clusters_rejected_low_coherence"] = 0
        stats["articles_removed_topic_mismatch"] = 0

        for label, cluster_articles in valid_cluster_groups.items():
            # ========== CORRECTION 2: Check coherence FIRST ==========
            # Compute cluster coherence (average pairwise similarity within cluster)
            if len(cluster_articles) > 1:
                cluster_embs = np.array([art["embedding"] for art in cluster_articles])
                cluster_embs_norm = normalize(cluster_embs)
                cluster_sims = []
                for i in range(len(cluster_embs_norm)):
                    for j in range(i + 1, len(cluster_embs_norm)):
                        cluster_sims.append(float(np.dot(cluster_embs_norm[i], cluster_embs_norm[j])))
                coherence = np.mean(cluster_sims) if cluster_sims else 1.0
            else:
                coherence = 1.0

            # Reject cluster if coherence is too low (articles are too different)
            MIN_COHERENCE = 0.55
            if coherence < MIN_COHERENCE:
                log.warning(f"⚠️ Rejecting cluster {label}: coherence {coherence:.3f} < {MIN_COHERENCE}")
                stats["clusters_rejected_low_coherence"] += 1
                for art in cluster_articles:
                    exclusions.append({
                        "type": "low_coherence_cluster",
                        "article": art.get("title", "")[:50],
                        "topic": art.get("topic", "unknown"),
                        "reason": f"Cluster coherence {coherence:.3f} < {MIN_COHERENCE} threshold"
                    })
                    stats["articles_excluded"] += 1
                continue

            # ========== CORRECTION 1: ALWAYS use content-based topic inference ==========
            # Don't rely on source topic - use embedding similarity to topic descriptions
            cluster_embeddings = [art["embedding"] for art in cluster_articles]
            inferred_topic, topic_similarity = infer_topic_from_embeddings(
                cluster_embeddings, topic_embeddings
            )

            # Log the inference with source topics for comparison
            source_topics = [art.get("topic", "unknown") for art in cluster_articles]
            source_topic_counts = {}
            for t in source_topics:
                if t != "general":
                    source_topic_counts[t] = source_topic_counts.get(t, 0) + 1

            if source_topic_counts:
                dominant_source_topic = max(source_topic_counts, key=source_topic_counts.get)
                if dominant_source_topic != inferred_topic:
                    log.info(f"🔄 Topic override: source='{dominant_source_topic}' → content='{inferred_topic}' (sim: {topic_similarity:.3f})")

            log.info(f"🎯 Cluster {label}: topic='{inferred_topic}' (similarity: {topic_similarity:.3f}, coherence: {coherence:.3f})")

            # ========== CORRECTION 3: Validate each article matches the inferred topic ==========
            validated_articles = []
            topic_embedding = topic_embeddings[inferred_topic]

            for art in cluster_articles:
                is_match, art_topic_sim = validate_article_topic_match(
                    art["embedding"], topic_embedding, threshold=0.30
                )

                if is_match:
                    validated_articles.append(art)
                else:
                    log.debug(f"🚫 Article removed from cluster: '{art.get('title', '')[:40]}' (topic sim: {art_topic_sim:.3f})")
                    exclusions.append({
                        "type": "topic_mismatch",
                        "article": art.get("title", "")[:50],
                        "inferred_topic": inferred_topic,
                        "article_topic_similarity": round(art_topic_sim, 3),
                        "reason": f"Article doesn't match cluster topic '{inferred_topic}' (sim: {art_topic_sim:.3f} < 0.30)"
                    })
                    stats["articles_removed_topic_mismatch"] += 1
                    stats["articles_excluded"] += 1

            # Skip cluster if too few articles remain after validation
            if len(validated_articles) < min_cluster_size:
                log.warning(f"⚠️ Cluster {label} dropped: only {len(validated_articles)} articles after validation")
                for art in validated_articles:
                    exclusions.append({
                        "type": "cluster_too_small_after_validation",
                        "article": art.get("title", "")[:50],
                        "topic": inferred_topic,
                        "reason": f"Cluster shrunk to {len(validated_articles)} articles after topic validation"
                    })
                    stats["articles_excluded"] += 1
                continue

            # Get unique sources
            sources = list(set(a.get("source_name", "Unknown") for a in validated_articles))

            clusters.append({
                "topic": inferred_topic,
                "cluster_id": f"cluster_{label}",
                "size": len(validated_articles),
                "articles": validated_articles,
                "representative_title": validated_articles[0].get("title", ""),
                "sources": sources,
                "source_diversity": len(sources),
                "coherence": round(coherence, 3),
                "topic_confidence": round(topic_similarity, 3)
            })
            stats["clusters_formed"] += 1
            stats["articles_clustered"] += len(validated_articles)

        # Handle singleton/excluded articles
        for art in singleton_articles:
            exclusions.append({
                "type": "cluster_too_small",
                "article": art.get("title", "")[:50],
                "topic": art.get("topic", "unknown"),
                "reason": f"Cluster had fewer than {min_cluster_size} articles"
            })
            stats["articles_excluded"] += 1

        # Sort clusters by size (largest first)
        clusters.sort(key=lambda c: c["size"], reverse=True)

        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        stats["singleton_articles"] = len(singleton_articles)

        log.info(f"✅ HAC Clustering complete: {len(clusters)} clusters, {len(singleton_articles)} singletons excluded")

    except Exception as e:
        log.error("Sandbox cluster error", error=str(e))
        import traceback
        traceback.print_exc()
        exclusions.append({
            "type": "fatal_error",
            "reason": str(e)
        })

    return {
        "clusters": clusters,
        "exclusions": exclusions,
        "stats": stats
    }


# ============================================
# SANDBOX SELECT
# ============================================

def sandbox_select(clusters: list[dict], articles: list[dict], params: dict, format_type: str = "flash") -> dict:
    """
    Select content for podcast in sandbox mode.
    
    Args:
        clusters: List of clusters from clustering step
        articles: Original articles (for fallback if no clusters)
        params: Custom parameters
        format_type: "flash" or "digest"
    
    Returns:
        {
            "segments": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    start_time = datetime.now()
    segments = []
    exclusions = []
    
    # Get format-specific params
    if format_type == "flash":
        target_segments = params.get("flash_segment_count", 4)
        duration_min = params.get("flash_duration_min", 45)
        duration_max = params.get("flash_duration_max", 60)
    else:
        target_segments = params.get("digest_segment_count", 8)
        duration_min = params.get("digest_duration_min", 90)
        duration_max = params.get("digest_duration_max", 120)
    
    min_cluster_size = params.get("min_cluster_size", 3)
    min_articles_fallback = params.get("min_articles_fallback", 5)
    
    stats = {
        "format": format_type,
        "target_segments": target_segments,
        "input_clusters": len(clusters),
        "segments_created": 0,
        "topics_covered": set()
    }
    
    try:
        # Priority 1: Topics with valid clusters
        topics_with_clusters = {}
        for cluster in clusters:
            topic = cluster.get("topic", "unknown")
            if cluster.get("size", 0) >= min_cluster_size:
                if topic not in topics_with_clusters:
                    topics_with_clusters[topic] = []
                topics_with_clusters[topic].append(cluster)
        
        # Priority 2: Topics with enough articles (fallback)
        articles_by_topic = {}
        for art in articles:
            topic = art.get("topic", "unknown")
            if topic not in articles_by_topic:
                articles_by_topic[topic] = []
            articles_by_topic[topic].append(art)
        
        topics_fallback = {
            topic: arts for topic, arts in articles_by_topic.items()
            if topic not in topics_with_clusters and len(arts) >= min_articles_fallback
        }
        
        # Build segments
        selected_topics = []
        
        # First, add topics with clusters
        for topic, topic_clusters in topics_with_clusters.items():
            if len(segments) >= target_segments:
                break
            
            # Take best cluster (largest)
            best_cluster = max(topic_clusters, key=lambda c: c.get("size", 0))
            
            segments.append({
                "topic": topic,
                "type": "cluster",
                "cluster_size": best_cluster.get("size", 0),
                "articles": best_cluster.get("articles", []),
                "representative_title": best_cluster.get("representative_title", ""),
                "duration_target": (duration_min + duration_max) // 2
            })
            stats["segments_created"] += 1
            stats["topics_covered"].add(topic)
            selected_topics.append(topic)
        
        # Then, add fallback topics
        for topic, arts in topics_fallback.items():
            if len(segments) >= target_segments:
                break
            
            if topic in selected_topics:
                continue
            
            segments.append({
                "topic": topic,
                "type": "fallback",
                "cluster_size": 0,
                "articles": arts[:5],  # Max 5 articles for fallback
                "representative_title": arts[0].get("title", "") if arts else "",
                "duration_target": (duration_min + duration_max) // 2
            })
            stats["segments_created"] += 1
            stats["topics_covered"].add(topic)
            selected_topics.append(topic)
        
        # Record exclusions
        for topic, topic_clusters in topics_with_clusters.items():
            if topic not in selected_topics:
                for cluster in topic_clusters:
                    exclusions.append({
                        "type": "segment_limit_reached",
                        "topic": topic,
                        "cluster_size": cluster.get("size", 0),
                        "reason": f"Already have {target_segments} segments"
                    })
        
        for topic, arts in articles_by_topic.items():
            if topic not in selected_topics and topic not in topics_with_clusters:
                if len(arts) < min_articles_fallback:
                    exclusions.append({
                        "type": "insufficient_articles",
                        "topic": topic,
                        "article_count": len(arts),
                        "reason": f"Has {len(arts)} articles, need {min_articles_fallback} for fallback"
                    })
        
        stats["topics_covered"] = list(stats["topics_covered"])
        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        
    except Exception as e:
        log.error("Sandbox select error", error=str(e))
        exclusions.append({
            "type": "fatal_error",
            "reason": str(e)
        })
    
    return {
        "segments": segments,
        "exclusions": exclusions,
        "stats": stats
    }


# ============================================
# NEW ARCHITECTURE: Fresh + Archive
# ============================================

def fetch_fresh_articles(hours_back: int = 48, topics: list[str] = None) -> list[dict]:
    """
    Fetch fresh articles from the new 'articles' table.

    This is the NEW architecture replacement for content_queue.
    Articles are fetched by article_fetcher.py cron job.

    Args:
        hours_back: How many hours to look back (default: 48)
        topics: Optional list of topics to filter

    Returns:
        List of articles with embeddings
    """
    from datetime import datetime, timezone, timedelta

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        query = supabase.table("articles") \
            .select("id, url, title, description, content, embedding, source_name, source_url, topic, published_at, fetched_at") \
            .gte("fetched_at", cutoff.isoformat()) \
            .not_.is_("embedding", "null") \
            .order("fetched_at", desc=True)

        if topics:
            query = query.in_("topic", topics)

        result = query.execute()
        articles = result.data or []

        log.info(f"📰 Fetched {len(articles)} fresh articles from new architecture (last {hours_back}h)")

        # Log topic distribution
        topic_counts = {}
        for a in articles:
            t = a.get("topic", "unknown")
            topic_counts[t] = topic_counts.get(t, 0) + 1
        if topic_counts:
            log.info(f"📊 Topics: {dict(sorted(topic_counts.items(), key=lambda x: -x[1]))}")

        return articles

    except Exception as e:
        log.error(f"❌ Failed to fetch fresh articles: {e}")
        return []


def enrich_cluster_with_archive(
    cluster: dict,
    max_archive_articles: int = 2,
    min_similarity: float = 0.7,
    max_age_days: int = 90
) -> dict:
    """
    Enrich a cluster with relevant archive articles.

    Finds archive articles (> 48h old) that are similar to the cluster's centroid.

    Args:
        cluster: Cluster dict with articles and embeddings
        max_archive_articles: Max archive articles to add
        min_similarity: Minimum cosine similarity threshold
        max_age_days: Max age of archive articles in days

    Returns:
        Enriched cluster with archive_articles added
    """
    import numpy as np
    from sklearn.preprocessing import normalize

    try:
        articles = cluster.get("articles", [])
        if not articles:
            return cluster

        # Compute cluster centroid
        embeddings = [a.get("embedding") for a in articles if a.get("embedding")]
        if not embeddings:
            return cluster

        embeddings_array = np.array(embeddings)
        centroid = np.mean(embeddings_array, axis=0).tolist()

        # Get article URLs to exclude
        exclude_urls = [a.get("url") for a in articles if a.get("url")]

        # Search archive using the Supabase function
        try:
            result = supabase.rpc("find_archive_context", {
                "cluster_centroid": centroid,
                "exclude_urls": exclude_urls,
                "max_results": max_archive_articles,
                "min_similarity": min_similarity,
                "max_age_days": max_age_days
            }).execute()

            archive_articles = result.data or []

            if archive_articles:
                log.info(f"🗄️ Found {len(archive_articles)} archive articles for cluster '{cluster.get('topic')}'")
                for a in archive_articles:
                    log.debug(f"   - [{a.get('topic')}] {a.get('title', '')[:50]} (sim: {a.get('similarity', 0):.3f})")

            # Add archive articles to cluster
            cluster["archive_articles"] = archive_articles
            cluster["archive_count"] = len(archive_articles)

        except Exception as e:
            # Function might not exist yet
            log.warning(f"Archive search failed (migration not applied?): {e}")
            cluster["archive_articles"] = []
            cluster["archive_count"] = 0

    except Exception as e:
        log.error(f"❌ Archive enrichment failed: {e}")
        cluster["archive_articles"] = []
        cluster["archive_count"] = 0

    return cluster


def check_cluster_already_used(cluster: dict, days_back: int = 7) -> bool:
    """
    Check if a cluster was already used recently.

    Prevents creating the same segment as yesterday.

    Args:
        cluster: Cluster dict with articles
        days_back: How far back to check

    Returns:
        True if cluster was already used
    """
    try:
        articles = cluster.get("articles", [])
        if not articles:
            return False

        article_urls = [a.get("url") for a in articles if a.get("url")]
        if not article_urls:
            return False

        result = supabase.rpc("is_cluster_used", {
            "article_urls_to_check": article_urls,
            "days_back": days_back
        }).execute()

        is_used = result.data or False

        if is_used:
            log.info(f"⚠️ Cluster already used: '{cluster.get('representative_title', '')[:50]}...'")

        return is_used

    except Exception as e:
        # Function might not exist yet
        log.debug(f"Cluster check failed (migration not applied?): {e}")
        return False


def mark_cluster_as_used(cluster: dict) -> str | None:
    """
    Mark a cluster as used after creating a segment.

    Args:
        cluster: Cluster dict with articles

    Returns:
        Cluster ID or None on failure
    """
    try:
        articles = cluster.get("articles", [])
        article_urls = [a.get("url") for a in articles if a.get("url")]

        if not article_urls:
            return None

        result = supabase.rpc("mark_cluster_used", {
            "p_article_urls": article_urls,
            "p_topic": cluster.get("topic", "unknown"),
            "p_representative_title": cluster.get("representative_title", "")[:200]
        }).execute()

        return result.data

    except Exception as e:
        log.debug(f"Mark cluster failed (migration not applied?): {e}")
        return None


def sandbox_fetch_v2(params: dict, topics: list[str] = None) -> dict:
    """
    NEW ARCHITECTURE: Fetch from 'articles' table instead of content_queue.

    This uses articles fetched by the article_fetcher.py cron job.
    Articles have embeddings pre-computed at fetch time.

    Args:
        params: Pipeline parameters
        topics: Optional list of topics to filter

    Returns:
        {
            "articles": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    start_time = datetime.now()
    articles = []
    exclusions = []
    stats = {
        "source": "articles_table",
        "architecture": "fresh_archive_v2"
    }

    try:
        # Get enabled topics from params if not explicitly provided
        if not topics:
            enabled_topics = params.get("topics_enabled", {})
            topics = [t for t, enabled in enabled_topics.items() if enabled]

        hours_back = params.get("fresh_hours", 48)

        # Fetch fresh articles
        raw_articles = fetch_fresh_articles(hours_back=hours_back, topics=topics if topics else None)

        stats["raw_articles_fetched"] = len(raw_articles)
        stats["topics_queried"] = topics if topics else "all"
        stats["hours_back"] = hours_back

        # Convert to expected format (some fields may differ from content_queue)
        for art in raw_articles:
            articles.append({
                "id": art.get("id"),
                "url": art.get("url"),
                "title": art.get("title"),
                "description": art.get("description"),
                "content": art.get("content"),
                "processed_content": art.get("content"),  # Alias
                "embedding": art.get("embedding"),
                "source_name": art.get("source_name"),
                "topic": art.get("topic"),
                "published_at": art.get("published_at"),
                "fetched_at": art.get("fetched_at"),
                "keyword": art.get("topic"),  # Alias for compatibility
            })

        stats["articles_returned"] = len(articles)

        # Topic distribution
        topic_counts = {}
        for a in articles:
            t = a.get("topic", "unknown")
            topic_counts[t] = topic_counts.get(t, 0) + 1
        stats["topic_distribution"] = topic_counts

        stats["duration_seconds"] = (datetime.now() - start_time).total_seconds()

    except Exception as e:
        log.error(f"❌ sandbox_fetch_v2 error: {e}")
        import traceback
        traceback.print_exc()
        exclusions.append({
            "type": "fatal_error",
            "reason": str(e)
        })

    return {
        "articles": articles,
        "exclusions": exclusions,
        "stats": stats
    }


def sandbox_cluster_v2(articles: list[dict], params: dict) -> dict:
    """
    NEW ARCHITECTURE: Cluster with archive enrichment + deduplication.

    Same as sandbox_cluster but:
    1. Enriches clusters with archive articles
    2. Checks for cluster deduplication (avoid same as yesterday)

    Args:
        articles: List of articles (with embeddings from fetch_v2)
        params: Custom parameters

    Returns:
        {
            "clusters": [...],
            "exclusions": [...],
            "stats": {...}
        }
    """
    # First, run the base clustering
    result = sandbox_cluster(articles, params)

    clusters = result.get("clusters", [])
    stats = result.get("stats", {})
    exclusions = result.get("exclusions", [])

    # NEW: Archive enrichment and deduplication
    enriched_clusters = []
    deduplicated_count = 0

    max_archive = params.get("max_archive_articles", 2)
    archive_similarity = params.get("archive_min_similarity", 0.7)
    archive_max_age = params.get("archive_max_age_days", 90)
    check_dedup = params.get("check_cluster_dedup", True)
    dedup_days = params.get("cluster_dedup_days", 7)

    for cluster in clusters:
        # Step 1: Check if cluster was already used
        if check_dedup and check_cluster_already_used(cluster, days_back=dedup_days):
            deduplicated_count += 1
            for art in cluster.get("articles", []):
                exclusions.append({
                    "type": "cluster_already_used",
                    "article": art.get("title", "")[:50],
                    "topic": cluster.get("topic"),
                    "reason": f"This cluster was already used in the last {dedup_days} days"
                })
            continue

        # Step 2: Enrich with archive articles
        enriched = enrich_cluster_with_archive(
            cluster,
            max_archive_articles=max_archive,
            min_similarity=archive_similarity,
            max_age_days=archive_max_age
        )
        enriched_clusters.append(enriched)

    stats["clusters_deduplicated"] = deduplicated_count
    stats["clusters_after_dedup"] = len(enriched_clusters)
    stats["total_archive_articles"] = sum(c.get("archive_count", 0) for c in enriched_clusters)
    stats["archive_enrichment_enabled"] = max_archive > 0
    stats["deduplication_enabled"] = check_dedup

    log.info(f"✅ Clustering V2 complete: {len(enriched_clusters)} clusters ({deduplicated_count} deduplicated), {stats['total_archive_articles']} archive articles added")

    return {
        "clusters": enriched_clusters,
        "exclusions": exclusions,
        "stats": stats
    }


def sandbox_full_pipeline_v2(params: dict, format_type: str = "flash", topics: list[str] = None) -> dict:
    """
    NEW ARCHITECTURE: Full pipeline using fresh articles + archive enrichment.

    This is the V2 pipeline that uses:
    - articles table instead of content_queue
    - Archive enrichment for clusters
    - Cluster deduplication

    Returns:
        {
            "fetch": {...},
            "cluster": {...},
            "select": {...},
            "final_segments": [...],
            "total_duration_seconds": float
        }
    """
    start_time = datetime.now()

    # Step 1: Fetch from new articles table
    fetch_result = sandbox_fetch_v2(params, topics)

    # Step 2: Cluster with archive enrichment + dedup
    cluster_result = sandbox_cluster_v2(fetch_result["articles"], params)

    # Step 3: Select (same as before)
    select_result = sandbox_select(
        cluster_result["clusters"],
        fetch_result["articles"],
        params,
        format_type
    )

    return {
        "fetch": fetch_result,
        "cluster": cluster_result,
        "select": select_result,
        "final_segments": select_result["segments"],
        "total_duration_seconds": (datetime.now() - start_time).total_seconds(),
        "architecture": "fresh_archive_v2"
    }


# ============================================
# FULL PIPELINE (convenience)
# ============================================

def sandbox_full_pipeline(params: dict, format_type: str = "flash", topics: list[str] = None) -> dict:
    """
    Run full pipeline in sandbox mode.
    
    Returns:
        {
            "fetch": {...},
            "cluster": {...},
            "select": {...},
            "final_segments": [...],
            "total_duration_seconds": float
        }
    """
    start_time = datetime.now()
    
    # Step 1: Fetch
    fetch_result = sandbox_fetch(params, topics)
    
    # Step 2: Cluster
    cluster_result = sandbox_cluster(fetch_result["articles"], params)
    
    # Step 3: Select
    select_result = sandbox_select(
        cluster_result["clusters"],
        fetch_result["articles"],
        params,
        format_type
    )
    
    return {
        "fetch": fetch_result,
        "cluster": cluster_result,
        "select": select_result,
        "final_segments": select_result["segments"],
        "total_duration_seconds": (datetime.now() - start_time).total_seconds()
    }
