-- ============================================
-- KEERNEL - Migration V5: Granular Topics
-- ============================================

-- Add display_name and search_keywords to user_interests
ALTER TABLE user_interests 
ADD COLUMN IF NOT EXISTS display_name TEXT;

ALTER TABLE user_interests 
ADD COLUMN IF NOT EXISTS search_keywords TEXT[] DEFAULT '{}';

-- ============================================
-- FIX RLS POLICIES FOR user_interests
-- ============================================

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Users can view own interests" ON user_interests;
DROP POLICY IF EXISTS "Users can insert own interests" ON user_interests;
DROP POLICY IF EXISTS "Users can update own interests" ON user_interests;
DROP POLICY IF EXISTS "Users can delete own interests" ON user_interests;

-- Enable RLS
ALTER TABLE user_interests ENABLE ROW LEVEL SECURITY;

-- Create proper policies
CREATE POLICY "Users can view own interests" ON user_interests
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own interests" ON user_interests
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own interests" ON user_interests
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own interests" ON user_interests
    FOR DELETE USING (auth.uid() = user_id);

-- ============================================
-- CREATE TOPICS REFERENCE TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS topic_definitions (
    id TEXT PRIMARY KEY,
    category_id TEXT NOT NULL,
    category_name TEXT NOT NULL,
    label TEXT NOT NULL,
    keywords TEXT[] NOT NULL,
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

-- Insert topic definitions
INSERT INTO topic_definitions (id, category_id, category_name, label, keywords, icon, sort_order) VALUES
-- IA & Tech
('llm', 'ai_tech', 'IA & Tech', 'LLM & ChatGPT', ARRAY['LLM', 'ChatGPT', 'OpenAI', 'Claude', 'GPT'], '🤖', 1),
('hardware', 'ai_tech', 'IA & Tech', 'Hardware & Chips', ARRAY['GPU', 'NVIDIA', 'Apple Silicon', 'semiconducteurs'], '🤖', 2),
('robotics', 'ai_tech', 'IA & Tech', 'Robotique', ARRAY['robotique', 'robots', 'Tesla Bot', 'Boston Dynamics'], '🤖', 3),

-- Politique
('france', 'politics', 'Politique', 'France', ARRAY['politique France', 'Macron', 'Assemblée nationale'], '🌍', 4),
('usa', 'politics', 'Politique', 'USA', ARRAY['US politics', 'White House', 'Congress', 'Trump', 'Biden'], '🌍', 5),
('international', 'politics', 'Politique', 'International', ARRAY['géopolitique', 'ONU', 'diplomatie', 'G20'], '🌍', 6),

-- Finance
('stocks', 'finance', 'Finance', 'Bourse', ARRAY['CAC 40', 'Wall Street', 'bourse', 'actions'], '📈', 7),
('crypto', 'finance', 'Finance', 'Crypto', ARRAY['Bitcoin', 'Ethereum', 'crypto', 'blockchain'], '📈', 8),
('macro', 'finance', 'Finance', 'Géo-économie', ARRAY['BCE', 'Fed', 'inflation', 'économie mondiale'], '📈', 9),

-- Science
('space', 'science', 'Science', 'Espace', ARRAY['NASA', 'SpaceX', 'espace', 'Mars', 'fusée'], '🔬', 10),
('health', 'science', 'Science', 'Santé', ARRAY['santé', 'médecine', 'biotech', 'vaccin'], '🔬', 11),
('energy', 'science', 'Science', 'Énergie', ARRAY['énergie', 'nucléaire', 'renouvelable', 'climat'], '🔬', 12),

-- Culture
('cinema', 'culture', 'Culture', 'Cinéma & Séries', ARRAY['cinéma', 'Netflix', 'films', 'séries'], '🎬', 13),
('gaming', 'culture', 'Culture', 'Gaming', ARRAY['jeux vidéo', 'PlayStation', 'Nintendo', 'gaming'], '🎬', 14),
('lifestyle', 'culture', 'Culture', 'Lifestyle', ARRAY['lifestyle', 'tendances', 'mode', 'design'], '🎬', 15)

ON CONFLICT (id) DO UPDATE SET
    keywords = EXCLUDED.keywords,
    label = EXCLUDED.label;

-- ============================================
-- INDEX FOR PERFORMANCE
-- ============================================

CREATE INDEX IF NOT EXISTS idx_user_interests_user_id ON user_interests(user_id);
CREATE INDEX IF NOT EXISTS idx_user_interests_keyword ON user_interests(keyword);
