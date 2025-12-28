-- Migration V12: Transitions Cache & Episode Chapters
-- 
-- FEATURES:
-- 1. cached_transitions table for segment transition audio
-- 2. chapters column in episodes for player navigation

-- ============================================
-- CACHED TRANSITIONS TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS cached_transitions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    cache_key VARCHAR(20) NOT NULL UNIQUE,
    text TEXT NOT NULL,
    topic VARCHAR(50),
    audio_url TEXT NOT NULL,
    audio_duration INTEGER DEFAULT 2,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_cached_transitions_cache_key 
ON cached_transitions(cache_key);

CREATE INDEX IF NOT EXISTS idx_cached_transitions_topic 
ON cached_transitions(topic);

-- ============================================
-- ADD CHAPTERS COLUMN TO EPISODES
-- ============================================

-- Add chapters column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'episodes' AND column_name = 'chapters'
    ) THEN
        ALTER TABLE episodes ADD COLUMN chapters JSONB DEFAULT '[]';
    END IF;
END $$;

-- Create index for chapters querying
CREATE INDEX IF NOT EXISTS idx_episodes_chapters 
ON episodes USING GIN (chapters);

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE cached_transitions IS 'Cache for transition audio between segments (e.g., "Passons à l IA...")';
COMMENT ON COLUMN cached_transitions.cache_key IS 'MD5 hash of transition text for lookup';
COMMENT ON COLUMN cached_transitions.text IS 'The spoken transition text';
COMMENT ON COLUMN cached_transitions.topic IS 'Topic/vertical this transition is for';

COMMENT ON COLUMN episodes.chapters IS 'JSON array of chapters with title, start_time, type, topic, url';

-- ============================================
-- SAMPLE DATA (Optional - Pre-populate common transitions)
-- ============================================

-- You can run this separately to pre-generate transitions:
-- INSERT INTO cached_transitions (cache_key, text, topic) VALUES
--   ('abc123', 'Passons à l''intelligence artificielle.', 'ia'),
--   ('def456', 'Direction les cryptomonnaies.', 'crypto')
-- ON CONFLICT (cache_key) DO NOTHING;
