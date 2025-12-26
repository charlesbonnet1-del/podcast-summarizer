-- Migration: Signal Mixer & Playlist Selection
-- Creates tables for user signal weights and adds relevance scoring

-- ============================================
-- USER SIGNAL WEIGHTS TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS user_signal_weights (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    weights JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Index for fast lookup by user
CREATE INDEX IF NOT EXISTS idx_user_signal_weights_user_id 
ON user_signal_weights(user_id);

-- RLS Policies
ALTER TABLE user_signal_weights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own signal weights"
ON user_signal_weights FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own signal weights"
ON user_signal_weights FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own signal weights"
ON user_signal_weights FOR UPDATE
USING (auth.uid() = user_id);

-- ============================================
-- ADD RELEVANCE SCORE TO SEGMENT CACHE
-- ============================================

-- Add relevance_score column if it doesn't exist
ALTER TABLE segment_cache 
ADD COLUMN IF NOT EXISTS relevance_score FLOAT DEFAULT 0.5;

-- Add index for sorting by relevance
CREATE INDEX IF NOT EXISTS idx_segment_cache_relevance 
ON segment_cache(target_date, relevance_score DESC);

-- ============================================
-- SAMPLE DEFAULT WEIGHTS
-- ============================================

-- Example: Insert default weights for a user (uncomment to use)
-- INSERT INTO user_signal_weights (user_id, weights)
-- VALUES (
--     'your-user-id-here',
--     '{
--         "ia": 100,
--         "quantum": 80,
--         "robotics": 60,
--         "asia": 50,
--         "regulation": 50,
--         "resources": 30,
--         "crypto": 70,
--         "macro": 60,
--         "stocks": 40,
--         "energy": 50,
--         "health": 50,
--         "space": 80,
--         "cinema": 20,
--         "gaming": 30,
--         "lifestyle": 0
--     }'::jsonb
-- );

-- ============================================
-- FUNCTION: Get weighted segments for user
-- ============================================

CREATE OR REPLACE FUNCTION get_weighted_segments(
    p_user_id UUID,
    p_target_date DATE DEFAULT CURRENT_DATE,
    p_limit INT DEFAULT 15
)
RETURNS TABLE (
    segment_id UUID,
    topic_slug TEXT,
    audio_url TEXT,
    duration INT,
    relevance_score FLOAT,
    user_weight INT,
    final_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH user_weights AS (
        SELECT 
            COALESCE(weights, '{}'::jsonb) as weights
        FROM user_signal_weights
        WHERE user_id = p_user_id
    ),
    scored_segments AS (
        SELECT 
            sc.id as segment_id,
            sc.topic_slug,
            sc.audio_url,
            sc.audio_duration as duration,
            COALESCE(sc.relevance_score, 0.5) as relevance_score,
            COALESCE((uw.weights->>sc.topic_slug)::int, 50) as user_weight,
            COALESCE(sc.relevance_score, 0.5) * 
                COALESCE((uw.weights->>sc.topic_slug)::int, 50) / 100.0 as final_score
        FROM segment_cache sc
        CROSS JOIN user_weights uw
        WHERE sc.target_date = p_target_date
    )
    SELECT * FROM scored_segments
    ORDER BY final_score DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- TRIGGER: Update timestamp on weights change
-- ============================================

CREATE OR REPLACE FUNCTION update_signal_weights_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_signal_weights_timestamp ON user_signal_weights;
CREATE TRIGGER trigger_update_signal_weights_timestamp
    BEFORE UPDATE ON user_signal_weights
    FOR EACH ROW
    EXECUTE FUNCTION update_signal_weights_timestamp();

-- ============================================
-- GRANT PERMISSIONS
-- ============================================

GRANT SELECT, INSERT, UPDATE ON user_signal_weights TO authenticated;
GRANT USAGE ON SCHEMA public TO authenticated;
