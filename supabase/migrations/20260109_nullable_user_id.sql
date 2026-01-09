-- ============================================
-- Migration: Make user_id nullable in content_queue
-- Purpose: Allow system-generated content (RSS feeds) without a user
-- ============================================

-- 1. Drop the NOT NULL constraint on user_id
ALTER TABLE content_queue ALTER COLUMN user_id DROP NOT NULL;

-- 2. Update RLS policy to allow reading system content (user_id IS NULL)
DROP POLICY IF EXISTS "Users can view own content" ON content_queue;
CREATE POLICY "Users can view own content" ON content_queue
    FOR SELECT
    USING (auth.uid() = user_id OR user_id IS NULL);

-- 3. Allow service role to insert system content
DROP POLICY IF EXISTS "Service role can insert" ON content_queue;
CREATE POLICY "Service role can insert" ON content_queue
    FOR INSERT
    WITH CHECK (true);

-- 4. Allow service role to update
DROP POLICY IF EXISTS "Service role can update" ON content_queue;
CREATE POLICY "Service role can update" ON content_queue
    FOR UPDATE
    USING (true);
