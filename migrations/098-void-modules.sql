-- 098: void-crossing modules — inter-nebular ship capability (2026-08-15)
--
-- "Crossing the void" = traveling BETWEEN nebulas (z-planes) without a gate.
-- Gates are the legal crossings; the VOID is what lies between the veils.
-- A ship needs a VOID DRIVE to cross it on its own power:
--
--   Void Drive          — core capability: allows z-crossing without a gate
--                        (travel_mult 0.5 = faster than the 24h/u standard)
--   Nebular Ward        — defense: reduces void-risk by 20% on crossing
--   Exotic Matter Cells — logistics: exotic-matter storage for long void runs
--   Void Anchor         — stability: resist wormhole/gate collapse (collapse_resist)
--
-- Install into ships via maya_rp.ship_modules (ship_id, module_id, slot_index).

INSERT INTO maya_rp.modules (name, category, effect_type, effect_value, grade, tier_min, tier_max, cost_alloys, cost_credits, special_rules)
VALUES
  ('Void Drive', 'void', 'void_cross', 1, 3, 4, 12, 200000, 5000000,
   '{"z_crossing": true, "travel_mult": 0.5, "exotic_matter_per_jump": 50}'::jsonb),
  ('Nebular Ward', 'void', 'void_resist', 20, 2, 3, 12, 80000, 2000000,
   '{"void_risk_reduction": 20}'::jsonb),
  ('Exotic Matter Cells', 'void', 'void_fuel', 100, 1, 3, 12, 50000, 1500000,
   '{"void_autonomy": true, "exotic_matter_capacity": 300}'::jsonb),
  ('Void Anchor', 'void', 'void_stabilize', 15, 4, 5, 12, 300000, 8000000,
   '{"collapse_resist": true}'::jsonb)
ON CONFLICT DO NOTHING;

-- capitals (T9-12, dreadnoughts/worldships) must be able to fit void gear
UPDATE maya_rp.modules SET tier_max = 12 WHERE category = 'void';
