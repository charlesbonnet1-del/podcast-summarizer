-- ============================================
-- KEERNEL V3 - Signal Detection System
-- Clean migration: drops old tables, creates new structure
-- ============================================

-- ============================================
-- PART 1: CLEANUP OLD TABLES
-- ============================================

-- Drop old tables we don't need anymore
DROP TABLE IF EXISTS daily_briefings CASCADE;
DROP TABLE IF EXISTS cluster_summaries CASCADE;
DROP TABLE IF EXISTS user_favorites CASCADE;
DROP TABLE IF EXISTS daily_clusters CASCADE;
DROP TABLE IF EXISTS news_embeddings CASCADE;
DROP TABLE IF EXISTS content_queue CASCADE;
DROP TABLE IF EXISTS episodes CASCADE;
DROP TABLE IF EXISTS podcast_episodes CASCADE;
DROP TABLE IF EXISTS clusters CASCADE;
DROP TABLE IF EXISTS articles CASCADE;
DROP TABLE IF EXISTS prompt_templates CASCADE;
DROP TABLE IF EXISTS pipeline_params CASCADE;

-- Drop old functions
DROP FUNCTION IF EXISTS get_todays_summaries CASCADE;
DROP FUNCTION IF EXISTS get_user_favorites CASCADE;
DROP FUNCTION IF EXISTS toggle_favorite CASCADE;
DROP FUNCTION IF EXISTS find_similar_articles CASCADE;
DROP FUNCTION IF EXISTS get_topic_centroid CASCADE;
DROP FUNCTION IF EXISTS cleanup_old_embeddings CASCADE;

-- ============================================
-- PART 2: EXTENSIONS
-- ============================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================
-- PART 3: SOURCES TABLE
-- Reference table for all news sources
-- ============================================

CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identification
    name TEXT UNIQUE NOT NULL,
    url_rss TEXT NOT NULL,
    
    -- Classification
    topic TEXT NOT NULL,  -- ia, macro, asia
    tier TEXT NOT NULL CHECK (tier IN ('authority', 'generalist', 'corporate')),
    language TEXT DEFAULT 'en',
    
    -- Quality metrics
    score INTEGER DEFAULT 50 CHECK (score BETWEEN 0 AND 100),
    priority INTEGER DEFAULT 1,  -- 1=active, 0=disabled
    
    -- Baseline stats (updated daily)
    avg_articles_per_day FLOAT DEFAULT 0,
    last_baseline_update TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sources_topic ON sources(topic);
CREATE INDEX idx_sources_tier ON sources(tier);
CREATE INDEX idx_sources_priority ON sources(priority);

-- ============================================
-- PART 4: ARTICLES TABLE
-- All fetched articles with embeddings
-- ============================================

CREATE TABLE articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Source reference
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    source_name TEXT,
    source_tier TEXT,
    
    -- Content
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    content TEXT,  -- Full text for embedding (up to 6000 chars)
    
    -- Classification
    topic TEXT NOT NULL,
    classified_topic TEXT,  -- After LLM classification (if generalist)
    classification_method TEXT,  -- 'passthrough' or 'llm'
    
    -- Embedding
    embedding vector(1536),
    embedding_text TEXT,  -- What was embedded (for debugging)
    
    -- Clustering
    cluster_id UUID,  -- Which cluster this belongs to
    
    -- Timing
    published_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_articles_topic ON articles(topic);
CREATE INDEX idx_articles_cluster ON articles(cluster_id);
CREATE INDEX idx_articles_first_seen ON articles(first_seen_at DESC);
CREATE INDEX idx_articles_published ON articles(published_at DESC);
CREATE INDEX idx_articles_url ON articles(url);

-- Vector similarity index
CREATE INDEX idx_articles_embedding ON articles 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- ============================================
-- PART 5: CLUSTERS TABLE
-- Groups of similar articles
-- ============================================

CREATE TABLE clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identification
    topic TEXT NOT NULL,
    name TEXT,  -- Auto-generated from article titles
    
    -- Embedding
    centroid vector(1536),  -- Average embedding of articles
    
    -- Stats
    article_count INTEGER DEFAULT 0,
    authority_count INTEGER DEFAULT 0,
    generalist_count INTEGER DEFAULT 0,
    corporate_count INTEGER DEFAULT 0,
    source_names TEXT[],  -- List of unique sources
    
    -- History for velocity calculation
    -- JSON: {"2025-01-01": 3, "2025-01-02": 5, ...}
    article_count_history JSONB DEFAULT '{}'::jsonb,
    
    -- Timing
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_article_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_clusters_topic ON clusters(topic);
CREATE INDEX idx_clusters_last_article ON clusters(last_article_at DESC);

-- Vector similarity index for cluster matching
CREATE INDEX idx_clusters_centroid ON clusters 
USING ivfflat (centroid vector_cosine_ops)
WITH (lists = 50);

-- ============================================
-- PART 6: SIGNALS TABLE
-- Detected anomalies / breaking news
-- ============================================

CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identification
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT UNIQUE,
    
    -- Cluster source
    cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
    article_ids UUID[],
    
    -- Velocity metrics
    velocity_score FLOAT,  -- x times baseline
    velocity_details JSONB,  -- {"baseline": 2.1, "current": 12, "window_hours": 24}
    
    -- Quality metrics
    source_quality_score FLOAT,
    source_mix JSONB,  -- {"authority": 2, "generalist": 5, "corporate": 1}
    novelty_score FLOAT,  -- New cluster vs existing
    cross_topic_score FLOAT,  -- Detected in multiple topics?
    
    -- Final score
    total_score INTEGER CHECK (total_score BETWEEN 0 AND 100),
    score_breakdown JSONB,
    
    -- Status
    status TEXT DEFAULT 'detected' CHECK (status IN ('detected', 'sent', 'confirmed', 'dismissed')),
    severity TEXT DEFAULT 'digest' CHECK (severity IN ('log', 'digest', 'alert', 'breaking')),
    
    -- Content (generated)
    summary TEXT,
    analysis TEXT,  -- Perplexity enrichment
    audio_url TEXT,
    
    -- Enrichment from Perplexity
    hook TEXT,
    thesis TEXT,
    antithesis TEXT,
    key_data TEXT,
    
    -- Timing
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    
    -- Validation (filled later)
    mainstream_coverage_at TIMESTAMPTZ,
    lead_time_hours FLOAT,
    was_confirmed BOOLEAN,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_signals_topic ON signals(topic);
CREATE INDEX idx_signals_status ON signals(status);
CREATE INDEX idx_signals_severity ON signals(severity);
CREATE INDEX idx_signals_detected ON signals(detected_at DESC);
CREATE INDEX idx_signals_score ON signals(total_score DESC);

-- ============================================
-- PART 7: SIGNAL FEEDBACK TABLE
-- User ratings for learning
-- ============================================

CREATE TABLE signal_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID REFERENCES signals(id) ON DELETE CASCADE,
    
    -- Feedback
    rating TEXT CHECK (rating IN ('useful', 'not_useful', 'acted_on')),
    comment TEXT,
    
    -- Context at feedback time
    hours_after_signal FLOAT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feedback_signal ON signal_feedback(signal_id);
CREATE INDEX idx_feedback_rating ON signal_feedback(rating);

-- ============================================
-- PART 8: SIGNAL THRESHOLDS TABLE
-- Adaptive thresholds per topic
-- ============================================

CREATE TABLE signal_thresholds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic TEXT UNIQUE NOT NULL,
    
    -- Current thresholds
    min_velocity FLOAT DEFAULT 5.0,
    min_score INTEGER DEFAULT 60,
    min_authority_sources INTEGER DEFAULT 1,
    min_total_sources INTEGER DEFAULT 3,
    
    -- Recommended (calculated from feedback)
    recommended_velocity FLOAT,
    recommended_score INTEGER,
    recommendation_confidence FLOAT,  -- 0-1
    
    -- Stats
    signals_sent_30d INTEGER DEFAULT 0,
    precision_30d FLOAT,
    
    -- Timestamps
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert defaults
INSERT INTO signal_thresholds (topic) VALUES ('ia'), ('macro'), ('asia')
ON CONFLICT (topic) DO NOTHING;

-- ============================================
-- PART 9: ARTICLE VELOCITY TABLE
-- Daily/hourly aggregations for baseline
-- ============================================

CREATE TABLE article_velocity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Aggregation key
    topic TEXT NOT NULL,
    date DATE NOT NULL,
    hour INTEGER,  -- 0-23, NULL for daily aggregation
    
    -- Counts
    article_count INTEGER DEFAULT 0,
    authority_count INTEGER DEFAULT 0,
    generalist_count INTEGER DEFAULT 0,
    corporate_count INTEGER DEFAULT 0,
    
    -- Unique sources active
    active_sources INTEGER DEFAULT 0,
    
    UNIQUE(topic, date, hour)
);

CREATE INDEX idx_velocity_topic_date ON article_velocity(topic, date DESC);

-- ============================================
-- PART 10: PROMPT TEMPLATES (keep for lab)
-- ============================================

CREATE TABLE prompt_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    template TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert defaults
INSERT INTO prompt_templates (name, template, description) VALUES
('classification', 'You are a news classifier. Classify this article into ONE of these topics, or "discard" if not relevant.

TOPICS:
- ia: Artificial Intelligence, Machine Learning, LLMs, AI companies, AI research
- macro: Geopolitics, Economics, Finance, Markets, Central banks, Trade
- asia: News specifically about Asia (China, Japan, Korea, India, Southeast Asia)

ARTICLE:
Title: {title}
Description: {description}
Source: {source_name}

Respond with ONLY the topic ID (ia, macro, asia) or "discard". Nothing else.', 'Classification prompt'),

('summary', 'Tu es analyste d''intelligence économique.

SUJET: {topic}
ARTICLES:
{articles}

CONTEXTE:
{context}

Écris un briefing structuré:

## [Titre accrocheur]

**Points clés:**
• [Point 1 avec données précises]
• [Point 2]
• [Point 3]

**Pourquoi c''est important:**
[Un paragraphe]

**Sources:** {sources}', 'Summary prompt'),

('dialogue', 'Tu es scripteur de podcast. Écris un DIALOGUE de {word_count} mots entre deux hôtes.

## SYNTHÈSE À TRANSFORMER EN DIALOGUE
**Sujet**: {theme}
**Accroche**: {hook}
**Thèse (fait principal)**: {thesis}
**Antithèse (nuances/contre-arguments)**: {antithesis}
**Données clés**: {key_data}
**Sources**: {sources}

## LES HÔTES
- [B] L''ANALYSTE (voix masculine) = Présente la THÈSE avec les données clés
- [A] LA SCEPTIQUE (voix féminine) = Apporte l''ANTITHÈSE et les nuances

## RÈGLES ABSOLUES
⚠️ PAS DE TICS: "Tu vois", "Écoute", "Attends", "En fait", "C''est intéressant"
⚠️ STYLE DENSE: Chaque phrase apporte de l''information

## FORMAT
[B]
(expose la thèse avec données)

[A]
(apporte l''antithèse ou nuance)

## STRUCTURE OBLIGATOIRE
1. [B] ouvre avec l''accroche et la thèse principale + données
2. [A] challenge avec l''antithèse ou demande une précision
3. [B] répond avec des données complémentaires
4. [A] apporte une nuance finale ou perspective
5. [B] CONCLUT avec une synthèse

Minimum 6 répliques. Cite les sources naturellement.

## GÉNÈRE LE DIALOGUE ({word_count} mots):', 'Dialogue podcast prompt')

ON CONFLICT (name) DO UPDATE SET 
    template = EXCLUDED.template,
    description = EXCLUDED.description,
    updated_at = NOW();

-- ============================================
-- PART 11: PIPELINE PARAMS (keep for lab)
-- ============================================

CREATE TABLE pipeline_params (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    params JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO pipeline_params (params, description) VALUES
('{
    "max_articles_per_source": 10,
    "max_age_days_generalist": 3,
    "max_age_days_corporate": 7,
    "dbscan_eps": 0.65,
    "dbscan_min_samples": 2,
    "min_authority_sources": 1,
    "min_generalist_sources": 5,
    "max_corporate_per_cluster": 1,
    "tier_multipliers": {
        "authority": 2.0,
        "corporate": 1.5,
        "generalist": 1.0
    },
    "velocity_threshold": 5.0,
    "velocity_window_hours": 24,
    "signal_min_score": 60
}', 'Default pipeline parameters with signal detection')
ON CONFLICT DO NOTHING;

-- ============================================
-- PART 12: HELPER FUNCTIONS
-- ============================================

-- Calculate velocity for a topic/cluster
CREATE OR REPLACE FUNCTION calculate_velocity(
    p_topic TEXT,
    p_window_hours INTEGER DEFAULT 24
)
RETURNS TABLE (
    current_count INTEGER,
    baseline_avg FLOAT,
    velocity FLOAT
) AS $$
DECLARE
    v_current INTEGER;
    v_baseline FLOAT;
BEGIN
    -- Count articles in current window
    SELECT COUNT(*) INTO v_current
    FROM articles
    WHERE topic = p_topic
      AND first_seen_at > NOW() - (p_window_hours || ' hours')::INTERVAL;
    
    -- Calculate 7-day baseline (excluding today)
    SELECT COALESCE(AVG(article_count), 1) INTO v_baseline
    FROM article_velocity
    WHERE topic = p_topic
      AND date < CURRENT_DATE
      AND date >= CURRENT_DATE - 7;
    
    -- Avoid division by zero
    IF v_baseline < 0.1 THEN
        v_baseline := 0.1;
    END IF;
    
    RETURN QUERY SELECT 
        v_current,
        v_baseline,
        (v_current::FLOAT / v_baseline)::FLOAT;
END;
$$ LANGUAGE plpgsql;

-- Find or create cluster for an article
CREATE OR REPLACE FUNCTION find_nearest_cluster(
    p_embedding vector(1536),
    p_topic TEXT,
    p_threshold FLOAT DEFAULT 0.35  -- cosine distance threshold
)
RETURNS UUID AS $$
DECLARE
    v_cluster_id UUID;
    v_distance FLOAT;
BEGIN
    -- Find nearest cluster by centroid
    SELECT id, centroid <=> p_embedding INTO v_cluster_id, v_distance
    FROM clusters
    WHERE topic = p_topic
      AND last_article_at > NOW() - INTERVAL '7 days'  -- Only recent clusters
    ORDER BY centroid <=> p_embedding
    LIMIT 1;
    
    -- If close enough, return existing cluster
    IF v_distance IS NOT NULL AND v_distance < p_threshold THEN
        RETURN v_cluster_id;
    END IF;
    
    -- Otherwise return NULL (caller should create new cluster)
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Update daily velocity stats
CREATE OR REPLACE FUNCTION update_velocity_stats()
RETURNS void AS $$
BEGIN
    INSERT INTO article_velocity (topic, date, article_count, authority_count, generalist_count, corporate_count, active_sources)
    SELECT 
        topic,
        CURRENT_DATE,
        COUNT(*),
        COUNT(*) FILTER (WHERE source_tier = 'authority'),
        COUNT(*) FILTER (WHERE source_tier = 'generalist'),
        COUNT(*) FILTER (WHERE source_tier = 'corporate'),
        COUNT(DISTINCT source_name)
    FROM articles
    WHERE DATE(first_seen_at) = CURRENT_DATE
    GROUP BY topic
    ON CONFLICT (topic, date, hour) 
    DO UPDATE SET 
        article_count = EXCLUDED.article_count,
        authority_count = EXCLUDED.authority_count,
        generalist_count = EXCLUDED.generalist_count,
        corporate_count = EXCLUDED.corporate_count,
        active_sources = EXCLUDED.active_sources;
END;
$$ LANGUAGE plpgsql;

-- Cleanup old data (keep 90 days)
CREATE OR REPLACE FUNCTION cleanup_old_data(p_days INTEGER DEFAULT 90)
RETURNS TABLE (
    articles_deleted INTEGER,
    clusters_deleted INTEGER,
    signals_deleted INTEGER
) AS $$
DECLARE
    v_articles INTEGER;
    v_clusters INTEGER;
    v_signals INTEGER;
BEGIN
    -- Delete old articles (keep embeddings for 90 days)
    DELETE FROM articles WHERE first_seen_at < NOW() - (p_days || ' days')::INTERVAL;
    GET DIAGNOSTICS v_articles = ROW_COUNT;
    
    -- Delete orphan clusters
    DELETE FROM clusters WHERE id NOT IN (SELECT DISTINCT cluster_id FROM articles WHERE cluster_id IS NOT NULL);
    GET DIAGNOSTICS v_clusters = ROW_COUNT;
    
    -- Keep signals for 1 year
    DELETE FROM signals WHERE detected_at < NOW() - INTERVAL '365 days';
    GET DIAGNOSTICS v_signals = ROW_COUNT;
    
    RETURN QUERY SELECT v_articles, v_clusters, v_signals;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- PART 13: RLS POLICIES
-- ============================================

ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_thresholds ENABLE ROW LEVEL SECURITY;
ALTER TABLE article_velocity ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_params ENABLE ROW LEVEL SECURITY;

-- Service role has full access to everything
CREATE POLICY "service_sources" ON sources FOR ALL TO service_role USING (true);
CREATE POLICY "service_articles" ON articles FOR ALL TO service_role USING (true);
CREATE POLICY "service_clusters" ON clusters FOR ALL TO service_role USING (true);
CREATE POLICY "service_signals" ON signals FOR ALL TO service_role USING (true);
CREATE POLICY "service_feedback" ON signal_feedback FOR ALL TO service_role USING (true);
CREATE POLICY "service_thresholds" ON signal_thresholds FOR ALL TO service_role USING (true);
CREATE POLICY "service_velocity" ON article_velocity FOR ALL TO service_role USING (true);
CREATE POLICY "service_prompts" ON prompt_templates FOR ALL TO service_role USING (true);
CREATE POLICY "service_params" ON pipeline_params FOR ALL TO service_role USING (true);

-- Authenticated users can read signals and clusters
CREATE POLICY "read_signals" ON signals FOR SELECT TO authenticated USING (true);
CREATE POLICY "read_clusters" ON clusters FOR SELECT TO authenticated USING (true);
CREATE POLICY "read_articles" ON articles FOR SELECT TO authenticated USING (true);

-- ============================================
-- PART 14: TRIGGERS
-- ============================================

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_sources_timestamp BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_clusters_timestamp BEFORE UPDATE ON clusters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_signals_timestamp BEFORE UPDATE ON signals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_thresholds_timestamp BEFORE UPDATE ON signal_thresholds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- VERIFICATION
-- ============================================

SELECT 'Migration V3 Signal System complete' as status;

-- Show created tables
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
