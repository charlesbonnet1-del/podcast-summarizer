-- =============================================
-- CLEAR ALL CACHES - Run this in Supabase SQL Editor
-- =============================================

-- 1. Clear cached intros (removes Azure voices)
DELETE FROM cached_intros;

-- 2. Clear today's ephemeride
DELETE FROM daily_ephemeride WHERE date = CURRENT_DATE;

-- 3. Clear processed segments
DELETE FROM processed_segments WHERE date = CURRENT_DATE;

-- 4. Verify caches are empty
SELECT 'cached_intros' as table_name, COUNT(*) as count FROM cached_intros
UNION ALL
SELECT 'daily_ephemeride', COUNT(*) FROM daily_ephemeride WHERE date = CURRENT_DATE
UNION ALL
SELECT 'processed_segments', COUNT(*) FROM processed_segments WHERE date = CURRENT_DATE;
