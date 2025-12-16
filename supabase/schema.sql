-- ============================================
-- SINGULAR DAILY - Database Schema
-- ============================================

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. USERS TABLE
-- ============================================
CREATE TABLE public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    telegram_chat_id BIGINT UNIQUE,
    connection_code TEXT UNIQUE,
    default_duration INTEGER DEFAULT 15 CHECK (default_duration BETWEEN 5 AND 30),
    voice_id TEXT DEFAULT 'alloy' CHECK (voice_id IN ('alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer')),
    rss_token UUID DEFAULT uuid_generate_v4() UNIQUE NOT NULL,
    subscription_status TEXT DEFAULT 'free' CHECK (subscription_status IN ('free', 'pro')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster lookups
CREATE INDEX idx_users_telegram_chat_id ON public.users(telegram_chat_id);
CREATE INDEX idx_users_connection_code ON public.users(connection_code);
CREATE INDEX idx_users_rss_token ON public.users(rss_token);

-- ============================================
-- 2. CONTENT QUEUE TABLE
-- ============================================
CREATE TABLE public.content_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN ('youtube', 'article', 'podcast')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
    error_message TEXT,
    processed_content TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for worker queries
CREATE INDEX idx_content_queue_status ON public.content_queue(status);
CREATE INDEX idx_content_queue_user_id ON public.content_queue(user_id);
CREATE INDEX idx_content_queue_created_at ON public.content_queue(created_at DESC);

-- ============================================
-- 3. EPISODES TABLE
-- ============================================
CREATE TABLE public.episodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary_text TEXT,
    audio_url TEXT NOT NULL,
    audio_duration INTEGER, -- Duration in seconds
    sources JSONB DEFAULT '[]'::jsonb, -- Array of source URLs used
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for feed queries
CREATE INDEX idx_episodes_user_id ON public.episodes(user_id);
CREATE INDEX idx_episodes_created_at ON public.episodes(created_at DESC);

-- ============================================
-- 4. ROW LEVEL SECURITY (RLS)
-- ============================================

-- Enable RLS on all tables
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.content_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.episodes ENABLE ROW LEVEL SECURITY;

-- Users policies
CREATE POLICY "Users can view own profile"
    ON public.users FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.users FOR UPDATE
    USING (auth.uid() = id);

-- Content queue policies
CREATE POLICY "Users can view own content"
    ON public.content_queue FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own content"
    ON public.content_queue FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own content"
    ON public.content_queue FOR DELETE
    USING (auth.uid() = user_id);

-- Episodes policies
CREATE POLICY "Users can view own episodes"
    ON public.episodes FOR SELECT
    USING (auth.uid() = user_id);

-- ============================================
-- 5. FUNCTIONS & TRIGGERS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_content_queue_updated_at
    BEFORE UPDATE ON public.content_queue
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to generate 6-digit connection code
CREATE OR REPLACE FUNCTION generate_connection_code()
RETURNS TEXT AS $$
DECLARE
    code TEXT;
    exists_already BOOLEAN;
BEGIN
    LOOP
        -- Generate random 6-digit code
        code := LPAD(FLOOR(RANDOM() * 1000000)::TEXT, 6, '0');
        
        -- Check if code already exists
        SELECT EXISTS(SELECT 1 FROM public.users WHERE connection_code = code) INTO exists_already;
        
        -- Exit loop if code is unique
        EXIT WHEN NOT exists_already;
    END LOOP;
    
    RETURN code;
END;
$$ LANGUAGE plpgsql;

-- Function to handle new user creation
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email, connection_code)
    VALUES (
        NEW.id,
        NEW.email,
        generate_connection_code()
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to auto-create user profile on signup
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================
-- 6. SERVICE ROLE POLICIES (for Python worker)
-- ============================================

-- Allow service role to read all content for processing
CREATE POLICY "Service role can read all content"
    ON public.content_queue FOR SELECT
    TO service_role
    USING (true);

CREATE POLICY "Service role can update all content"
    ON public.content_queue FOR UPDATE
    TO service_role
    USING (true);

CREATE POLICY "Service role can insert episodes"
    ON public.episodes FOR INSERT
    TO service_role
    WITH CHECK (true);

CREATE POLICY "Service role can read users"
    ON public.users FOR SELECT
    TO service_role
    USING (true);

CREATE POLICY "Service role can update users"
    ON public.users FOR UPDATE
    TO service_role
    USING (true);

-- ============================================
-- 7. STORAGE BUCKETS (run in SQL editor)
-- ============================================

-- Note: Storage buckets should be created via Supabase Dashboard
-- or via the Storage API. Here's the structure needed:

-- Bucket: 'episodes' - for MP3 files
-- Bucket: 'feeds' - for RSS XML files

-- After creating buckets, set these policies in the Dashboard:
-- episodes bucket: Public read, authenticated write
-- feeds bucket: Public read (for podcast apps)
