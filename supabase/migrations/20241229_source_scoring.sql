-- ============================================
-- Keernel V14: Source Scoring Engine Migration
-- ============================================

-- 1. Source Performance Table (main scoring table)
CREATE TABLE IF NOT EXISTS source_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_domain TEXT UNIQUE NOT NULL,
    dynamic_score FLOAT DEFAULT 50,
    retention_score FLOAT DEFAULT 50,
    lead_time_score FLOAT DEFAULT 50,
    snr_score FLOAT DEFAULT 50,
    gsheet_score INTEGER,
    publication_count INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ACTIF',
    last_redemption_test TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS source_performance_domain_idx ON source_performance (source_domain);
CREATE INDEX IF NOT EXISTS source_performance_status_idx ON source_performance (status);
CREATE INDEX IF NOT EXISTS source_performance_score_idx ON source_performance (dynamic_score DESC);

-- 2. Segment Listens Table (for retention tracking)
CREATE TABLE IF NOT EXISTS segment_listens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_id UUID,
    segment_index INTEGER,
    source_domain TEXT,
    listened_ratio FLOAT DEFAULT 0,
    redemption_test BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS segment_listens_source_idx ON segment_listens (source_domain);
CREATE INDEX IF NOT EXISTS segment_listens_date_idx ON segment_listens (created_at DESC);
CREATE INDEX IF NOT EXISTS segment_listens_user_idx ON segment_listens (user_id);

-- 3. Cluster Articles Table (for lead time tracking)
CREATE TABLE IF NOT EXISTS cluster_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id TEXT,
    article_url TEXT,
    source_domain TEXT,
    article_published_at TIMESTAMPTZ,
    cluster_created_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS cluster_articles_source_idx ON cluster_articles (source_domain);
CREATE INDEX IF NOT EXISTS cluster_articles_cluster_idx ON cluster_articles (cluster_id);

-- 4. System Alerts Table (for safety lock alerts)
CREATE TABLE IF NOT EXISTS system_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type TEXT NOT NULL,
    severity TEXT DEFAULT 'INFO',
    message TEXT,
    data JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS system_alerts_type_idx ON system_alerts (alert_type, created_at DESC);
CREATE INDEX IF NOT EXISTS system_alerts_severity_idx ON system_alerts (severity, acknowledged);

-- 5. Add redemption_test column to content_queue if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'content_queue' AND column_name = 'redemption_test'
    ) THEN
        ALTER TABLE content_queue ADD COLUMN redemption_test BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- 6. RLS Policies
ALTER TABLE source_performance ENABLE ROW LEVEL SECURITY;
ALTER TABLE segment_listens ENABLE ROW LEVEL SECURITY;
ALTER TABLE cluster_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_alerts ENABLE ROW LEVEL SECURITY;

-- Service role full access
CREATE POLICY "Service role source_performance" ON source_performance 
    FOR ALL USING (auth.role() = 'service_role');
    
CREATE POLICY "Service role segment_listens" ON segment_listens 
    FOR ALL USING (auth.role() = 'service_role');
    
CREATE POLICY "Service role cluster_articles" ON cluster_articles 
    FOR ALL USING (auth.role() = 'service_role');
    
CREATE POLICY "Service role system_alerts" ON system_alerts 
    FOR ALL USING (auth.role() = 'service_role');

-- Users can read their own listens
CREATE POLICY "Users read own listens" ON segment_listens 
    FOR SELECT USING (auth.uid() = user_id);

-- ============================================
-- VERIFICATION
-- ============================================
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('source_performance', 'segment_listens', 'cluster_articles', 'system_alerts');
