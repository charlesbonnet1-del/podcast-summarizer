-- Migration: Push Notifications Subscriptions
-- Creates table to store Web Push subscription tokens

-- ============================================
-- PUSH SUBSCRIPTIONS TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Web Push subscription data
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,        -- Public key for encryption
    auth TEXT NOT NULL,          -- Auth secret
    
    -- Metadata
    user_agent TEXT,             -- Browser/device info
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint on endpoint (one subscription per browser)
    UNIQUE(endpoint)
);

-- Index for fast lookup by user
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id 
ON push_subscriptions(user_id);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================

ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;

-- Users can only see their own subscriptions
CREATE POLICY "Users can view own push subscriptions"
ON push_subscriptions FOR SELECT
USING (auth.uid() = user_id);

-- Users can add their own subscriptions
CREATE POLICY "Users can insert own push subscriptions"
ON push_subscriptions FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Users can update their own subscriptions
CREATE POLICY "Users can update own push subscriptions"
ON push_subscriptions FOR UPDATE
USING (auth.uid() = user_id);

-- Users can delete their own subscriptions
CREATE POLICY "Users can delete own push subscriptions"
ON push_subscriptions FOR DELETE
USING (auth.uid() = user_id);

-- ============================================
-- TRIGGER: Update timestamp
-- ============================================

CREATE OR REPLACE FUNCTION update_push_subscription_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_push_subscription_timestamp ON push_subscriptions;
CREATE TRIGGER trigger_update_push_subscription_timestamp
    BEFORE UPDATE ON push_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_push_subscription_timestamp();

-- ============================================
-- PERMISSIONS
-- ============================================

GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO authenticated;

-- ============================================
-- SERVICE ROLE ACCESS (for backend notifications)
-- ============================================

-- Allow service role to read all subscriptions (for sending notifications)
CREATE POLICY "Service role can read all subscriptions"
ON push_subscriptions FOR SELECT
TO service_role
USING (true);
