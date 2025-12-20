-- ============================================
-- KEERNEL - Migration V4: Trusted Sources & Verticals
-- ============================================

-- ============================================
-- 1. UPDATE USERS TABLE
-- ============================================

-- Add selected_verticals JSONB column
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS selected_verticals JSONB DEFAULT '{"ai_tech": true, "politics": true, "finance": true, "science": true, "culture": true}'::jsonb;

-- Ensure other columns exist
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS target_duration INTEGER DEFAULT 20;
ALTER TABLE users ADD COLUMN IF NOT EXISTS include_international BOOLEAN DEFAULT false;

-- ============================================
-- 2. CREATE TRUSTED_SOURCES TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS trusted_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Source identity (unique per user)
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source_identity TEXT NOT NULL,  -- @Veritasium, lemonde.fr, TheDailyPodcast
    
    -- Metadata
    source_type TEXT NOT NULL DEFAULT 'web',  -- youtube, web, podcast, twitter
    display_name TEXT,  -- Human-readable name
    
    -- Scoring
    reliability_score INTEGER DEFAULT 10,  -- Starts at 10, increases with usage
    times_used INTEGER DEFAULT 1,
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint per user
    UNIQUE(user_id, source_identity)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_trusted_sources_user ON trusted_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_trusted_sources_score ON trusted_sources(reliability_score DESC);

-- ============================================
-- 3. UPDATE PROCESSED_SEGMENTS TABLE
-- ============================================

-- Add language column if not exists
ALTER TABLE processed_segments 
ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'fr';

-- Add source_identity reference
ALTER TABLE processed_segments 
ADD COLUMN IF NOT EXISTS source_identity TEXT;

-- ============================================
-- 4. CREATE VERTICALS REFERENCE TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS verticals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_fr TEXT NOT NULL,
    description TEXT,
    keywords JSONB NOT NULL,  -- Search keywords per language
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

-- Insert the 5 Alpha Verticals
INSERT INTO verticals (id, name, name_fr, description, keywords, icon, sort_order) VALUES
('ai_tech', 'AI & Tech', 'IA & Tech', 'LLM, Hardware, Robotique, Startups', 
 '{"fr": ["intelligence artificielle", "LLM", "robotique", "startup tech", "OpenAI", "GPU"],
   "en": ["artificial intelligence", "LLM", "robotics", "tech startup", "OpenAI", "GPU"],
   "de": ["künstliche Intelligenz", "Robotik", "Tech-Startup"],
   "es": ["inteligencia artificial", "robótica", "startup tecnológica"],
   "it": ["intelligenza artificiale", "robotica", "startup tech"]}'::jsonb,
 '🤖', 1),

('politics', 'Politics & World', 'Politique & Monde', 'France, USA, Géopolitique, Diplomatie',
 '{"fr": ["politique France", "élections", "diplomatie", "géopolitique"],
   "en": ["US politics", "elections", "diplomacy", "geopolitics", "world news"],
   "de": ["Politik Deutschland", "Wahlen", "Diplomatie"],
   "es": ["política España", "elecciones", "diplomacia"],
   "it": ["politica Italia", "elezioni", "diplomazia"]}'::jsonb,
 '🌍', 2),

('finance', 'Finance & Markets', 'Finance & Marchés', 'Bourse, Crypto, Macro-économie',
 '{"fr": ["bourse Paris", "CAC 40", "crypto", "économie", "BCE"],
   "en": ["stock market", "Wall Street", "crypto", "Fed", "economy"],
   "de": ["Börse", "DAX", "Krypto", "Wirtschaft"],
   "es": ["bolsa", "IBEX", "criptomonedas", "economía"],
   "it": ["borsa", "FTSE MIB", "criptovalute", "economia"]}'::jsonb,
 '📈', 3),

('science', 'Science & Health', 'Science & Santé', 'Espace, Biotech, Énergie, Climat',
 '{"fr": ["espace", "NASA", "biotech", "énergie", "climat", "santé"],
   "en": ["space", "NASA", "SpaceX", "biotech", "energy", "climate", "health"],
   "de": ["Weltraum", "Biotech", "Energie", "Klima", "Gesundheit"],
   "es": ["espacio", "biotecnología", "energía", "clima", "salud"],
   "it": ["spazio", "biotecnologia", "energia", "clima", "salute"]}'::jsonb,
 '🔬', 4),

('culture', 'Culture & Entertainment', 'Culture & Divertissement', 'Cinéma, Séries, Gaming, Digital Culture',
 '{"fr": ["cinéma", "séries Netflix", "jeux vidéo", "streaming", "YouTube"],
   "en": ["movies", "Netflix series", "gaming", "streaming", "YouTube"],
   "de": ["Kino", "Serien", "Gaming", "Streaming"],
   "es": ["cine", "series", "videojuegos", "streaming"],
   "it": ["cinema", "serie TV", "videogiochi", "streaming"]}'::jsonb,
 '🎬', 5)

ON CONFLICT (id) DO UPDATE SET
    keywords = EXCLUDED.keywords,
    name_fr = EXCLUDED.name_fr;

-- ============================================
-- 5. UPDATE CONTENT_QUEUE FOR VERTICALS
-- ============================================

ALTER TABLE content_queue 
ADD COLUMN IF NOT EXISTS vertical_id TEXT REFERENCES verticals(id);

-- ============================================
-- 6. RLS POLICIES
-- ============================================

-- Enable RLS on trusted_sources
ALTER TABLE trusted_sources ENABLE ROW LEVEL SECURITY;

-- Users can only see their own trusted sources
CREATE POLICY "Users can view own trusted sources" ON trusted_sources
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own trusted sources" ON trusted_sources
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own trusted sources" ON trusted_sources
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own trusted sources" ON trusted_sources
    FOR DELETE USING (auth.uid() = user_id);

-- ============================================
-- 7. FUNCTION TO UPDATE SOURCE SCORE
-- ============================================

CREATE OR REPLACE FUNCTION increment_source_score(
    p_user_id UUID,
    p_source_identity TEXT,
    p_source_type TEXT DEFAULT 'web',
    p_display_name TEXT DEFAULT NULL
) RETURNS void AS $$
BEGIN
    INSERT INTO trusted_sources (user_id, source_identity, source_type, display_name, reliability_score, times_used)
    VALUES (p_user_id, p_source_identity, p_source_type, p_display_name, 15, 1)
    ON CONFLICT (user_id, source_identity) DO UPDATE SET
        reliability_score = trusted_sources.reliability_score + 5,
        times_used = trusted_sources.times_used + 1,
        last_used_at = NOW(),
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
