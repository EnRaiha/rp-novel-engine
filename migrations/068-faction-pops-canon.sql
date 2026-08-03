-- 068: Canon population for ALL non-Setia factions (background scale-up).
-- Same treatment as 067: placeholder pops → believable canon scale, by dev level.
-- Setia worlds untouched. Population model still ticks only Setia (player realm);
-- other factions' worlds are now realistic for trade/strength/feeding dynamics.

UPDATE maya_rp.territory SET population = 250000000, max_population = 1500000000
WHERE session_id = 3 AND controlling_faction != 'Setia Empire' AND development_level = 1;

UPDATE maya_rp.territory SET population = 400000000, max_population = 1500000000
WHERE session_id = 3 AND controlling_faction != 'Setia Empire' AND development_level = 2;

UPDATE maya_rp.territory SET population = 550000000, max_population = 1500000000
WHERE session_id = 3 AND controlling_faction != 'Setia Empire' AND development_level = 3;

UPDATE maya_rp.territory SET population = 700000000, max_population = 1500000000
WHERE session_id = 3 AND controlling_faction != 'Setia Empire' AND development_level >= 4;
