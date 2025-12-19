-- ============================================
-- MIGRATION V3: Stitcher Architecture
-- Adds name fields, segment caching, ephemeride, international support
-- ============================================

-- 1. Add columns to users table
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS first_name TEXT,
ADD COLUMN IF NOT EXISTS last_name TEXT,
ADD COLUMN IF NOT EXISTS target_duration INTEGER DEFAULT 15,
ADD COLUMN IF NOT EXISTS include_international BOOLEAN DEFAULT false;

-- 2. Table for cached intro segments (mutualized by first_name)
CREATE TABLE IF NOT EXISTS public.cached_intros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name_normalized TEXT NOT NULL UNIQUE,  -- lowercase, no accents
    audio_url TEXT NOT NULL,
    audio_duration INTEGER DEFAULT 0,  -- seconds
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cached_intros_name ON public.cached_intros(first_name_normalized);

-- 3. Table for daily ephemeride (one per day, shared by all users)
CREATE TABLE IF NOT EXISTS public.daily_ephemeride (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL UNIQUE,
    script TEXT NOT NULL,
    audio_url TEXT,
    audio_duration INTEGER DEFAULT 0,
    saint_of_day TEXT,
    historical_fact TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ephemeride_date ON public.daily_ephemeride(date);

-- 4. Table for processed content segments (cache by URL + date)
-- Mutualized: same URL processed once per day, shared between users
CREATE TABLE IF NOT EXISTS public.processed_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL,
    date DATE NOT NULL,
    segment_type TEXT NOT NULL,  -- 'deep_dive' or 'flash_news'
    title TEXT,
    script TEXT,
    audio_url TEXT,
    audio_duration INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    source_name TEXT,
    source_country TEXT DEFAULT 'FR',  -- FR, US, UK, DE, ES, IT
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(url, date)
);

CREATE INDEX IF NOT EXISTS idx_segments_url_date ON public.processed_segments(url, date);
CREATE INDEX IF NOT EXISTS idx_segments_date ON public.processed_segments(date);

-- 5. Add priority field to content_queue
ALTER TABLE public.content_queue
ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'normal',
ADD COLUMN IF NOT EXISTS source_country TEXT DEFAULT 'FR';

-- Update existing manual entries to high priority
UPDATE public.content_queue 
SET priority = 'high' 
WHERE source = 'manual' AND (priority IS NULL OR priority = 'normal');

-- 6. RLS Policies
ALTER TABLE public.cached_intros ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_ephemeride ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processed_segments ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (idempotent)
DROP POLICY IF EXISTS "Cached intros are readable by authenticated users" ON public.cached_intros;
DROP POLICY IF EXISTS "Ephemeride is readable by authenticated users" ON public.daily_ephemeride;
DROP POLICY IF EXISTS "Segments are readable by authenticated users" ON public.processed_segments;

CREATE POLICY "Cached intros are readable by authenticated users"
ON public.cached_intros FOR SELECT TO authenticated USING (true);

CREATE POLICY "Ephemeride is readable by authenticated users"
ON public.daily_ephemeride FOR SELECT TO authenticated USING (true);

CREATE POLICY "Segments are readable by authenticated users"
ON public.processed_segments FOR SELECT TO authenticated USING (true);

-- 7. Cleanup function (run via cron)
-- DELETE FROM public.processed_segments WHERE date < CURRENT_DATE - INTERVAL '7 days';
-- DELETE FROM public.daily_ephemeride WHERE date < CURRENT_DATE - INTERVAL '30 days';
