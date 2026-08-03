-- 067: Population to narrative canon (Day 20 ruling — "pop should be more").
-- The engine held placeholder-scale populations (~6.6M / ~1M) while canon says
-- ~9.8B core + ~14.2B reclaimed. Scaling to canon with matching carrying caps.

-- 1. TKG core (11 non-Mastika): 9.8B total - 2.5B Mastika = 7.3B / 11 ≈ 663.6M each
UPDATE maya_rp.territory SET population = 663636363, max_population = 1500000000
WHERE session_id = 3 AND controlling_faction = 'Setia Empire'
  AND system_name IN ('0-0','0-1','1-0','1-1','5-8','9-17',
                      'TKG Aman','TKG Bayu','TKG Cendana','TKG Relau','TKG Waja');

-- 2. Reclaimed Ghost Signal systems — narrative tiers (name order):
--    C1 (5): ~760M | C2 (4): ~1.025B | C3 (4): ~875M | C4 (4): ~700M
UPDATE maya_rp.territory SET population = 760000000, max_population = 2000000000
WHERE session_id = 3 AND system_name IN ('19-11','19-12','20-11','20-19','20-21');

UPDATE maya_rp.territory SET population = 1025000000, max_population = 2000000000
WHERE session_id = 3 AND system_name IN ('20-24','21-14','21-16','21-19');

UPDATE maya_rp.territory SET population = 875000000, max_population = 2000000000
WHERE session_id = 3 AND system_name IN ('21-23','22-13','22-15','22-20');

UPDATE maya_rp.territory SET population = 700000000, max_population = 2000000000
WHERE session_id = 3 AND system_name IN ('22-24','23-17','23-22','23-23');

-- 3. C5 quarantine (3): evacuated, beacon net expired — dead worlds, survey pending.
UPDATE maya_rp.territory SET population = 0, status = 'abandoned'
WHERE session_id = 3 AND system_name IN ('24-14','24-15','24-23');

-- 4. Global pool: modeled sum now ≈ 24.0B (narrative ~26.5B incl. unmodeled masses).
UPDATE maya_rp.resources SET population =
    (SELECT COALESCE(SUM(population),0) FROM maya_rp.territory WHERE session_id = 3)
WHERE session_id = 3;
