-- ============================================
-- SINGULAR DAILY - V-MVP Migration
-- Table: user_interests (Sourcing Dynamique)
-- ============================================

-- 1. Créer la table user_interests
CREATE TABLE IF NOT EXISTS public.user_interests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Un utilisateur ne peut pas avoir le même mot-clé deux fois
    UNIQUE(user_id, keyword)
);

-- 2. Index pour les requêtes rapides
CREATE INDEX IF NOT EXISTS idx_user_interests_user_id ON public.user_interests(user_id);
CREATE INDEX IF NOT EXISTS idx_user_interests_keyword ON public.user_interests(keyword);

-- 3. Row Level Security
ALTER TABLE public.user_interests ENABLE ROW LEVEL SECURITY;

-- Politique : Les utilisateurs peuvent voir leurs propres intérêts
CREATE POLICY "Users can view own interests"
    ON public.user_interests FOR SELECT
    USING (auth.uid() = user_id);

-- Politique : Les utilisateurs peuvent ajouter leurs propres intérêts
CREATE POLICY "Users can insert own interests"
    ON public.user_interests FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Politique : Les utilisateurs peuvent supprimer leurs propres intérêts
CREATE POLICY "Users can delete own interests"
    ON public.user_interests FOR DELETE
    USING (auth.uid() = user_id);

-- Politique : Le service role peut tout faire (pour le bot Python)
CREATE POLICY "Service role full access to interests"
    ON public.user_interests FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 4. Ajouter une colonne 'source' à content_queue pour distinguer manuel vs auto
ALTER TABLE public.content_queue 
ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual' 
CHECK (source IN ('manual', 'google_news', 'rss'));

-- 5. Ajouter une colonne 'keyword' à content_queue pour tracer l'origine
ALTER TABLE public.content_queue 
ADD COLUMN IF NOT EXISTS keyword TEXT;

-- 6. Ajouter une colonne 'edition' pour morning/evening
ALTER TABLE public.content_queue 
ADD COLUMN IF NOT EXISTS edition TEXT 
CHECK (edition IN ('morning', 'evening', NULL));

-- ============================================
-- Vérification
-- ============================================
-- Exécute cette requête pour vérifier que tout est OK :
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
