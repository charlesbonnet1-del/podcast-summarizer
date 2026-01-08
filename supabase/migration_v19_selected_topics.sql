-- Migration V19: Simplified Topic Selection System
-- ================================================
--
-- Replaces percentage-based weighting (0-100%) with simple topic selection.
-- Users now pick 5-6 topics they care about.
-- Podcasts contain top 3 clusters by score from their selected topics.

-- ============================================
-- 1. ADD selected_topics COLUMN TO USERS
-- ============================================

-- Add selected_topics as TEXT array
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'selected_topics'
    ) THEN
        ALTER TABLE users ADD COLUMN selected_topics TEXT[] DEFAULT '{}';
    END IF;
END $$;

-- Add comment explaining the new system
COMMENT ON COLUMN users.selected_topics IS 'V19: Array of topic slugs user wants in their podcast. Replaces weighted topic_weights system.';

-- ============================================
-- 2. ADD onboarding_completed FLAG
-- ============================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'onboarding_completed'
    ) THEN
        ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

COMMENT ON COLUMN users.onboarding_completed IS 'V19: True after user selects their topics in onboarding';

-- ============================================
-- 3. ADD email_digest_enabled FLAG
-- ============================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'email_digest_enabled'
    ) THEN
        ALTER TABLE users ADD COLUMN email_digest_enabled BOOLEAN DEFAULT TRUE;
    END IF;
END $$;

COMMENT ON COLUMN users.email_digest_enabled IS 'V19: Enable daily email digest with podcast link and summary';

-- ============================================
-- 4. MIGRATE EXISTING USERS
-- ============================================

-- For existing users with topic_weights, convert to selected_topics
-- Take topics with weight >= 30% (old MEDIUM and HIGH priority)
UPDATE users
SET selected_topics = (
    SELECT ARRAY_AGG(key)
    FROM jsonb_each_text(topic_weights)
    WHERE value::int >= 30
)
WHERE topic_weights IS NOT NULL
  AND topic_weights != '{}'::jsonb
  AND (selected_topics IS NULL OR selected_topics = '{}');

-- Mark existing users with topics as onboarding complete
UPDATE users
SET onboarding_completed = TRUE
WHERE selected_topics IS NOT NULL
  AND array_length(selected_topics, 1) >= 5;

-- ============================================
-- 5. AVAILABLE TOPICS REFERENCE
-- ============================================

-- Reference list of valid topic slugs (same as TOPICS in cluster_pipeline.py):
-- Tech: ia, cyber, deep_tech
-- Science: health, space, energy
-- Economics: crypto, macro, deals
-- World: asia, regulation, resources
-- Influence: info, attention, persuasion
-- General: general (requires authority co-clustering)

-- ============================================
-- 6. INDEXES
-- ============================================

-- Index for filtering users by onboarding status
CREATE INDEX IF NOT EXISTS idx_users_onboarding_completed
ON users(onboarding_completed);

-- GIN index for selected_topics array queries
CREATE INDEX IF NOT EXISTS idx_users_selected_topics
ON users USING GIN(selected_topics);

-- ============================================
-- 7. RLS POLICIES (ensure users can update their own)
-- ============================================

-- Already covered by existing "Users can update own profile" policy

-- ============================================
-- 8. ADD digest_sent_at TO EPISODES
-- ============================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'episodes' AND column_name = 'digest_sent_at'
    ) THEN
        ALTER TABLE episodes ADD COLUMN digest_sent_at TIMESTAMPTZ DEFAULT NULL;
    END IF;
END $$;

COMMENT ON COLUMN episodes.digest_sent_at IS 'V19: Timestamp when email digest was sent for this episode';

-- Index for finding unsent digests
CREATE INDEX IF NOT EXISTS idx_episodes_digest_sent_at
ON episodes(created_at, digest_sent_at)
WHERE digest_sent_at IS NULL;

-- ============================================
-- VERIFICATION
-- ============================================

-- Run this to verify migration:
-- SELECT id, email, selected_topics, onboarding_completed, email_digest_enabled FROM users LIMIT 10;
