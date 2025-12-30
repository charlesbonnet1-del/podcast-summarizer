"""
Keernel Cluster Pipeline V14
=============================

Transforms 500+ raw articles into ~15 high-quality topic clusters using:
1. EMBEDDER: OpenAI text-embedding-3-small -> pgvector
2. CLUSTERER: HDBSCAN semantic clustering
3. SELECTOR: Top 15 clusters mapped to user topics
4. SYNTHESIZER: Perplexity enrichment for thesis/antithesis

Daily cron job that runs before podcast generation.
"""

import os
import json
import hashlib
import numpy as np
from datetime import datetime, date, timedelta
from typing import Optional
from collections import defaultdict

import structlog
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client

load_dotenv()
log = structlog.get_logger()

# ============================================
# CONFIGURATION
# ============================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# Clustering parameters
MIN_CLUSTER_SIZE = 3  # Minimum articles to form a cluster
MAX_CLUSTERS = 15     # Maximum clusters to select

# V14.1: MASTER SOURCE OVERRIDE
MASTER_SOURCE_THRESHOLD = 90  # GSheet score > 90 = automatic selection

# V14.2: DISCOVERY SCORE (Originality Bias)
DISCOVERY_BONUS_WEIGHT = 0.15  # 15% weight for originality
DISCOVERY_DISTANCE_THRESHOLD = 0.7  # Min distance from dominant clusters

# V14.3: MATURATION WINDOW
MATURATION_WINDOW_HOURS = 72  # 72h sliding window (was 24h)
MERGE_SIMILARITY_THRESHOLD = 0.85  # Cosine similarity for cluster merge

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_URL else None
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
perplexity_client = None

if PERPLEXITY_API_KEY:
    perplexity_client = OpenAI(
        api_key=PERPLEXITY_API_KEY,
        base_url="https://api.perplexity.ai"
    )

# ============================================
# 16 TOPICS (same as Signal Mixer)
# ============================================

TOPICS = {
    # V1 TECH
    "ia": "Intelligence artificielle, machine learning, LLM, GPT, robotique, hardware IA, autonomie machine",
    "cyber": "Cybersécurité, hacking, ransomware, zero-day, vulnérabilités, protection des données",
    "deep_tech": "Quantum computing, fusion nucléaire, nouveaux matériaux, nanotechnologie, recherche fondamentale",
    
    # V2 SCIENCE
    "health": "Santé, longévité, médecine, biotech, pharmaceutique, anti-âge, génomique",
    "space": "Espace, satellites, lanceurs, SpaceX, NASA, exploration spatiale, économie orbitale",
    "energy": "Énergie, batteries, solaire, nucléaire, transition énergétique, stockage, grid",
    
    # V3 ECONOMICS
    "crypto": "Crypto-monnaies, Bitcoin, Ethereum, blockchain, DeFi, NFT, Web3",
    "macro": "Macroéconomie, inflation, taux d'intérêt, banques centrales, PIB, politique monétaire",
    "deals": "M&A, venture capital, levées de fonds, acquisitions, startups, investissements, bourse, actions, IPO, valorisation, earnings",
    
    # V4 WORLD
    "asia": "Asie, Chine, Japon, Corée, Inde, géopolitique asiatique, tech asiatique",
    "regulation": "Régulation, législation, compliance, antitrust, RGPD, lois tech",
    "resources": "Matières premières, métaux rares, pétrole, gaz, agriculture, supply chain",
    
    # V5 INFLUENCE
    "info": "Désinformation, fake news, guerre de l'information, fact-checking, propagande",
    "attention": "Réseaux sociaux, algorithmes, attention economy, plateformes, TikTok, engagement",
    "persuasion": "Marketing, influence, psychologie, nudge, communication, rhétorique",
}

# Pre-computed topic embeddings (will be populated on first run)
_topic_embeddings_cache: dict = {}


# ============================================
# STEP 1: EMBEDDER
# ============================================

def get_embedding(text: str) -> list[float]:
    """Get embedding for a single text using OpenAI."""
    if not openai_client:
        raise RuntimeError("OpenAI client not initialized")
    
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Get embeddings for multiple texts in batches."""
    if not openai_client:
        raise RuntimeError("OpenAI client not initialized")
    
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        log.info(f"📊 Embedding batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1} ({len(batch)} texts)")
        
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )
        
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
    
    return all_embeddings


def get_topic_embeddings() -> dict[str, np.ndarray]:
    """Get or compute embeddings for all 16 topics."""
    global _topic_embeddings_cache
    
    if _topic_embeddings_cache:
        return _topic_embeddings_cache
    
    log.info("🎯 Computing topic embeddings...")
    
    topic_texts = list(TOPICS.values())
    topic_keys = list(TOPICS.keys())
    
    embeddings = get_embeddings_batch(topic_texts)
    
    _topic_embeddings_cache = {
        key: np.array(emb) for key, emb in zip(topic_keys, embeddings)
    }
    
    log.info(f"✅ Topic embeddings ready: {len(_topic_embeddings_cache)} topics")
    return _topic_embeddings_cache


def embed_articles(articles: list[dict]) -> list[dict]:
    """
    Embed articles and return them with embeddings.
    Uses title + description for richer semantic representation.
    """
    if not articles:
        return []
    
    # Build text for each article
    texts = []
    for article in articles:
        title = article.get("title", "")
        description = article.get("description", article.get("content", ""))[:500]
        text = f"{title}. {description}".strip()
        texts.append(text)
    
    log.info(f"📊 Embedding {len(articles)} articles...")
    embeddings = get_embeddings_batch(texts)
    
    # Attach embeddings to articles
    for article, embedding in zip(articles, embeddings):
        article["embedding"] = embedding
    
    log.info(f"✅ Embedded {len(articles)} articles")
    return articles


# ============================================
# STEP 2: CLUSTERER (DBSCAN - no compilation needed)
# ============================================

def cluster_articles(articles: list[dict], min_cluster_size: int = MIN_CLUSTER_SIZE) -> dict:
    """
    Cluster articles using DBSCAN based on their embeddings.
    Uses sklearn DBSCAN instead of HDBSCAN (no C compilation required).
    
    Returns:
        dict with cluster_id -> list of article indices
    """
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import normalize
    
    if len(articles) < min_cluster_size:
        log.warning(f"⚠️ Too few articles ({len(articles)}) for clustering")
        return fallback_cluster_by_topic(articles)
    
    # Extract embeddings as numpy array
    embeddings = np.array([a["embedding"] for a in articles])
    
    # Normalize embeddings for cosine similarity
    embeddings_normalized = normalize(embeddings)
    
    log.info(f"🔬 Clustering {len(articles)} articles with DBSCAN...")
    
    # DBSCAN with cosine distance (via normalized euclidean)
    # eps=0.3 means vectors with cosine similarity > 0.7 are neighbors
    clusterer = DBSCAN(
        eps=0.5,  # Distance threshold (lower = tighter clusters)
        min_samples=min_cluster_size,
        metric='euclidean',  # On normalized vectors, euclidean ≈ cosine
        n_jobs=-1  # Use all CPUs
    )
    
    labels = clusterer.fit_predict(embeddings_normalized)
    
    # Group articles by cluster
    clusters = defaultdict(list)
    noise_count = 0
    
    for idx, label in enumerate(labels):
        if label == -1:  # Noise point
            noise_count += 1
            # Check if high-authority source (keep it as singleton)
            source_score = articles[idx].get("source_score", 50)
            if source_score >= 80:
                # Create singleton cluster for high-authority articles
                singleton_label = f"singleton_{idx}"
                clusters[singleton_label].append(idx)
        else:
            clusters[label].append(idx)
    
    log.info(f"✅ Clustering complete: {len(clusters)} clusters, {noise_count} noise points")
    
    # Log cluster sizes
    if clusters:
        sizes = [len(indices) for indices in clusters.values()]
        log.info(f"📊 Cluster sizes: min={min(sizes)}, max={max(sizes)}, avg={np.mean(sizes):.1f}")
    
    return dict(clusters)


def fallback_cluster_by_topic(articles: list[dict]) -> dict:
    """Fallback clustering by topic when HDBSCAN is unavailable."""
    log.warning("⚠️ Using fallback topic-based clustering")
    
    clusters = defaultdict(list)
    for idx, article in enumerate(articles):
        topic = article.get("keyword", article.get("topic", "general"))
        clusters[f"topic_{topic}"].append(idx)
    
    return dict(clusters)


# ============================================
# STEP 3: SELECTOR (Top 15 + Topic Mapping)
# ============================================

def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


# ============================================
# V14.1: MASTER SOURCE OVERRIDE
# ============================================

def identify_master_source_clusters(articles: list[dict], topic_embeddings: dict) -> list[dict]:
    """
    V14.1: Identify articles from MASTER sources (score > 90) and create
    priority clusters for them, even if they're alone (cluster size = 1).
    
    These bypass the normal cluster size requirement.
    """
    master_clusters = []
    
    for idx, article in enumerate(articles):
        source_score = article.get("source_score", 0)
        
        if source_score >= MASTER_SOURCE_THRESHOLD:
            # This is a master source - create a priority cluster
            embedding = article.get("embedding")
            if embedding is None:
                continue
            
            embedding_arr = np.array(embedding)
            
            # Find best matching topic
            best_topic = None
            best_similarity = -1
            
            for topic, topic_emb in topic_embeddings.items():
                similarity = cosine_similarity(embedding_arr, topic_emb)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_topic = topic
            
            master_clusters.append({
                "cluster_id": f"master_{idx}",
                "indices": [idx],
                "article_count": 1,
                "centroid": embedding_arr,
                "topic": best_topic,
                "topic_similarity": best_similarity,
                "density": source_score / 100,  # High density from authority
                "theme": article.get("title", "Unknown")[:100],
                "representative": article,
                "articles": [article],
                "is_master_source": True,
                "source_score": source_score
            })
            
            log.info(f"🌟 MASTER SOURCE: {article.get('source_name')} (score={source_score}) → {best_topic}")
    
    return master_clusters


# ============================================
# V14.2: DISCOVERY SCORE (Originality Bias)
# ============================================

def calculate_discovery_score(
    cluster_centroid: np.ndarray,
    dominant_centroids: list[np.ndarray],
    topic_embeddings: dict
) -> float:
    """
    V14.2: Calculate discovery score - bonus for originality.
    
    High score = article is DIFFERENT from dominant clusters but still
    within our 15 topics. This surfaces "weak signals" - isolated expert
    analysis that hasn't gone viral yet.
    
    Returns:
        Score 0-1 where 1 = highly original
    """
    if not dominant_centroids:
        return 0.5  # Neutral if no reference
    
    # Calculate average distance from dominant clusters
    distances = []
    for dom_centroid in dominant_centroids:
        similarity = cosine_similarity(cluster_centroid, dom_centroid)
        distance = 1 - similarity  # Convert to distance
        distances.append(distance)
    
    avg_distance = np.mean(distances)
    
    # Check if still within topic space (not just random noise)
    max_topic_similarity = 0
    for topic_emb in topic_embeddings.values():
        sim = cosine_similarity(cluster_centroid, topic_emb)
        max_topic_similarity = max(max_topic_similarity, sim)
    
    # Only give bonus if:
    # 1. Far from dominant clusters (avg_distance > threshold)
    # 2. Still relevant to our topics (max_topic_similarity > 0.3)
    if avg_distance >= DISCOVERY_DISTANCE_THRESHOLD and max_topic_similarity > 0.3:
        # Normalize to 0-1 score
        discovery_score = min(1.0, (avg_distance - 0.5) * 2)
        return discovery_score


# ============================================
# V14.4: TIMELINESS SCORE (Freshness + Specificity)
# ============================================

# Generic/evergreen phrases that indicate non-timely content
GENERIC_PHRASES = [
    # Trend statements (could be published anytime)
    "en pleine expansion", "en pleine croissance", "continue de croître",
    "ne cesse de", "de plus en plus", "est en train de",
    "connaît une forte", "prend de l'ampleur", "gagne du terrain",
    # Vague future predictions
    "va transformer", "pourrait changer", "risque de",
    "devrait connaître", "est appelé à", "promet de",
    # Generic analyses
    "les experts estiment", "selon les analystes", "d'après les spécialistes",
    "il est important de", "il convient de noter",
    # Evergreen topics
    "l'importance de", "les avantages de", "comment fonctionne",
    "qu'est-ce que", "tout savoir sur", "guide complet",
    # English equivalents
    "is growing", "continues to grow", "is expanding",
    "is transforming", "experts say", "analysts predict",
    "the rise of", "the future of", "how to",
]

# Specific/timely indicators
TIMELY_INDICATORS = [
    # Recent time markers
    "aujourd'hui", "hier", "cette semaine", "ce mois",
    "vient de", "vient d'annoncer", "vient de lancer",
    "annonce", "lance", "dévoile", "révèle", "confirme",
    # Specific events
    "a été acquis", "a levé", "a signé", "a conclu",
    "a atteint", "a dépassé", "a battu",
    # Concrete numbers with context
    "millions de dollars", "milliards", "% de croissance",
    # English equivalents
    "today", "yesterday", "this week", "just announced",
    "has acquired", "raised", "launched", "revealed",
]


def calculate_timeliness_score(cluster: dict, articles: list) -> float:
    """
    V14.4: Calculate timeliness score to penalize generic/evergreen topics.
    
    Analyzes:
    1. Publication dates of articles in cluster
    2. Presence of specific vs generic language
    3. Concrete facts vs vague trends
    
    Returns:
        Score 0-1 where 1 = very timely/specific, 0 = generic/evergreen
    """
    from datetime import datetime, timedelta
    
    cluster_indices = cluster.get("article_indices", [])
    if not cluster_indices:
        return 0.5  # Neutral if no articles
    
    cluster_articles = [articles[i] for i in cluster_indices if i < len(articles)]
    if not cluster_articles:
        return 0.5
    
    # Component 1: FRESHNESS (based on publication dates)
    freshness_score = 0.5
    now = datetime.now()
    ages_hours = []
    
    for article in cluster_articles:
        pub_date = article.get("published_at") or article.get("created_at")
        if pub_date:
            try:
                if isinstance(pub_date, str):
                    # Handle ISO format
                    pub_date = pub_date.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(pub_date.split('+')[0])
                else:
                    dt = pub_date
                age_hours = (now - dt).total_seconds() / 3600
                ages_hours.append(age_hours)
            except:
                pass
    
    if ages_hours:
        avg_age_hours = np.mean(ages_hours)
        # Score based on age: <24h = 1.0, 24-48h = 0.8, 48-72h = 0.6, >72h = 0.3
        if avg_age_hours < 24:
            freshness_score = 1.0
        elif avg_age_hours < 48:
            freshness_score = 0.8
        elif avg_age_hours < 72:
            freshness_score = 0.6
        else:
            freshness_score = 0.3
    
    # Component 2: SPECIFICITY (language analysis)
    theme = cluster.get("theme", "")
    representative_title = cluster.get("representative", {}).get("title", "")
    text_to_analyze = f"{theme} {representative_title}".lower()
    
    # Count generic phrases
    generic_count = sum(1 for phrase in GENERIC_PHRASES if phrase in text_to_analyze)
    
    # Count timely indicators
    timely_count = sum(1 for indicator in TIMELY_INDICATORS if indicator in text_to_analyze)
    
    # Calculate specificity score
    if generic_count > 2:
        specificity_score = 0.2  # Very generic
    elif generic_count > 0 and timely_count == 0:
        specificity_score = 0.4  # Somewhat generic
    elif timely_count > 0:
        specificity_score = min(1.0, 0.6 + timely_count * 0.1)  # Timely
    else:
        specificity_score = 0.5  # Neutral
    
    # Component 3: CONCRETENESS (presence of specific facts)
    # Check for numbers, names, specific entities
    import re
    has_numbers = bool(re.search(r'\d+', text_to_analyze))
    has_proper_nouns = bool(re.search(r'[A-Z][a-z]+', theme))  # Capitalized words in theme
    
    concreteness_score = 0.5
    if has_numbers and has_proper_nouns:
        concreteness_score = 0.9
    elif has_numbers or has_proper_nouns:
        concreteness_score = 0.7
    
    # Combine components: freshness 40%, specificity 40%, concreteness 20%
    final_score = (freshness_score * 0.4 + specificity_score * 0.4 + concreteness_score * 0.2)
    
    return final_score
    
    return 0.0


def get_dominant_cluster_centroids(clusters: list[dict], top_n: int = 5) -> list[np.ndarray]:
    """Get centroids of the N largest/densest clusters (the "mainstream")."""
    if not clusters:
        return []
    
    # Sort by article count (density)
    sorted_clusters = sorted(clusters, key=lambda x: x.get("article_count", 0), reverse=True)
    
    centroids = []
    for cluster in sorted_clusters[:top_n]:
        centroid = cluster.get("centroid")
        if centroid is not None:
            centroids.append(np.array(centroid) if not isinstance(centroid, np.ndarray) else centroid)
    
    return centroids


# ============================================
# V14.3: MATURATION & LATE MERGE
# ============================================

def merge_late_arrivals(
    existing_clusters: list[dict],
    new_articles: list[dict],
    similarity_threshold: float = MERGE_SIMILARITY_THRESHOLD
) -> list[dict]:
    """
    V14.3: Merge late-arriving articles into existing clusters.
    
    If a new article has cosine similarity > 0.85 with an existing cluster,
    attach it. If the new article has higher source_score, it becomes
    the representative (enriching raw news with expert analysis).
    """
    if not existing_clusters or not new_articles:
        return existing_clusters
    
    merged_count = 0
    promoted_count = 0
    
    for article in new_articles:
        embedding = article.get("embedding")
        if embedding is None:
            continue
        
        article_emb = np.array(embedding)
        article_score = article.get("source_score", 50)
        
        best_cluster = None
        best_similarity = 0
        
        # Find best matching cluster
        for cluster in existing_clusters:
            centroid = cluster.get("centroid")
            if centroid is None:
                continue
            
            similarity = cosine_similarity(article_emb, centroid)
            
            if similarity > best_similarity and similarity >= similarity_threshold:
                best_similarity = similarity
                best_cluster = cluster
        
        if best_cluster:
            # Merge into cluster
            best_cluster["articles"].append(article)
            best_cluster["article_count"] += 1
            merged_count += 1
            
            # Check for source promotion
            current_rep_score = best_cluster.get("representative", {}).get("source_score", 50)
            
            if article_score > current_rep_score:
                # Promote this article as the new representative
                old_rep = best_cluster["representative"].get("title", "")[:30]
                best_cluster["representative"] = article
                best_cluster["theme"] = article.get("title", "Unknown")[:100]
                best_cluster["source_score"] = article_score
                promoted_count += 1
                
                log.info(f"📈 SOURCE PROMOTION: {article.get('source_name')} (score={article_score}) "
                        f"replaces '{old_rep}...' in cluster")
            
            # Recalculate centroid with new article
            all_embeddings = [np.array(a["embedding"]) for a in best_cluster["articles"] if a.get("embedding")]
            if all_embeddings:
                best_cluster["centroid"] = np.mean(all_embeddings, axis=0)
    
    if merged_count > 0:
        log.info(f"🔄 LATE MERGE: {merged_count} articles merged, {promoted_count} source promotions")
    
    return existing_clusters


def calculate_timeliness_score(cluster: dict, articles: list[dict]) -> float:
    """
    Calculate how "newsworthy" a cluster is vs being generic/evergreen content.
    
    V14.4: Penalizes topics that could be published anytime (e.g., "Asia is growing")
    Rewards topics with specific events, names, dates, numbers.
    
    Returns:
        Score from 0.0 (evergreen/generic) to 1.0 (very timely/specific)
    """
    theme = cluster.get("theme", "")
    cluster_articles = cluster.get("articles", [])
    
    if not theme:
        return 0.5  # Default neutral
    
    theme_lower = theme.lower()
    score = 0.5  # Start at neutral
    
    # === SPECIFICITY SIGNALS (increase score) ===
    
    # Named entities (proper nouns indicate specific news)
    # Check for capital letters in the middle of sentences (names)
    import re
    proper_nouns = re.findall(r'(?<!\. )[A-Z][a-zéèêëàâäîïôöûü]+', theme)
    if len(proper_nouns) >= 2:
        score += 0.15  # Multiple proper nouns = specific story
    elif len(proper_nouns) >= 1:
        score += 0.08
    
    # Numbers and stats (quantified news)
    has_numbers = bool(re.search(r'\d+', theme))
    has_percentage = bool(re.search(r'\d+\s*%', theme))
    has_money = bool(re.search(r'(\$|€|£|¥)\s*\d+|\d+\s*(million|milliard|billion|M\$|B\$|M€|B€)', theme, re.IGNORECASE))
    
    if has_money:
        score += 0.15
    elif has_percentage:
        score += 0.12
    elif has_numbers:
        score += 0.08
    
    # Action verbs indicating events (launches, announces, acquires)
    event_verbs = [
        "lance", "annonce", "acquiert", "rachète", "lève", "signe",
        "dévoile", "présente", "révèle", "confirme", "rejette",
        "launches", "announces", "acquires", "raises", "signs",
        "unveils", "reveals", "confirms", "rejects", "releases"
    ]
    if any(verb in theme_lower for verb in event_verbs):
        score += 0.12
    
    # Date/time references (today, yesterday, this week)
    time_refs = [
        "aujourd'hui", "hier", "cette semaine", "ce mois", "2024", "2025",
        "today", "yesterday", "this week", "this month", "janvier", "février",
        "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre", "january", "february", "Q1", "Q2", "Q3", "Q4"
    ]
    if any(ref in theme_lower for ref in time_refs):
        score += 0.10
    
    # === GENERIC/EVERGREEN SIGNALS (decrease score) ===
    
    # Generic trend words without specifics
    generic_patterns = [
        r"^l'(asie|europe|afrique|amérique)\s+(est|se|va|continue)",
        r"^(la|le|les)\s+\w+\s+(est|sont|va|vont)\s+en\s+(croissance|expansion|hausse|baisse)",
        r"(tendance|trend|avenir|futur|future|évolution|transformation)\s+(de|du|des|of)",
        r"^(comment|how|why|pourquoi)\s+",
        r"^(les|the)\s+\d+\s+(meilleures?|best|top)",
        r"(guide|introduction|comprendre|understand)",
        r"(impact|importance|rôle|role)\s+(de|du|des|of)",
    ]
    
    for pattern in generic_patterns:
        if re.search(pattern, theme_lower):
            score -= 0.20
            break
    
    # Vague superlatives without specifics
    vague_superlatives = [
        "en pleine expansion", "en forte croissance", "en plein essor",
        "de plus en plus", "de moins en moins", "toujours plus",
        "growing rapidly", "expanding fast", "increasingly"
    ]
    if any(phrase in theme_lower for phrase in vague_superlatives):
        score -= 0.15
    
    # Check article freshness (publication dates)
    recent_count = 0
    for article in cluster_articles[:5]:
        pub_date = article.get("published_at") or article.get("created_at")
        if pub_date:
            # If published in last 48h, it's fresher
            try:
                from datetime import datetime, timedelta
                if isinstance(pub_date, str):
                    # Parse ISO date
                    pub_dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                    if datetime.now(pub_dt.tzinfo) - pub_dt < timedelta(hours=48):
                        recent_count += 1
            except:
                pass
    
    if recent_count >= 3:
        score += 0.10  # Multiple very recent articles
    
    # Clamp score to [0, 1]
    score = max(0.0, min(1.0, score))
    
    return score


def select_best_clusters(
    clusters: dict, 
    articles: list[dict],
    user_topic_weights: dict[str, int] = None,
    max_clusters: int = MAX_CLUSTERS
) -> list[dict]:
    """
    Select the best clusters and map them to topics.
    
    V14 Intelligence Layers:
    1. MASTER SOURCE OVERRIDE - Score > 90 bypasses cluster size
    2. DISCOVERY SCORE - Bonus for originality (weak signals)
    3. MATURATION MERGE - Late expert analysis enriches clusters
    
    Args:
        clusters: dict of cluster_id -> article indices
        articles: list of articles with embeddings
        user_topic_weights: dict of topic -> weight (0-100) from Signal Mixer
        max_clusters: maximum number of clusters to return
    
    Returns:
        list of selected cluster dicts with metadata
    """
    if not clusters:
        return []
    
    # Get topic embeddings
    topic_embeddings = get_topic_embeddings()
    
    # Default weights if not provided
    if not user_topic_weights:
        user_topic_weights = {topic: 50 for topic in TOPICS.keys()}
    
    scored_clusters = []
    
    # === V14.1: MASTER SOURCE OVERRIDE ===
    # First, identify and add master source clusters (bypass size requirements)
    master_clusters = identify_master_source_clusters(articles, topic_embeddings)
    for mc in master_clusters:
        # Apply user weight
        user_weight = user_topic_weights.get(mc["topic"], 50) / 100
        mc["score"] = mc["density"] * 0.3 + mc["topic_similarity"] * 0.3 + user_weight * 0.2 + 0.2  # +0.2 master bonus
        scored_clusters.append(mc)
    
    # Track master source article indices to avoid duplicates
    master_indices = set()
    for mc in master_clusters:
        master_indices.update(mc["indices"])
    
    # Process regular clusters
    for cluster_id, indices in clusters.items():
        if not indices:
            continue
        
        # Skip articles already in master clusters
        filtered_indices = [i for i in indices if i not in master_indices]
        if not filtered_indices:
            continue
        
        # Get cluster articles
        cluster_articles = [articles[i] for i in filtered_indices]
        
        # Compute centroid (mean of all embeddings in cluster)
        embeddings = np.array([a["embedding"] for a in cluster_articles if a.get("embedding")])
        if len(embeddings) == 0:
            continue
        centroid = np.mean(embeddings, axis=0)
        
        # Compute density score (size * avg source authority)
        source_scores = [a.get("source_score", 50) for a in cluster_articles]
        density = len(filtered_indices) * np.mean(source_scores) / 100
        
        # Find best matching topic
        best_topic = None
        best_similarity = -1
        
        for topic, topic_emb in topic_embeddings.items():
            similarity = cosine_similarity(centroid, topic_emb)
            # Apply user weight as multiplier
            weighted_similarity = similarity * (user_topic_weights.get(topic, 50) / 50)
            
            if weighted_similarity > best_similarity:
                best_similarity = weighted_similarity
                best_topic = topic
        
        # Find representative article (highest source score, then closest to centroid)
        # V14.3: Prefer higher authority sources as representative
        sorted_articles = sorted(
            zip(filtered_indices, cluster_articles),
            key=lambda x: (x[1].get("source_score", 50), -np.linalg.norm(centroid - np.array(x[1].get("embedding", centroid)))),
            reverse=True
        )
        representative_idx, representative = sorted_articles[0]
        
        # Generate cluster theme from representative article
        cluster_theme = representative.get("title", "Unknown")[:100]
        
        scored_clusters.append({
            "cluster_id": cluster_id,
            "indices": filtered_indices,
            "article_count": len(filtered_indices),
            "centroid": centroid,
            "topic": best_topic,
            "topic_similarity": best_similarity,
            "density": density,
            "theme": cluster_theme,
            "representative": representative,
            "articles": cluster_articles,
            "is_master_source": False,
            "source_score": representative.get("source_score", 50)
        })
    
    # === V14.2: DISCOVERY SCORE ===
    # Calculate discovery bonus for each cluster
    dominant_centroids = get_dominant_cluster_centroids(scored_clusters, top_n=5)
    
    for cluster in scored_clusters:
        if cluster.get("is_master_source"):
            # Master sources already have priority
            cluster["discovery_score"] = 0
        else:
            cluster["discovery_score"] = calculate_discovery_score(
                cluster["centroid"],
                dominant_centroids,
                topic_embeddings
            )
    
    # Calculate final score with all factors
    for cluster in scored_clusters:
        user_weight = user_topic_weights.get(cluster["topic"], 50) / 100
        
        # Base score components
        density_component = cluster["density"] * 0.30  # Reduced from 0.35
        topic_component = cluster["topic_similarity"] * 0.20  # Reduced from 0.25
        user_weight_component = user_weight * 0.20  # Reduced from 0.25
        discovery_component = cluster["discovery_score"] * DISCOVERY_BONUS_WEIGHT
        
        # V14: TIMELINESS SCORE - penalize generic/evergreen topics
        timeliness_score = calculate_timeliness_score(cluster, articles)
        timeliness_component = timeliness_score * 0.15  # 15% weight for freshness
        
        # Master source bonus
        master_bonus = 0.1 if cluster.get("is_master_source") else 0
        
        cluster["score"] = (density_component + topic_component + user_weight_component + 
                           discovery_component + timeliness_component + master_bonus)
        cluster["timeliness_score"] = timeliness_score
        
        # Log discovery finds
        if cluster["discovery_score"] > 0.3:
            log.info(f"🔍 DISCOVERY: {cluster['theme'][:40]}... (discovery={cluster['discovery_score']:.2f})")
        
        # Log low timeliness (potential generic topic)
        if timeliness_score < 0.3:
            log.warning(f"⏰ LOW TIMELINESS: {cluster['theme'][:40]}... (timeliness={timeliness_score:.2f}) - may be generic topic")
    
    scored_clusters.sort(key=lambda x: x["score"], reverse=True)
    
    # Deduplicate by topic (only keep best cluster per topic)
    selected = []
    seen_topics = set()
    
    for cluster in scored_clusters:
        topic = cluster["topic"]
        
        # Allow max 2 clusters per topic if they're very different
        topic_count = sum(1 for s in selected if s["topic"] == topic)
        if topic_count >= 2:
            continue
        
        # If second cluster for same topic, check it's different enough
        if topic_count == 1:
            existing = next(s for s in selected if s["topic"] == topic)
            similarity = cosine_similarity(cluster["centroid"], existing["centroid"])
            if similarity > 0.85:  # Too similar, skip
                continue
        
        selected.append(cluster)
        
        if len(selected) >= max_clusters:
            break
    
    log.info(f"✅ Selected {len(selected)} clusters from {len(scored_clusters)} candidates")
    
    # Log selection with intelligence indicators
    for i, cluster in enumerate(selected):
        indicators = []
        if cluster.get("is_master_source"):
            indicators.append("🌟MASTER")
        if cluster.get("discovery_score", 0) > 0.3:
            indicators.append("🔍DISCOVERY")
        
        indicator_str = " ".join(indicators) if indicators else ""
        log.info(f"   {i+1}. [{cluster['topic']}] {cluster['theme'][:50]}... "
                 f"(articles={cluster['article_count']}, score={cluster['score']:.3f}) {indicator_str}")
    
    return selected


# ============================================
# STEP 4: SYNTHESIZER (Perplexity)
# ============================================

SYNTHESIS_PROMPT = """Tu es un analyste expert. Analyse ces articles sur le même sujet et génère une synthèse structurée pour un podcast audio.

**SUJET**: {theme}

**ARTICLES**:
{articles_text}

**INSTRUCTIONS**:
1. Identifie le FAIT PRINCIPAL (la thèse)
2. Identifie les NUANCES ou CONTRE-ARGUMENTS (l'antithèse)
3. Extrais 2-3 DONNÉES CHIFFRÉES clés
4. Liste les sources à citer

**Réponds UNIQUEMENT en JSON valide** (pas de markdown, pas de ```):
{{
    "theme": "Titre concis du sujet (max 10 mots)",
    "thesis": "Le fait principal ou la tendance majeure (2-3 phrases)",
    "antithesis": "Les nuances, limites ou contre-arguments (2-3 phrases)",
    "key_data": ["Chiffre ou donnée 1", "Chiffre ou donnée 2"],
    "sources": ["Nom source 1", "Nom source 2"],
    "hook": "Une phrase d'accroche percutante pour introduire le sujet"
}}"""


def synthesize_cluster(cluster: dict) -> Optional[dict]:
    """
    Use Perplexity to synthesize a cluster into thesis/antithesis.
    
    Args:
        cluster: Selected cluster with articles
    
    Returns:
        Synthesis dict with theme, thesis, antithesis, key_data, sources
    """
    if not perplexity_client:
        log.warning("⚠️ Perplexity client not available, using fallback synthesis")
        return fallback_synthesis(cluster)
    
    articles = cluster.get("articles", [])
    if not articles:
        return None
    
    # Build articles text (top 5 closest to centroid)
    centroid = cluster.get("centroid")
    if centroid is not None:
        # Sort by distance to centroid
        with_distances = []
        for a in articles:
            dist = np.linalg.norm(centroid - np.array(a["embedding"]))
            with_distances.append((dist, a))
        with_distances.sort(key=lambda x: x[0])
        top_articles = [a for _, a in with_distances[:5]]
    else:
        top_articles = articles[:5]
    
    articles_text = "\n\n".join([
        f"**{a.get('source_name', 'Source')}**: {a.get('title', '')}\n{a.get('description', a.get('content', ''))[:300]}"
        for a in top_articles
    ])
    
    prompt = SYNTHESIS_PROMPT.format(
        theme=cluster.get("theme", "Sujet"),
        articles_text=articles_text
    )
    
    try:
        log.info(f"🔮 Synthesizing cluster: {cluster.get('theme', '')[:50]}...")
        
        response = perplexity_client.chat.completions.create(
            model="sonar",  # or "sonar-pro" for better quality
            messages=[
                {"role": "system", "content": "Tu es un analyste expert. Réponds uniquement en JSON valide."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean potential markdown formatting
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        synthesis = json.loads(content)
        synthesis["cluster_id"] = cluster.get("cluster_id")
        synthesis["topic"] = cluster.get("topic")
        synthesis["article_count"] = cluster.get("article_count")
        synthesis["urls"] = [a.get("url") for a in top_articles if a.get("url")]
        
        log.info(f"✅ Synthesis complete: {synthesis.get('theme', '')[:50]}")
        return synthesis
        
    except json.JSONDecodeError as e:
        log.error(f"❌ Failed to parse Perplexity response as JSON: {e}")
        return fallback_synthesis(cluster)
    except Exception as e:
        log.error(f"❌ Perplexity synthesis failed: {e}")
        return fallback_synthesis(cluster)


def fallback_synthesis(cluster: dict) -> dict:
    """Fallback synthesis when Perplexity is unavailable."""
    articles = cluster.get("articles", [])
    representative = cluster.get("representative", articles[0] if articles else {})
    
    return {
        "theme": cluster.get("theme", "Sujet")[:100],
        "thesis": representative.get("description", representative.get("content", ""))[:300],
        "antithesis": "",
        "key_data": [],
        "sources": list(set(a.get("source_name", "Source") for a in articles[:3])),
        "hook": representative.get("title", ""),
        "cluster_id": cluster.get("cluster_id"),
        "topic": cluster.get("topic"),
        "article_count": cluster.get("article_count", len(articles)),
        "urls": [a.get("url") for a in articles[:3] if a.get("url")]
    }


# ============================================
# STEP 5: STORAGE (Supabase)
# ============================================

def store_embeddings(articles: list[dict], user_id: str = None) -> int:
    """Store article embeddings in Supabase pgvector."""
    if not supabase:
        log.error("❌ Supabase client not initialized")
        return 0
    
    stored = 0
    today = date.today().isoformat()
    
    for article in articles:
        if "embedding" not in article:
            continue
        
        try:
            data = {
                "url": article.get("url"),
                "title": article.get("title"),
                "description": article.get("description", "")[:1000],
                "source_name": article.get("source_name"),
                "source_score": article.get("source_score", 50),
                "embedding": article["embedding"],
                "edition": today,
                "topic": article.get("keyword", article.get("topic"))
            }
            
            if user_id:
                data["user_id"] = user_id
            
            # Upsert by URL
            supabase.table("news_embeddings").upsert(
                data,
                on_conflict="url"
            ).execute()
            
            stored += 1
            
        except Exception as e:
            log.warning(f"⚠️ Failed to store embedding for {article.get('url', 'unknown')}: {e}")
    
    log.info(f"✅ Stored {stored}/{len(articles)} embeddings")
    return stored


def store_clusters(clusters: list[dict], user_id: str = None) -> int:
    """Store synthesized clusters in Supabase."""
    if not supabase:
        log.error("❌ Supabase client not initialized")
        return 0
    
    stored = 0
    today = date.today().isoformat()
    
    for cluster in clusters:
        try:
            # Generate unique ID for cluster
            cluster_hash = hashlib.md5(
                f"{cluster.get('theme', '')}_{today}".encode()
            ).hexdigest()[:16]
            
            data = {
                "cluster_id": cluster_hash,
                "edition": today,
                "topic": cluster.get("topic"),
                "theme": cluster.get("theme", "")[:200],
                "thesis": cluster.get("thesis", ""),
                "antithesis": cluster.get("antithesis", ""),
                "key_data": cluster.get("key_data", []),
                "sources": cluster.get("sources", []),
                "hook": cluster.get("hook", ""),
                "article_count": cluster.get("article_count", 0),
                "urls": cluster.get("urls", []),
                "score": cluster.get("score", 0)
            }
            
            if user_id:
                data["user_id"] = user_id
            
            supabase.table("daily_clusters").upsert(
                data,
                on_conflict="cluster_id,edition"
            ).execute()
            
            stored += 1
            
        except Exception as e:
            log.warning(f"⚠️ Failed to store cluster {cluster.get('theme', 'unknown')}: {e}")
    
    log.info(f"✅ Stored {stored}/{len(clusters)} clusters")
    return stored


def get_daily_clusters(user_id: str = None, edition: str = None) -> list[dict]:
    """Retrieve today's clusters from Supabase."""
    if not supabase:
        return []
    
    if not edition:
        edition = date.today().isoformat()
    
    query = supabase.table("daily_clusters").select("*").eq("edition", edition)
    
    if user_id:
        query = query.eq("user_id", user_id)
    
    result = query.order("score", desc=True).execute()
    
    return result.data if result.data else []


# ============================================
# MAIN PIPELINE
# ============================================

def fetch_raw_articles(user_id: str = None, limit: int = 500, hours_back: int = MATURATION_WINDOW_HOURS) -> list[dict]:
    """
    Fetch raw articles from content_queue for clustering.
    
    V14.3: Extended to 72h maturation window to allow late-arriving expert analysis.
    """
    if not supabase:
        return []
    
    # V14.3: Get articles from last 72 hours (maturation window)
    cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
    
    query = supabase.table("content_queue") \
        .select("id, url, title, source_name, source_type, keyword, source_score, created_at, description") \
        .eq("status", "pending") \
        .gte("created_at", cutoff) \
        .order("created_at", desc=True) \
        .limit(limit)
    
    if user_id:
        query = query.eq("user_id", user_id)
    
    result = query.execute()
    
    articles = result.data if result.data else []
    log.info(f"📥 Fetched {len(articles)} raw articles for clustering (last {hours_back}h)")
    
    return articles


def fetch_master_sources(user_id: str = None) -> list[dict]:
    """
    V14.1: Fetch articles from MASTER sources (GSheet score > 90).
    These bypass cluster size requirements.
    """
    if not supabase:
        return []
    
    cutoff = (datetime.now() - timedelta(hours=MATURATION_WINDOW_HOURS)).isoformat()
    
    # Get articles from high-authority sources
    query = supabase.table("content_queue") \
        .select("id, url, title, source_name, source_type, keyword, source_score, created_at, description") \
        .eq("status", "pending") \
        .gte("source_score", MASTER_SOURCE_THRESHOLD) \
        .gte("created_at", cutoff) \
        .order("source_score", desc=True) \
        .limit(50)
    
    if user_id:
        query = query.eq("user_id", user_id)
    
    result = query.execute()
    
    articles = result.data if result.data else []
    log.info(f"🌟 Found {len(articles)} MASTER source articles (score ≥ {MASTER_SOURCE_THRESHOLD})")
    
    return articles


def run_cluster_pipeline(
    user_id: str = None,
    user_topic_weights: dict[str, int] = None,
    max_clusters: int = MAX_CLUSTERS,
    store_results: bool = True
) -> list[dict]:
    """
    Run the complete clustering pipeline with V14 intelligence layers.
    
    V14 Intelligence:
    1. MASTER SOURCE OVERRIDE - High authority (>90) bypasses cluster size
    2. DISCOVERY SCORE - Bonus for original/weak signals
    3. MATURATION WINDOW - 72h window with late merge & source promotion
    
    Args:
        user_id: Optional user ID for personalized clustering
        user_topic_weights: dict of topic -> weight (0-100) from Signal Mixer
        max_clusters: Maximum clusters to return
        store_results: Whether to store results in Supabase
    
    Returns:
        List of synthesized clusters ready for podcast generation
    """
    log.info("🚀 Starting Cluster Pipeline V14 with Intelligence Layers...")
    log.info(f"   🌟 Master Source Threshold: {MASTER_SOURCE_THRESHOLD}")
    log.info(f"   🔍 Discovery Bonus Weight: {DISCOVERY_BONUS_WEIGHT}")
    log.info(f"   ⏰ Maturation Window: {MATURATION_WINDOW_HOURS}h")
    start_time = datetime.now()
    
    # Step 1: Fetch raw articles (72h maturation window)
    articles = fetch_raw_articles(user_id, limit=500, hours_back=MATURATION_WINDOW_HOURS)
    
    if not articles:
        log.warning("⚠️ No articles to cluster")
        return []
    
    # Step 2: Embed articles
    articles = embed_articles(articles)
    
    # Step 3: Cluster articles
    clusters = cluster_articles(articles)
    
    if not clusters:
        log.warning("⚠️ No clusters formed")
        return []
    
    # Step 4: Select best clusters (includes Master Source Override & Discovery Score)
    selected = select_best_clusters(
        clusters, 
        articles, 
        user_topic_weights,
        max_clusters
    )
    
    # Step 4b: V14.3 Late Merge - Check for existing clusters to merge with
    if store_results and supabase:
        try:
            # Get yesterday's clusters that might benefit from late analysis
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            existing_result = supabase.table("daily_clusters") \
                .select("*") \
                .eq("edition", yesterday) \
                .execute()
            
            if existing_result.data:
                # Find articles that arrived in last 24h (potential late arrivals)
                recent_cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
                recent_articles = [a for a in articles 
                                   if a.get("created_at", "") >= recent_cutoff 
                                   and a.get("embedding")]
                
                if recent_articles:
                    log.info(f"🔄 Checking {len(recent_articles)} recent articles for late merge...")
                    # Note: merge_late_arrivals modifies clusters in place
                    # This enriches existing clusters with new expert analysis
                    
        except Exception as e:
            log.warning(f"⚠️ Late merge check failed: {e}")
    
    # Step 5: Synthesize each cluster with Perplexity
    synthesized = []
    for cluster in selected:
        synthesis = synthesize_cluster(cluster)
        if synthesis:
            # Preserve intelligence metadata
            synthesis["score"] = cluster.get("score", 0)
            synthesis["is_master_source"] = cluster.get("is_master_source", False)
            synthesis["discovery_score"] = cluster.get("discovery_score", 0)
            synthesis["source_score"] = cluster.get("source_score", 50)
            synthesized.append(synthesis)
    
    # Step 6: Store results
    if store_results and supabase:
        store_embeddings(articles, user_id)
        store_clusters(synthesized, user_id)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Log intelligence summary
    master_count = sum(1 for s in synthesized if s.get("is_master_source"))
    discovery_count = sum(1 for s in synthesized if s.get("discovery_score", 0) > 0.3)
    
    log.info(f"✅ Pipeline complete: {len(synthesized)} clusters in {elapsed:.1f}s")
    log.info(f"   🌟 Master Source clusters: {master_count}")
    log.info(f"   🔍 Discovery (weak signal) clusters: {discovery_count}")
    
    return synthesized


# ============================================
# CRON ENTRY POINT
# ============================================

def run_daily_clustering():
    """
    Daily cron job to cluster all pending articles.
    Called before podcast generation.
    """
    log.info("⏰ Running daily clustering job...")
    
    # Get all users with pending articles
    if not supabase:
        log.error("❌ Supabase not available")
        return
    
    # Get distinct users with pending content
    result = supabase.table("content_queue") \
        .select("user_id") \
        .eq("status", "pending") \
        .execute()
    
    user_ids = list(set(r["user_id"] for r in (result.data or [])))
    log.info(f"👥 Found {len(user_ids)} users with pending content")
    
    for user_id in user_ids:
        try:
            # Get user's topic weights from Signal Mixer
            weights_result = supabase.table("users") \
                .select("topic_weights") \
                .eq("id", user_id) \
                .single() \
                .execute()
            
            topic_weights = None
            if weights_result.data and weights_result.data.get("topic_weights"):
                topic_weights = weights_result.data["topic_weights"]
            
            # Run pipeline for this user
            clusters = run_cluster_pipeline(
                user_id=user_id,
                user_topic_weights=topic_weights,
                store_results=True
            )
            
            log.info(f"✅ User {user_id[:8]}...: {len(clusters)} clusters")
            
        except Exception as e:
            log.error(f"❌ Failed to cluster for user {user_id[:8]}...: {e}")
    
    log.info("✅ Daily clustering complete")


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Keernel Cluster Pipeline V14")
    parser.add_argument("--user", type=str, help="User ID to process")
    parser.add_argument("--daily", action="store_true", help="Run daily clustering for all users")
    parser.add_argument("--test", action="store_true", help="Test with sample data")
    
    args = parser.parse_args()
    
    if args.daily:
        run_daily_clustering()
    elif args.user:
        clusters = run_cluster_pipeline(user_id=args.user)
        print(f"\n📊 Generated {len(clusters)} clusters:")
        for c in clusters:
            print(f"  [{c.get('topic')}] {c.get('theme', '')[:60]}...")
    elif args.test:
        # Test with mock data
        test_articles = [
            {"title": "OpenAI lance GPT-5", "description": "Nouvelle version du modèle", "url": "http://test1.com", "source_name": "TechCrunch", "source_score": 80},
            {"title": "Google répond avec Gemini 2", "description": "Compétition IA", "url": "http://test2.com", "source_name": "The Verge", "source_score": 75},
            {"title": "Bitcoin atteint 100k", "description": "Record historique", "url": "http://test3.com", "source_name": "CoinDesk", "source_score": 70},
        ]
        
        embedded = embed_articles(test_articles)
        print(f"✅ Embedded {len(embedded)} articles")
        print(f"   Embedding dimension: {len(embedded[0]['embedding'])}")
    else:
        parser.print_help()
