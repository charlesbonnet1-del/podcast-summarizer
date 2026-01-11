-- Migration: Fresh + Archive Architecture
-- Date: 2026-01-11
-- Purpose: New architecture with articles table, source tracking, and cluster deduplication

-- ============================================
-- 1. ARTICLES TABLE (replaces content_queue for sourcing)
-- ============================================

CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Content
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    content TEXT,  -- Scraped content

    -- Embedding (pgvector)
    embedding vector(1536),

    -- Source info
    source_name TEXT NOT NULL,
    source_url TEXT,  -- RSS feed URL
    topic TEXT NOT NULL,  -- From GSheet source topic

    -- Timestamps
    published_at TIMESTAMPTZ,  -- When article was published
    fetched_at TIMESTAMPTZ DEFAULT NOW()  -- When we fetched it

    -- Note: is_fresh is computed at query time, not stored
    -- Fresh = fetched_at > NOW() - INTERVAL '48 hours'
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles(topic);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_name);
CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);

-- Vector similarity index for archive search
CREATE INDEX IF NOT EXISTS idx_articles_embedding ON articles
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================
-- 2. SOURCE_FETCH_STATUS TABLE (tracking fetches)
-- ============================================

CREATE TABLE IF NOT EXISTS source_fetch_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification (from GSheet)
    source_name TEXT UNIQUE NOT NULL,
    source_url TEXT NOT NULL,  -- RSS feed URL
    topic TEXT NOT NULL,

    -- Fetch tracking
    last_fetched_at TIMESTAMPTZ,
    next_fetch_at TIMESTAMPTZ DEFAULT NOW(),  -- For scheduling

    -- Stats
    total_fetches INT DEFAULT 0,
    successful_fetches INT DEFAULT 0,
    failed_fetches INT DEFAULT 0,
    consecutive_failures INT DEFAULT 0,
    last_error TEXT,

    -- Estimated activity
    avg_articles_per_fetch FLOAT DEFAULT 0,

    -- Status
    status TEXT DEFAULT 'unknown' CHECK (status IN ('working', 'broken', 'unknown')),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for scheduling (fetch oldest first)
CREATE INDEX IF NOT EXISTS idx_source_fetch_next ON source_fetch_status(next_fetch_at ASC);
CREATE INDEX IF NOT EXISTS idx_source_fetch_status ON source_fetch_status(status);

-- ============================================
-- 3. USED_CLUSTERS TABLE (avoid duplicate clusters)
-- ============================================

CREATE TABLE IF NOT EXISTS used_clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Cluster identification
    cluster_hash TEXT UNIQUE NOT NULL,  -- Hash of sorted article URLs
    topic TEXT NOT NULL,
    representative_title TEXT,

    -- Articles in this cluster
    article_urls TEXT[] NOT NULL,  -- Array of URLs
    article_count INT NOT NULL,

    -- When this cluster was used
    used_at TIMESTAMPTZ DEFAULT NOW(),

    -- Optional: link to generated content
    episode_id UUID
);

-- Index for checking recent clusters
CREATE INDEX IF NOT EXISTS idx_used_clusters_hash ON used_clusters(cluster_hash);
CREATE INDEX IF NOT EXISTS idx_used_clusters_used_at ON used_clusters(used_at DESC);
CREATE INDEX IF NOT EXISTS idx_used_clusters_topic ON used_clusters(topic);

-- ============================================
-- 4. FUNCTION: Get fresh articles for clustering
-- ============================================

CREATE OR REPLACE FUNCTION get_fresh_articles(
    hours_back INT DEFAULT 48
)
RETURNS TABLE (
    id UUID,
    url TEXT,
    title TEXT,
    description TEXT,
    content TEXT,
    embedding vector(1536),
    source_name TEXT,
    topic TEXT,
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id,
        a.url,
        a.title,
        a.description,
        a.content,
        a.embedding,
        a.source_name,
        a.topic,
        a.published_at,
        a.fetched_at
    FROM articles a
    WHERE a.fetched_at > NOW() - (hours_back || ' hours')::INTERVAL
      AND a.embedding IS NOT NULL
    ORDER BY a.fetched_at DESC;
END;
$$;

-- ============================================
-- 5. FUNCTION: Find archive context for a cluster
-- ============================================

CREATE OR REPLACE FUNCTION find_archive_context(
    cluster_centroid vector(1536),
    exclude_urls TEXT[],
    max_results INT DEFAULT 2,
    min_similarity FLOAT DEFAULT 0.7,
    max_age_days INT DEFAULT 90
)
RETURNS TABLE (
    id UUID,
    url TEXT,
    title TEXT,
    description TEXT,
    source_name TEXT,
    topic TEXT,
    published_at TIMESTAMPTZ,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id,
        a.url,
        a.title,
        a.description,
        a.source_name,
        a.topic,
        a.published_at,
        1 - (a.embedding <=> cluster_centroid) AS similarity
    FROM articles a
    WHERE a.fetched_at <= NOW() - INTERVAL '48 hours'  -- Not fresh (archive)
      AND a.fetched_at > NOW() - (max_age_days || ' days')::INTERVAL
      AND a.embedding IS NOT NULL
      AND NOT (a.url = ANY(exclude_urls))  -- Exclude articles already in cluster
      AND 1 - (a.embedding <=> cluster_centroid) >= min_similarity
    ORDER BY a.embedding <=> cluster_centroid
    LIMIT max_results;
END;
$$;

-- ============================================
-- 6. FUNCTION: Check if cluster was already used
-- ============================================

CREATE OR REPLACE FUNCTION is_cluster_used(
    article_urls_to_check TEXT[],
    days_back INT DEFAULT 7
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    cluster_hash_to_check TEXT;
    existing_count INT;
BEGIN
    -- Generate hash from sorted URLs
    SELECT md5(array_to_string(array_agg(u ORDER BY u), ','))
    INTO cluster_hash_to_check
    FROM unnest(article_urls_to_check) AS u;

    -- Check if this exact cluster was used recently
    SELECT COUNT(*) INTO existing_count
    FROM used_clusters
    WHERE cluster_hash = cluster_hash_to_check
      AND used_at > NOW() - (days_back || ' days')::INTERVAL;

    RETURN existing_count > 0;
END;
$$;

-- ============================================
-- 7. FUNCTION: Mark cluster as used
-- ============================================

CREATE OR REPLACE FUNCTION mark_cluster_used(
    p_article_urls TEXT[],
    p_topic TEXT,
    p_representative_title TEXT
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    cluster_hash_val TEXT;
    new_id UUID;
BEGIN
    -- Generate hash from sorted URLs
    SELECT md5(array_to_string(array_agg(u ORDER BY u), ','))
    INTO cluster_hash_val
    FROM unnest(p_article_urls) AS u;

    -- Insert or update
    INSERT INTO used_clusters (cluster_hash, topic, representative_title, article_urls, article_count)
    VALUES (cluster_hash_val, p_topic, p_representative_title, p_article_urls, array_length(p_article_urls, 1))
    ON CONFLICT (cluster_hash) DO UPDATE SET
        used_at = NOW(),
        representative_title = EXCLUDED.representative_title
    RETURNING id INTO new_id;

    RETURN new_id;
END;
$$;

-- ============================================
-- 8. FUNCTION: Get sources to fetch (oldest first)
-- ============================================

CREATE OR REPLACE FUNCTION get_sources_to_fetch(
    batch_size INT DEFAULT 150
)
RETURNS TABLE (
    source_name TEXT,
    source_url TEXT,
    topic TEXT,
    last_fetched_at TIMESTAMPTZ,
    consecutive_failures INT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.source_name,
        s.source_url,
        s.topic,
        s.last_fetched_at,
        s.consecutive_failures
    FROM source_fetch_status s
    WHERE s.status != 'broken'  -- Skip broken sources
      AND s.next_fetch_at <= NOW()  -- Due for fetch
    ORDER BY s.next_fetch_at ASC  -- Oldest first
    LIMIT batch_size;
END;
$$;

-- ============================================
-- 9. Permissions
-- ============================================

GRANT ALL ON articles TO authenticated;
GRANT ALL ON articles TO service_role;
GRANT ALL ON source_fetch_status TO authenticated;
GRANT ALL ON source_fetch_status TO service_role;
GRANT ALL ON used_clusters TO authenticated;
GRANT ALL ON used_clusters TO service_role;

GRANT EXECUTE ON FUNCTION get_fresh_articles TO authenticated;
GRANT EXECUTE ON FUNCTION get_fresh_articles TO service_role;
GRANT EXECUTE ON FUNCTION find_archive_context TO authenticated;
GRANT EXECUTE ON FUNCTION find_archive_context TO service_role;
GRANT EXECUTE ON FUNCTION is_cluster_used TO authenticated;
GRANT EXECUTE ON FUNCTION is_cluster_used TO service_role;
GRANT EXECUTE ON FUNCTION mark_cluster_used TO authenticated;
GRANT EXECUTE ON FUNCTION mark_cluster_used TO service_role;
GRANT EXECUTE ON FUNCTION get_sources_to_fetch TO authenticated;
GRANT EXECUTE ON FUNCTION get_sources_to_fetch TO service_role;
