-- ═══════════════════════════════════════════════════════════════════
-- WORLD MODELS — faction scale, the food ladder, and the ship tiers
-- Applied to production 2026-10-02; this file makes it reproducible.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET LOCAL search_path TO maya_rp;

ALTER TABLE factions ADD COLUMN IF NOT EXISTS systems_held integer DEFAULT 0;
ALTER TABLE factions ADD COLUMN IF NOT EXISTS scale_class text;
COMMENT ON COLUMN factions.scale_class IS 'major | minor | not_established. The King reseeded the map, so the database map is wider than the canon rule';

-- The food ladder. Prices are in credit, issued by the Consortium (D4).
INSERT INTO commodities (session_id, name, category, base_price, current_price, volatility, supply, demand, last_tick_at)
VALUES (5,'Nutrient Pack','food',1.0,1.0,0.03,90000000,88000000,1),
       (5,'Frozen Ration','food',2.5,2.5,0.08,9000000,7400000,1),
       (5,'Sealed Old-World Ration','food',9.0,9.0,0.22,240000,680000,1),
       (5,'Fresh Produce (farm world)','food',14.0,14.0,0.35,90000,520000,1),
       (5,'Craft-Preserved Ration','food',30.0,30.0,0.45,4000,38000,1)
ON CONFLICT DO NOTHING;

COMMIT;
