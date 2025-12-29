-- ============================================
-- Keernel V14: Pivot stocks → deals
-- ============================================
-- This migration:
-- 1. Migrates all "stocks" data to "deals"
-- 2. Adds deal_type column for classification
-- 3. Removes stocks references

-- ============================================
-- 1. ADD deal_type COLUMN
-- ============================================

-- Add deal_type to content_queue
ALTER TABLE content_queue 
ADD COLUMN IF NOT EXISTS deal_type TEXT;

-- Add premium_source flag
ALTER TABLE content_queue 
ADD COLUMN IF NOT EXISTS premium_source BOOLEAN DEFAULT FALSE;

-- Add deal_type to daily_clusters
ALTER TABLE daily_clusters 
ADD COLUMN IF NOT EXISTS deal_type TEXT;

-- Comment for documentation
COMMENT ON COLUMN content_queue.deal_type IS 'Type of deal: MA (M&A), FUNDRAISING, PARTNERSHIP, IPO, MARKET';
COMMENT ON COLUMN daily_clusters.deal_type IS 'Type of deal: MA (M&A), FUNDRAISING, PARTNERSHIP, IPO, MARKET';

-- ============================================
-- 2. MIGRATE stocks → deals
-- ============================================

-- Migrate content_queue
UPDATE content_queue 
SET keyword = 'deals', deal_type = 'MARKET'
WHERE keyword = 'stocks';

-- Migrate daily_clusters
UPDATE daily_clusters 
SET topic = 'deals', deal_type = 'MARKET'
WHERE topic = 'stocks';

-- Migrate cached_segments
UPDATE cached_segments 
SET topic_slug = 'deals'
WHERE topic_slug = 'stocks';

-- Migrate news_embeddings
UPDATE news_embeddings 
SET topic = 'deals'
WHERE topic = 'stocks';

-- Migrate source_performance
UPDATE source_performance 
SET source_domain = REPLACE(source_domain, 'stocks', 'deals')
WHERE source_domain LIKE '%stocks%';

-- Migrate user_interests
UPDATE user_interests 
SET keyword = 'deals'
WHERE keyword = 'stocks';

-- ============================================
-- 3. UPDATE topics TABLE (if exists)
-- ============================================

-- Delete stocks topic
DELETE FROM topics WHERE slug = 'stocks';

-- Update deals topic with expanded scope
UPDATE topics 
SET 
    display_name = 'M&A & VC',
    description = 'Fusions-acquisitions, levées de fonds, IPO et mouvements de capital',
    keywords = ARRAY['M&A', 'acquisition', 'levée de fonds', 'VC', 'funding', 'IPO', 'bourse', 'valorisation']
WHERE slug = 'deals';

-- ============================================
-- 4. UPDATE user topic_weights (JSONB)
-- ============================================

-- Migrate stocks weight to deals in users.topic_weights
UPDATE users 
SET topic_weights = topic_weights - 'stocks' || 
    jsonb_build_object('deals', COALESCE(
        GREATEST(
            (topic_weights->>'stocks')::int, 
            (topic_weights->>'deals')::int
        ), 
        50
    ))
WHERE topic_weights ? 'stocks';

-- ============================================
-- 5. CREATE deal_type CLASSIFICATION FUNCTION
-- ============================================

CREATE OR REPLACE FUNCTION classify_deal_type(title TEXT, content TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    combined TEXT;
BEGIN
    combined := LOWER(COALESCE(title, '') || ' ' || COALESCE(content, ''));
    
    -- M&A keywords
    IF combined ~ '(acquisition|rachat|fusion|merger|m&a|achète|rachète|absorb)' THEN
        RETURN 'MA';
    END IF;
    
    -- Fundraising keywords
    IF combined ~ '(levée|fundrais|série [a-d]|seed|investissement|investisseur|vc|venture|capital-risque)' THEN
        RETURN 'FUNDRAISING';
    END IF;
    
    -- IPO keywords
    IF combined ~ '(ipo|introduction en bourse|entrée en bourse|cotation|nasdaq|nyse|euronext)' THEN
        RETURN 'IPO';
    END IF;
    
    -- Partnership keywords
    IF combined ~ '(partenariat|partnership|alliance|collaboration|accord|joint.?venture)' THEN
        RETURN 'PARTNERSHIP';
    END IF;
    
    -- Default to MARKET for general stock/market news
    IF combined ~ '(bourse|action|cac|dow|nasdaq|valorisation|cours|marché)' THEN
        RETURN 'MARKET';
    END IF;
    
    RETURN NULL;
END;
$$;

-- ============================================
-- 6. AUTO-CLASSIFY EXISTING deals CONTENT
-- ============================================

-- Classify existing deals content that doesn't have deal_type
UPDATE content_queue 
SET deal_type = classify_deal_type(title, processed_content)
WHERE keyword = 'deals' AND deal_type IS NULL;

UPDATE daily_clusters 
SET deal_type = classify_deal_type(theme, thesis)
WHERE topic = 'deals' AND deal_type IS NULL;

-- ============================================
-- 7. CREATE INDEX FOR deal_type
-- ============================================

CREATE INDEX IF NOT EXISTS content_queue_deal_type_idx 
ON content_queue (deal_type) 
WHERE keyword = 'deals';

CREATE INDEX IF NOT EXISTS daily_clusters_deal_type_idx 
ON daily_clusters (deal_type) 
WHERE topic = 'deals';

-- ============================================
-- 8. VERIFICATION
-- ============================================

-- Check no more stocks references
SELECT 'content_queue' as table_name, COUNT(*) as stocks_count 
FROM content_queue WHERE keyword = 'stocks'
UNION ALL
SELECT 'daily_clusters', COUNT(*) 
FROM daily_clusters WHERE topic = 'stocks'
UNION ALL
SELECT 'cached_segments', COUNT(*) 
FROM cached_segments WHERE topic_slug = 'stocks';

-- Check deal_type distribution
SELECT deal_type, COUNT(*) as count
FROM content_queue 
WHERE keyword = 'deals'
GROUP BY deal_type;
