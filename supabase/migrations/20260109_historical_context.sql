-- Migration: Add historical context search function
-- Date: 2026-01-09
-- Purpose: Enable finding similar past articles for trend analysis and enrichment

-- ============================================
-- 1. FUNCTION: Find historical similar articles
-- ============================================

CREATE OR REPLACE FUNCTION find_historical_context(
    query_embedding vector(1536),
    days_back INT DEFAULT 30,
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    url TEXT,
    title TEXT,
    description TEXT,
    topic TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ne.id,
        ne.url,
        ne.title,
        ne.description,
        ne.topic,
        ne.created_at,
        1 - (ne.embedding <=> query_embedding) AS similarity
    FROM news_embeddings ne
    WHERE ne.created_at > NOW() - (days_back || ' days')::INTERVAL
      AND 1 - (ne.embedding <=> query_embedding) > match_threshold
    ORDER BY ne.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================
-- 2. FUNCTION: Get trend analysis (volume over time)
-- ============================================

CREATE OR REPLACE FUNCTION get_topic_trend(
    query_embedding vector(1536),
    days_back INT DEFAULT 30,
    match_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    week_start DATE,
    article_count BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        DATE_TRUNC('week', ne.created_at)::DATE as week_start,
        COUNT(*) as article_count
    FROM news_embeddings ne
    WHERE ne.created_at > NOW() - (days_back || ' days')::INTERVAL
      AND 1 - (ne.embedding <=> query_embedding) > match_threshold
    GROUP BY DATE_TRUNC('week', ne.created_at)
    ORDER BY week_start;
END;
$$;

-- ============================================
-- 3. Add description column to news_embeddings if missing
-- ============================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'news_embeddings' AND column_name = 'description'
    ) THEN
        ALTER TABLE news_embeddings ADD COLUMN description TEXT;
    END IF;
END $$;

-- ============================================
-- 4. Grant permissions
-- ============================================

GRANT EXECUTE ON FUNCTION find_historical_context TO authenticated;
GRANT EXECUTE ON FUNCTION find_historical_context TO service_role;
GRANT EXECUTE ON FUNCTION get_topic_trend TO authenticated;
GRANT EXECUTE ON FUNCTION get_topic_trend TO service_role;
