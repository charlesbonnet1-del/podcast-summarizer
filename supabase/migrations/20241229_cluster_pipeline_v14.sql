-- ============================================
-- Keernel V14: Cluster Pipeline Migration
-- ============================================
-- Run this in Supabase SQL Editor

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. News Embeddings Table (for storing article vectors)
CREATE TABLE IF NOT EXISTS news_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT,
    description TEXT,
    source_name TEXT,
    source_score INTEGER DEFAULT 50,
    topic TEXT,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    edition DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint on URL (one embedding per article)
    CONSTRAINT news_embeddings_url_unique UNIQUE (url)
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS news_embeddings_embedding_idx 
ON news_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for filtering by date
CREATE INDEX IF NOT EXISTS news_embeddings_edition_idx 
ON news_embeddings (edition DESC);

-- Index for filtering by user
CREATE INDEX IF NOT EXISTS news_embeddings_user_idx 
ON news_embeddings (user_id);

-- 3. Daily Clusters Table (synthesized clusters ready for podcast)
CREATE TABLE IF NOT EXISTS daily_clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id TEXT NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    edition DATE DEFAULT CURRENT_DATE,
    topic TEXT NOT NULL,
    theme TEXT NOT NULL,
    thesis TEXT,
    antithesis TEXT,
    key_data JSONB DEFAULT '[]'::jsonb,
    sources JSONB DEFAULT '[]'::jsonb,
    hook TEXT,
    article_count INTEGER DEFAULT 0,
    urls JSONB DEFAULT '[]'::jsonb,
    score FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint: one cluster per ID per day
    CONSTRAINT daily_clusters_unique UNIQUE (cluster_id, edition)
);

-- Index for retrieving daily clusters
CREATE INDEX IF NOT EXISTS daily_clusters_edition_idx 
ON daily_clusters (edition DESC, score DESC);

-- Index for user-specific clusters
CREATE INDEX IF NOT EXISTS daily_clusters_user_idx 
ON daily_clusters (user_id, edition DESC);

-- Index for topic filtering
CREATE INDEX IF NOT EXISTS daily_clusters_topic_idx 
ON daily_clusters (topic);

-- 4. Add description column to content_queue if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'content_queue' AND column_name = 'description'
    ) THEN
        ALTER TABLE content_queue ADD COLUMN description TEXT;
    END IF;
END $$;

-- 5. Function to find similar articles (for deduplication)
CREATE OR REPLACE FUNCTION find_similar_articles(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.85,
    match_count INT DEFAULT 10,
    filter_edition DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    id UUID,
    url TEXT,
    title TEXT,
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
        1 - (ne.embedding <=> query_embedding) AS similarity
    FROM news_embeddings ne
    WHERE ne.edition = filter_edition
      AND 1 - (ne.embedding <=> query_embedding) > match_threshold
    ORDER BY ne.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 6. Function to get cluster centroids (for analysis)
CREATE OR REPLACE FUNCTION get_topic_centroid(
    target_topic TEXT,
    target_edition DATE DEFAULT CURRENT_DATE
)
RETURNS vector(1536)
LANGUAGE plpgsql
AS $$
DECLARE
    centroid vector(1536);
BEGIN
    SELECT AVG(embedding) INTO centroid
    FROM news_embeddings
    WHERE topic = target_topic
      AND edition = target_edition;
    
    RETURN centroid;
END;
$$;

-- 7. RLS Policies (Row Level Security)

-- Enable RLS on new tables
ALTER TABLE news_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_clusters ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own embeddings
CREATE POLICY "Users can read own embeddings" ON news_embeddings
    FOR SELECT USING (auth.uid() = user_id OR user_id IS NULL);

-- Policy: Users can read their own clusters
CREATE POLICY "Users can read own clusters" ON daily_clusters
    FOR SELECT USING (auth.uid() = user_id OR user_id IS NULL);

-- Policy: Service role can do everything (for backend)
CREATE POLICY "Service role full access embeddings" ON news_embeddings
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access clusters" ON daily_clusters
    FOR ALL USING (auth.role() = 'service_role');

-- 8. Cleanup function (remove old data)
CREATE OR REPLACE FUNCTION cleanup_old_embeddings(days_to_keep INT DEFAULT 7)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM news_embeddings
    WHERE edition < CURRENT_DATE - days_to_keep;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    DELETE FROM daily_clusters
    WHERE edition < CURRENT_DATE - days_to_keep;
    
    RETURN deleted_count;
END;
$$;

-- 9. Grant permissions
GRANT ALL ON news_embeddings TO authenticated;
GRANT ALL ON daily_clusters TO authenticated;
GRANT EXECUTE ON FUNCTION find_similar_articles TO authenticated;
GRANT EXECUTE ON FUNCTION get_topic_centroid TO authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_embeddings TO authenticated;

-- ============================================
-- VERIFICATION
-- ============================================

-- Check tables created
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('news_embeddings', 'daily_clusters');

-- Check vector extension
SELECT * FROM pg_extension WHERE extname = 'vector';
