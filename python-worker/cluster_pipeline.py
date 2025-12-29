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
    "stocks": "Bourse, actions, marchés financiers, valorisation, earnings, indices",
    "deals": "M&A, venture capital, levées de fonds, acquisitions, startups, investissements",
    
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


def select_best_clusters(
    clusters: dict, 
    articles: list[dict],
    user_topic_weights: dict[str, int] = None,
    max_clusters: int = MAX_CLUSTERS
) -> list[dict]:
    """
    Select the best clusters and map them to topics.
    
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
    
    for cluster_id, indices in clusters.items():
        if not indices:
            continue
        
        # Get cluster articles
        cluster_articles = [articles[i] for i in indices]
        
        # Compute centroid (mean of all embeddings in cluster)
        embeddings = np.array([a["embedding"] for a in cluster_articles])
        centroid = np.mean(embeddings, axis=0)
        
        # Compute density score (size * avg source authority)
        source_scores = [a.get("source_score", 50) for a in cluster_articles]
        density = len(indices) * np.mean(source_scores) / 100
        
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
        
        # Find representative article (closest to centroid)
        distances = [np.linalg.norm(centroid - np.array(a["embedding"])) for a in cluster_articles]
        representative_idx = indices[np.argmin(distances)]
        representative = articles[representative_idx]
        
        # Generate cluster theme from representative article
        cluster_theme = representative.get("title", "Unknown")[:100]
        
        scored_clusters.append({
            "cluster_id": cluster_id,
            "indices": indices,
            "article_count": len(indices),
            "centroid": centroid,
            "topic": best_topic,
            "topic_similarity": best_similarity,
            "density": density,
            "theme": cluster_theme,
            "representative": representative,
            "articles": cluster_articles
        })
    
    # Sort by combined score (density + topic similarity + user weight)
    for cluster in scored_clusters:
        user_weight = user_topic_weights.get(cluster["topic"], 50) / 100
        cluster["score"] = cluster["density"] * 0.4 + cluster["topic_similarity"] * 0.3 + user_weight * 0.3
    
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
    
    # Log selection
    for i, cluster in enumerate(selected):
        log.info(f"   {i+1}. [{cluster['topic']}] {cluster['theme'][:50]}... "
                 f"(articles={cluster['article_count']}, score={cluster['score']:.3f})")
    
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

def fetch_raw_articles(user_id: str = None, limit: int = 500) -> list[dict]:
    """Fetch raw articles from content_queue for clustering."""
    if not supabase:
        return []
    
    # Get articles from last 24 hours
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    
    query = supabase.table("content_queue") \
        .select("id, url, title, source_name, source_type, keyword, created_at") \
        .eq("status", "pending") \
        .gte("created_at", yesterday) \
        .order("created_at", desc=True) \
        .limit(limit)
    
    if user_id:
        query = query.eq("user_id", user_id)
    
    result = query.execute()
    
    articles = result.data if result.data else []
    log.info(f"📥 Fetched {len(articles)} raw articles for clustering")
    
    return articles


def run_cluster_pipeline(
    user_id: str = None,
    user_topic_weights: dict[str, int] = None,
    max_clusters: int = MAX_CLUSTERS,
    store_results: bool = True
) -> list[dict]:
    """
    Run the complete clustering pipeline.
    
    Args:
        user_id: Optional user ID for personalized clustering
        user_topic_weights: dict of topic -> weight (0-100) from Signal Mixer
        max_clusters: Maximum clusters to return
        store_results: Whether to store results in Supabase
    
    Returns:
        List of synthesized clusters ready for podcast generation
    """
    log.info("🚀 Starting Cluster Pipeline V14...")
    start_time = datetime.now()
    
    # Step 1: Fetch raw articles
    articles = fetch_raw_articles(user_id, limit=500)
    
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
    
    # Step 4: Select best clusters
    selected = select_best_clusters(
        clusters, 
        articles, 
        user_topic_weights,
        max_clusters
    )
    
    # Step 5: Synthesize each cluster with Perplexity
    synthesized = []
    for cluster in selected:
        synthesis = synthesize_cluster(cluster)
        if synthesis:
            # Preserve score from selection
            synthesis["score"] = cluster.get("score", 0)
            synthesized.append(synthesis)
    
    # Step 6: Store results
    if store_results and supabase:
        store_embeddings(articles, user_id)
        store_clusters(synthesized, user_id)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    log.info(f"✅ Pipeline complete: {len(synthesized)} clusters in {elapsed:.1f}s")
    
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
