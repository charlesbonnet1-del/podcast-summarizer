-- ============================================
-- Keernel V14: Intelligence Layers Migration
-- ============================================
-- 1. Master Source Override
-- 2. Discovery Score
-- 3. 72h Maturation Window

-- ============================================
-- 1. ADD NEW COLUMNS
-- ============================================

-- Add source_score to content_queue if not exists
ALTER TABLE content_queue 
ADD COLUMN IF NOT EXISTS source_score INTEGER DEFAULT 50;

-- Add intelligence metadata to daily_clusters
ALTER TABLE daily_clusters 
ADD COLUMN IF NOT EXISTS is_master_source BOOLEAN DEFAULT FALSE;

ALTER TABLE daily_clusters 
ADD COLUMN IF NOT EXISTS discovery_score FLOAT DEFAULT 0;

ALTER TABLE daily_clusters 
ADD COLUMN IF NOT EXISTS source_score INTEGER DEFAULT 50;

-- Add maturation tracking
ALTER TABLE daily_clusters 
ADD COLUMN IF NOT EXISTS merged_articles JSONB DEFAULT '[]'::jsonb;

ALTER TABLE daily_clusters 
ADD COLUMN IF NOT EXISTS source_promoted BOOLEAN DEFAULT FALSE;

-- Comments for documentation
COMMENT ON COLUMN daily_clusters.is_master_source IS 'V14.1: True if from source with GSheet score > 90';
COMMENT ON COLUMN daily_clusters.discovery_score IS 'V14.2: Originality score (0-1), high = weak signal';
COMMENT ON COLUMN daily_clusters.merged_articles IS 'V14.3: URLs of articles merged via late arrival';
COMMENT ON COLUMN daily_clusters.source_promoted IS 'V14.3: True if representative was promoted by late expert';

-- ============================================
-- 2. CREATE INDEXES FOR INTELLIGENCE QUERIES
-- ============================================

-- Index for finding master source content
CREATE INDEX IF NOT EXISTS content_queue_source_score_idx 
ON content_queue (source_score DESC) 
WHERE source_score >= 90;

-- Index for discovery score queries
CREATE INDEX IF NOT EXISTS daily_clusters_discovery_idx 
ON daily_clusters (discovery_score DESC) 
WHERE discovery_score > 0.3;

-- Index for master source clusters
CREATE INDEX IF NOT EXISTS daily_clusters_master_idx 
ON daily_clusters (is_master_source) 
WHERE is_master_source = TRUE;

-- ============================================
-- 3. UPDATE CLEANUP FUNCTION (72h RETENTION)
-- ============================================

-- Modified cleanup to keep 72h of content for maturation
CREATE OR REPLACE FUNCTION cleanup_old_content(hours_to_keep INT DEFAULT 72)
RETURNS TABLE (
    table_name TEXT,
    deleted_count INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    cutoff TIMESTAMPTZ;
    content_deleted INTEGER;
    embeddings_deleted INTEGER;
BEGIN
    -- V14.3: Keep content for 72h maturation window
    cutoff := NOW() - (hours_to_keep || ' hours')::INTERVAL;
    
    -- Clean processed content (not pending)
    DELETE FROM content_queue
    WHERE status = 'processed' 
    AND created_at < cutoff;
    GET DIAGNOSTICS content_deleted = ROW_COUNT;
    
    -- Clean old embeddings (keep 7 days for analysis)
    DELETE FROM news_embeddings
    WHERE created_at < NOW() - INTERVAL '7 days';
    GET DIAGNOSTICS embeddings_deleted = ROW_COUNT;
    
    -- Return results
    RETURN QUERY 
    SELECT 'content_queue'::TEXT, content_deleted
    UNION ALL
    SELECT 'news_embeddings'::TEXT, embeddings_deleted;
END;
$$;

-- ============================================
-- 4. VIEW FOR INTELLIGENCE MONITORING
-- ============================================

CREATE OR REPLACE VIEW v_cluster_intelligence AS
SELECT 
    dc.edition,
    dc.topic,
    dc.theme,
    dc.score,
    dc.article_count,
    dc.is_master_source,
    dc.discovery_score,
    dc.source_score,
    dc.source_promoted,
    CASE 
        WHEN dc.is_master_source THEN '🌟 MASTER'
        WHEN dc.discovery_score > 0.3 THEN '🔍 DISCOVERY'
        WHEN dc.source_promoted THEN '📈 PROMOTED'
        ELSE '📊 STANDARD'
    END as intelligence_type,
    dc.created_at
FROM daily_clusters dc
ORDER BY dc.edition DESC, dc.score DESC;

-- ============================================
-- 5. FUNCTION TO GET MASTER SOURCES
-- ============================================

CREATE OR REPLACE FUNCTION get_master_source_articles(
    p_user_id UUID DEFAULT NULL,
    p_hours_back INT DEFAULT 72
)
RETURNS TABLE (
    id UUID,
    url TEXT,
    title TEXT,
    source_name TEXT,
    source_score INTEGER,
    keyword TEXT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cq.id,
        cq.url,
        cq.title,
        cq.source_name,
        cq.source_score,
        cq.keyword,
        cq.created_at
    FROM content_queue cq
    WHERE cq.status = 'pending'
    AND cq.source_score >= 90
    AND cq.created_at >= NOW() - (p_hours_back || ' hours')::INTERVAL
    AND (p_user_id IS NULL OR cq.user_id = p_user_id)
    ORDER BY cq.source_score DESC, cq.created_at DESC;
END;
$$;

-- ============================================
-- 6. FUNCTION FOR DISCOVERY CANDIDATES
-- ============================================

-- This will be called from Python, but having SQL version for debugging
CREATE OR REPLACE FUNCTION find_discovery_candidates(
    p_edition DATE DEFAULT CURRENT_DATE,
    p_min_discovery_score FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    cluster_id TEXT,
    topic TEXT,
    theme TEXT,
    discovery_score FLOAT,
    article_count INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.cluster_id,
        dc.topic,
        dc.theme,
        dc.discovery_score,
        dc.article_count
    FROM daily_clusters dc
    WHERE dc.edition = p_edition
    AND dc.discovery_score >= p_min_discovery_score
    AND dc.is_master_source = FALSE
    ORDER BY dc.discovery_score DESC;
END;
$$;

-- ============================================
-- 7. GRANT PERMISSIONS
-- ============================================

GRANT EXECUTE ON FUNCTION cleanup_old_content TO authenticated;
GRANT EXECUTE ON FUNCTION get_master_source_articles TO authenticated;
GRANT EXECUTE ON FUNCTION find_discovery_candidates TO authenticated;
GRANT SELECT ON v_cluster_intelligence TO authenticated;

-- ============================================
-- 8. VERIFICATION
-- ============================================

SELECT 'Columns added' as status, 
       COUNT(*) as count 
FROM information_schema.columns 
WHERE table_name = 'daily_clusters' 
AND column_name IN ('is_master_source', 'discovery_score', 'source_promoted');
