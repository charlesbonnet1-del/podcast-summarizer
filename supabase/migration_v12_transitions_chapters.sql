-- Migration V12: Transitions Cache, Episode Chapters & User History
-- 
-- FEATURES:
-- 1. cached_transitions table for segment transition audio
-- 2. chapters column in episodes for player navigation
-- 3. user_history table for segment deduplication (inventory-first logic)

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
-- USER_HISTORY TABLE (Segment Deduplication)
-- ============================================
-- Tracks which segments have been served to which user
-- Used by the 14+1 selection algorithm to avoid repetition

CREATE TABLE IF NOT EXISTS user_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    segment_id UUID NOT NULL,
    content_hash VARCHAR(64),  -- For quick dedup check
    topic_slug VARCHAR(50),
    served_at TIMESTAMPTZ DEFAULT NOW(),
    episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL,
    
    -- Prevent duplicate entries
    UNIQUE(user_id, content_hash)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_history_user_id 
ON user_history(user_id);

CREATE INDEX IF NOT EXISTS idx_user_history_content_hash 
ON user_history(user_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_user_history_served_at 
ON user_history(served_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_history_topic 
ON user_history(user_id, topic_slug);

-- ============================================
-- ADD RELEVANCE SCORE TO AUDIO_SEGMENTS
-- ============================================

-- Add relevance_score column for sorting
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'audio_segments' AND column_name = 'relevance_score'
    ) THEN
        ALTER TABLE audio_segments ADD COLUMN relevance_score FLOAT DEFAULT 0.5;
    END IF;
END $$;

-- ============================================
-- ADD TOPIC_WEIGHTS TO USERS TABLE
-- ============================================
-- Stores user's topic preferences (0-100 weight per topic)

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'topic_weights'
    ) THEN
        ALTER TABLE users ADD COLUMN topic_weights JSONB DEFAULT '{}';
    END IF;
END $$;

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE cached_transitions IS 'Cache for transition audio between segments';
COMMENT ON TABLE user_history IS 'Tracks segments served to users for deduplication';
COMMENT ON COLUMN user_history.content_hash IS 'Hash of segment content for quick dedup';
COMMENT ON COLUMN user_history.served_at IS 'When segment was served to user';

COMMENT ON COLUMN episodes.chapters IS 'JSON array of chapters with title, start_time, type, topic';
COMMENT ON COLUMN audio_segments.relevance_score IS 'AI-computed relevance score (0-1)';
COMMENT ON COLUMN users.topic_weights IS 'User topic preferences: {"ia": 80, "crypto": 50, ...}';
