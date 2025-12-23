-- ============================================
-- KEERNEL V2.3 - VERTICALS UPDATE
-- ============================================
-- Updates vertical structure for V2 architecture
-- WORLD, TECH, ECONOMICS, SCIENCE, CULTURE

-- ============================================
-- 1. ADD NEW VERTICALS
-- ============================================

-- Add 'economics' vertical (replaces 'finance')
INSERT INTO verticals (id, name, name_fr, keywords, icon, sort_order) 
VALUES (
  'economics', 
  'Economics', 
  'Économie', 
  '["crypto", "macro", "stocks"]'::jsonb,
  '📈',
  3
)
ON CONFLICT (id) DO UPDATE SET 
  name = EXCLUDED.name,
  name_fr = EXCLUDED.name_fr,
  keywords = EXCLUDED.keywords;

-- Add/Update 'tech' vertical
INSERT INTO verticals (id, name, name_fr, keywords, icon, sort_order) 
VALUES (
  'tech', 
  'Tech', 
  'Tech', 
  '["ia", "quantum", "robotics"]'::jsonb,
  '🤖',
  1
)
ON CONFLICT (id) DO UPDATE SET 
  name = EXCLUDED.name,
  name_fr = EXCLUDED.name_fr,
  keywords = EXCLUDED.keywords;

-- Update 'world' vertical keywords
UPDATE verticals 
SET keywords = '["asia", "regulation", "resources"]'::jsonb
WHERE id = 'world';

-- Update 'science' vertical keywords
UPDATE verticals 
SET keywords = '["energy", "health", "space"]'::jsonb
WHERE id = 'science';

-- Update 'culture' vertical keywords
UPDATE verticals 
SET keywords = '["cinema", "gaming", "lifestyle"]'::jsonb
WHERE id = 'culture';

-- ============================================
-- 2. MIGRATE OLD VERTICAL REFERENCES
-- ============================================

-- Migrate 'ai_tech' to 'tech'
UPDATE content_queue 
SET vertical_id = 'tech' 
WHERE vertical_id = 'ai_tech';

UPDATE user_interests 
SET vertical_id = 'tech' 
WHERE vertical_id = 'ai_tech';

-- Migrate 'finance' to 'economics'
UPDATE content_queue 
SET vertical_id = 'economics' 
WHERE vertical_id = 'finance';

UPDATE user_interests 
SET vertical_id = 'economics' 
WHERE vertical_id = 'finance';

-- Migrate 'politics' to 'world'
UPDATE content_queue 
SET vertical_id = 'world' 
WHERE vertical_id = 'politics';

UPDATE user_interests 
SET vertical_id = 'world' 
WHERE vertical_id = 'politics';

-- ============================================
-- 3. VERIFY VERTICALS
-- ============================================

SELECT id, name, name_fr, keywords, icon, sort_order 
FROM verticals 
ORDER BY sort_order;
