-- ============================================
-- MIGRATION V3: Stitcher Architecture
-- Adds name fields, segment caching, ephemeride
-- ============================================

-- 1. Add first_name and last_name to users
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS first_name TEXT,
ADD COLUMN IF NOT EXISTS last_name TEXT;

-- 2. Table for cached intro segments (mutualized by first_name)
CREATE TABLE IF NOT EXISTS public.cached_intros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name_normalized TEXT NOT NULL UNIQUE,  -- lowercase, no accents
    audio_url TEXT NOT NULL,
    audio_duration INTEGER DEFAULT 0,  -- seconds
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_cached_intros_name ON public.cached_intros(first_name_normalized);

-- 3. Table for daily ephemeride (one per day, shared by all users)
CREATE TABLE IF NOT EXISTS public.daily_ephemeride (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL UNIQUE,  -- YYYY-MM-DD
    script TEXT NOT NULL,  -- The ephemeride text
    audio_url TEXT,
    audio_duration INTEGER DEFAULT 0,
    saint_of_day TEXT,
    historical_fact TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookup by date
CREATE INDEX IF NOT EXISTS idx_ephemeride_date ON public.daily_ephemeride(date);

-- 4. Table for processed content segments (cache by URL + date)
CREATE TABLE IF NOT EXISTS public.processed_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL,
    date DATE NOT NULL,  -- Cache is valid for one day
    segment_type TEXT NOT NULL,  -- 'deep_dive' or 'flash_news'
    title TEXT,
    script TEXT,
    audio_url TEXT,
    audio_duration INTEGER DEFAULT 0,  -- seconds
    word_count INTEGER DEFAULT 0,
    source_name TEXT,  -- e.g., "TechCrunch", "Le Monde"
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint: one cached segment per URL per day
    UNIQUE(url, date)
);

-- Indexes for processed_segments
CREATE INDEX IF NOT EXISTS idx_segments_url_date ON public.processed_segments(url, date);
CREATE INDEX IF NOT EXISTS idx_segments_date ON public.processed_segments(date);

-- 5. Update users.settings to include target_duration
-- Default settings structure: {"voice_id": "alloy", "target_duration": 15}
UPDATE public.users 
SET settings = jsonb_set(
    COALESCE(settings, '{}'::jsonb),
    '{target_duration}',
    '15'::jsonb
)
WHERE settings IS NULL OR NOT (settings ? 'target_duration');

-- 6. Add priority field to content_queue to distinguish manual vs auto
ALTER TABLE public.content_queue
ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'normal';  -- 'high' for manual, 'normal' for auto

-- Update existing manual entries
UPDATE public.content_queue 
SET priority = 'high' 
WHERE source = 'manual';

-- 7. RLS Policies for new tables
ALTER TABLE public.cached_intros ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_ephemeride ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processed_segments ENABLE ROW LEVEL SECURITY;

-- Cached intros: readable by all authenticated, writable by service role only
CREATE POLICY "Cached intros are readable by authenticated users"
ON public.cached_intros FOR SELECT
TO authenticated
USING (true);

-- Daily ephemeride: readable by all authenticated
CREATE POLICY "Ephemeride is readable by authenticated users"
ON public.daily_ephemeride FOR SELECT
TO authenticated
USING (true);

-- Processed segments: readable by all authenticated
CREATE POLICY "Segments are readable by authenticated users"
ON public.processed_segments FOR SELECT
TO authenticated
USING (true);

-- ============================================
-- CLEANUP: Remove old processed segments (older than 7 days)
-- Run this periodically via cron
-- ============================================
-- DELETE FROM public.processed_segments WHERE date < CURRENT_DATE - INTERVAL '7 days';
-- DELETE FROM public.daily_ephemeride WHERE date < CURRENT_DATE - INTERVAL '30 days';
