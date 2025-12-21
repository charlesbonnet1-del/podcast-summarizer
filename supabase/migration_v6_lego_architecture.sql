-- ============================================
-- KEERNEL V2 - LEGO ARCHITECTURE MIGRATION
-- ============================================
-- Objectif : Mutualiser les segments audio pour réduire les coûts TTS par 10x
-- Date : 2025-12-21

-- ============================================
-- 1. PHANTOM USER GUARDRAIL
-- ============================================
-- Ajoute last_listened_at pour tracker l'activité des utilisateurs
-- Si > 3 jours sans écoute, on skip la génération automatique

ALTER TABLE users 
ADD COLUMN IF NOT EXISTS last_listened_at TIMESTAMP WITH TIME ZONE;

-- Index pour requêtes rapides sur l'activité
CREATE INDEX IF NOT EXISTS idx_users_last_listened_at 
ON users(last_listened_at);

-- Initialiser avec created_at pour les utilisateurs existants
UPDATE users 
SET last_listened_at = created_at 
WHERE last_listened_at IS NULL;

-- ============================================
-- 2. NOUVEAUX FORMATS (Flash/Digest)
-- ============================================
-- Remplace les anciens formats 20/30 min par Flash (4min) et Digest (15min)

ALTER TABLE users 
ADD COLUMN IF NOT EXISTS preferred_format VARCHAR(20) DEFAULT 'digest';

-- Contrainte pour formats valides
ALTER TABLE users 
DROP CONSTRAINT IF EXISTS users_format_check;

ALTER TABLE users 
ADD CONSTRAINT users_format_check 
CHECK (preferred_format IN ('flash', 'digest'));

-- Migrer les anciennes durées
UPDATE users 
SET preferred_format = CASE 
    WHEN default_duration <= 5 THEN 'flash'
    ELSE 'digest'
END
WHERE preferred_format IS NULL;

-- ============================================
-- 3. CACHE AUDIO SEGMENTS (LEGO BLOCKS)
-- ============================================
-- Cache les segments audio par topic/date/edition
-- Un segment = 1 article traité = audio réutilisable

CREATE TABLE IF NOT EXISTS audio_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Clé de cache unique
    content_hash VARCHAR(64) NOT NULL,  -- SHA256 du contenu source
    topic_slug VARCHAR(50) NOT NULL,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    edition VARCHAR(20) NOT NULL DEFAULT 'morning',  -- morning/evening
    
    -- Métadonnées source
    source_url TEXT,
    source_title TEXT,
    source_domain VARCHAR(100),
    
    -- Audio généré
    script_text TEXT NOT NULL,
    audio_url TEXT NOT NULL,
    audio_duration INTEGER NOT NULL,  -- seconds
    file_size INTEGER,  -- bytes
    
    -- Stats d'utilisation
    use_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '7 days'),
    
    -- Contrainte d'unicité : un seul segment par hash/date/edition
    UNIQUE(content_hash, date, edition)
);

-- Index pour recherche rapide
CREATE INDEX IF NOT EXISTS idx_audio_segments_lookup 
ON audio_segments(topic_slug, date, edition);

CREATE INDEX IF NOT EXISTS idx_audio_segments_hash 
ON audio_segments(content_hash);

CREATE INDEX IF NOT EXISTS idx_audio_segments_expires 
ON audio_segments(expires_at);

-- ============================================
-- 4. TABLE POUR INTRO/OUTRO CACHE
-- ============================================
-- Les intros personnalisées sont déjà cachées dans cached_intros
-- On ajoute juste les outros mutualisés

CREATE TABLE IF NOT EXISTS cached_outros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    outro_type VARCHAR(20) NOT NULL DEFAULT 'standard',  -- standard, weekend, holiday
    audio_url TEXT NOT NULL,
    audio_duration INTEGER NOT NULL,
    script_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(outro_type)
);

-- ============================================
-- 5. EPISODE COMPOSITION (Assemblage Lego)
-- ============================================
-- Track quels segments composent chaque épisode

CREATE TABLE IF NOT EXISTS episode_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    segment_id UUID REFERENCES audio_segments(id) ON DELETE SET NULL,
    segment_type VARCHAR(20) NOT NULL,  -- intro, news, outro
    position INTEGER NOT NULL,  -- ordre dans l'épisode
    duration INTEGER,  -- seconds
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(episode_id, position)
);

CREATE INDEX IF NOT EXISTS idx_episode_segments_episode 
ON episode_segments(episode_id);

-- ============================================
-- 6. FONCTION : Nettoyage des segments expirés
-- ============================================

CREATE OR REPLACE FUNCTION cleanup_expired_segments()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audio_segments 
    WHERE expires_at < NOW()
    AND use_count = 0;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 7. FONCTION : Vérifier utilisateur actif
-- ============================================

CREATE OR REPLACE FUNCTION is_user_active(p_user_id UUID, p_days INTEGER DEFAULT 3)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM users 
        WHERE id = p_user_id 
        AND (
            last_listened_at IS NULL 
            OR last_listened_at > NOW() - (p_days || ' days')::INTERVAL
        )
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 8. TRIGGER : Mettre à jour last_listened_at
-- ============================================
-- Appelé quand un utilisateur joue un épisode

CREATE OR REPLACE FUNCTION update_last_listened()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE users 
    SET last_listened_at = NOW()
    WHERE id = NEW.user_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Note: Ce trigger serait sur une table episode_plays
-- Pour l'instant, on le fait côté application

-- ============================================
-- 9. STATS VIEW
-- ============================================

CREATE OR REPLACE VIEW v_segment_stats AS
SELECT 
    date,
    edition,
    COUNT(*) as total_segments,
    SUM(use_count) as total_uses,
    SUM(audio_duration) as total_duration_sec,
    ROUND(AVG(audio_duration)) as avg_duration_sec
FROM audio_segments
GROUP BY date, edition
ORDER BY date DESC;

-- ============================================
-- 10. CLEANUP OLD DATA
-- ============================================
-- Supprimer les anciens champs inutiles (optionnel, à exécuter manuellement)

-- ALTER TABLE users DROP COLUMN IF EXISTS default_duration;
-- (Garder pour migration douce, supprimer plus tard)

COMMENT ON TABLE audio_segments IS 'Cache des segments audio mutualisés (architecture Lego V2)';
COMMENT ON COLUMN users.last_listened_at IS 'Dernière écoute pour le Phantom User Guardrail';
COMMENT ON COLUMN users.preferred_format IS 'Format préféré: flash (4min) ou digest (15min)';
