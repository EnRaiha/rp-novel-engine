-- 102: Exotic Matter — Old Council Vault stockpile (2026-08-15, RP canon)
-- The last Rim Council's hoard, seized when the King ascended.
-- Random quantities per type (King's decree: 200–2000 each).
-- colony_id NULL = central royal vault (Mastika). Used for wormhole upkeep,
-- void-drive Exotic Matter Cells, and exotic transits.

INSERT INTO maya_rp.material_stockpiles (session_id, colony_id, material_name, quantity, reserved)
SELECT 3, NULL, 'EXOTIC — ' || v.mat, v.qty, 0
FROM (VALUES
  ('Negative Energy Cells', 912),
  ('Antimatter Canisters', 926),
  ('Strange Matter Cores', 589),
  ('Tachyon Condensate', 1332),
  ('Zero-Point Batteries', 1557),
  ('Dark Matter Slurry', 1352),
  ('Aetherium Crystals', 1941)
) AS v(mat, qty)
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.material_stockpiles s
                  WHERE s.session_id=3 AND s.colony_id IS NULL
                    AND s.material_name = 'EXOTIC — ' || v.mat);
