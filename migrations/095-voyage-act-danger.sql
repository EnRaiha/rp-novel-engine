-- 095: voyage hidden-thread risk v2 — act-driven danger model (2026-08-15)
-- Izzat's model: base danger 10-20%; detection roll; the ACT determines the
-- outcome. Running (act='run') adds +30-50% danger; no guide adds +20%.
-- Preparation, equipment, knowledge, and guide all REDUCE danger (each -5%).
-- Hot cargo (cargo_heat) attracts attention (+5% each).
--
-- POSITIVE SIDE (2026-08-15): hidden thread = smuggling = high risk, high
-- reward. On a clean arrival the cargo is sold at a premium margin and the
-- profit is credited to the treasury. cargo_value = estimated cargo worth;
-- reward_credits = profit actually paid out.
--
--   act             — how the run is conducted: sneak|run|guard|bribe (default sneak)
--   guide           — guide name/id (NULL = no guide → +20% danger)
--   prep_level      — persediaan 0-3 (-5% each)
--   equip_level     — peralatan 0-3 (-5% each)
--   knowledge_level — pengetahuan 0-3 (-5% each)
--   cargo_heat      — cargo berharga/ilegal 0-3 (+5% danger, +margin)
--   cargo_value     — estimated cargo worth in credits (for profit payout)
--   danger_pct      — computed detection chance at register (5..95)
--   loss_ships      — recorded when interdicted
--   reward_credits  — profit credited on clean arrival
ALTER TABLE maya_rp.voyages
  ADD COLUMN IF NOT EXISTS act TEXT NOT NULL DEFAULT 'sneak',
  ADD COLUMN IF NOT EXISTS guide TEXT,
  ADD COLUMN IF NOT EXISTS prep_level INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS equip_level INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS knowledge_level INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cargo_heat INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cargo_value BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS danger_pct INTEGER,
  ADD COLUMN IF NOT EXISTS loss_ships INTEGER,
  ADD COLUMN IF NOT EXISTS reward_credits BIGINT;
