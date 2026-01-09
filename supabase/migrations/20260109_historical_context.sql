-- Migration: Add historical context search function
-- Date: 2026-01-09
-- Purpose: Enable finding similar past articles for trend analysis and enrichment

-- ============================================
-- 0. CREATE news_embeddings TABLE IF NOT EXISTS
-- ============================================

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS news_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL,
    title TEXT,
    description TEXT,
    topic TEXT,
    source_name TEXT,
    user_id UUID,
    edition DATE DEFAULT CURRENT_DATE,
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT news_embeddings_url_unique UNIQUE (url)
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS news_embeddings_embedding_idx
ON news_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for date filtering
CREATE INDEX IF NOT EXISTS news_embeddings_created_at_idx
ON news_embeddings (created_at DESC);

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
      AND ne.embedding IS NOT NULL
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
      AND ne.embedding IS NOT NULL
      AND 1 - (ne.embedding <=> query_embedding) > match_threshold
    GROUP BY DATE_TRUNC('week', ne.created_at)
    ORDER BY week_start;
END;
$$;

-- ============================================
-- 3. Grant permissions
-- ============================================

GRANT ALL ON news_embeddings TO authenticated;
GRANT ALL ON news_embeddings TO service_role;
GRANT EXECUTE ON FUNCTION find_historical_context TO authenticated;
GRANT EXECUTE ON FUNCTION find_historical_context TO service_role;
GRANT EXECUTE ON FUNCTION get_topic_trend TO authenticated;
GRANT EXECUTE ON FUNCTION get_topic_trend TO service_role;
