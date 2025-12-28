-- Migration V13: Transitions Cache, Episode Chapters & User History
-- Run this in Supabase SQL Editor

-- ============================================
-- 1. CACHED TRANSITIONS TABLE
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

CREATE INDEX IF NOT EXISTS idx_cached_transitions_cache_key 
ON cached_transitions(cache_key);

CREATE INDEX IF NOT EXISTS idx_cached_transitions_topic 
ON cached_transitions(topic);

-- ============================================
-- 2. ADD CHAPTERS COLUMN TO EPISODES
-- ============================================

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'episodes' AND column_name = 'chapters'
    ) THEN
        ALTER TABLE episodes ADD COLUMN chapters JSONB DEFAULT '[]';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_episodes_chapters 
ON episodes USING GIN (chapters);

-- ============================================
-- 3. USER_HISTORY TABLE (Segment Deduplication)
-- ============================================

CREATE TABLE IF NOT EXISTS user_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    content_hash VARCHAR(64),
    topic_slug VARCHAR(50),
    served_at TIMESTAMPTZ DEFAULT NOW(),
    episode_id UUID,
    UNIQUE(user_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_user_history_user_id 
ON user_history(user_id);

CREATE INDEX IF NOT EXISTS idx_user_history_content_hash 
ON user_history(user_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_user_history_served_at 
ON user_history(served_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_history_topic 
ON user_history(user_id, topic_slug);

-- ============================================
-- 4. ADD RELEVANCE SCORE TO AUDIO_SEGMENTS
-- ============================================

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
-- 5. ADD TOPIC_WEIGHTS TO USERS TABLE
-- ============================================

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
-- 6. ADD SOURCE_NAME TO CONTENT_QUEUE
-- ============================================
-- Stores the media name (e.g., "Le Monde", "TechCrunch") 
-- to be used in dialogue prompts instead of guessing from URL

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'content_queue' AND column_name = 'source_name'
    ) THEN
        ALTER TABLE content_queue ADD COLUMN source_name VARCHAR(100);
    END IF;
END $$;

-- ============================================
-- 7. ADD SOURCE_NAME TO AUDIO_SEGMENTS
-- ============================================
-- Persists the media name in cached segments

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'audio_segments' AND column_name = 'source_name'
    ) THEN
        ALTER TABLE audio_segments ADD COLUMN source_name VARCHAR(100);
    END IF;
END $$;
