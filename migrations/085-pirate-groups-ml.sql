-- 085: pirate group classification + ML decision-log columns (ML review 2026-08-14)
-- King's directive: pirate factions split into THREE groups, each with its own ML models:
--   Group 1 "free"     — wild & free pirates
--   Group 2 "sponsor"  — the 6 wolf pirates (all-human)
--   Group 3 "hired"    — contracted/loyal pirates
ALTER TABLE maya_rp.factions ADD COLUMN IF NOT EXISTS pirate_group text;

-- Group 2 — the six wolf pirates (tier 5, governed territory, all-human crews)
UPDATE maya_rp.factions SET pirate_group='sponsor' WHERE is_pirate AND name IN (
  'Dagger''s Rest Raiders','The Ashen Corsairs','Marrow Fleet',
  'Hollow Deck Syndicate','Rustgrave Pillagers','Gutterhawk Marauders');
-- Group 3 — hired: "loyal, allied, integrated" personality
UPDATE maya_rp.factions SET pirate_group='hired' WHERE is_pirate
  AND ai_personality::text ILIKE '%loyal, allied, integrated%';
-- Group 1 — everyone else is wild & free
UPDATE maya_rp.factions SET pirate_group='free' WHERE is_pirate AND pirate_group IS NULL;

-- ML decision-log extensions (retraining corpus for train_models.py)
ALTER TABLE maya_rp.ai_decision_log ADD COLUMN IF NOT EXISTS faction_id integer;
ALTER TABLE maya_rp.ai_decision_log ADD COLUMN IF NOT EXISTS model_name text;
ALTER TABLE maya_rp.ai_decision_log ADD COLUMN IF NOT EXISTS inputs jsonb;
ALTER TABLE maya_rp.ai_decision_log ADD COLUMN IF NOT EXISTS predicted text;
ALTER TABLE maya_rp.ai_decision_log ADD COLUMN IF NOT EXISTS probs jsonb;
ALTER TABLE maya_rp.ai_decision_log ADD COLUMN IF NOT EXISTS pirate_group text;
ALTER TABLE maya_rp.ai_decision_log ADD COLUMN IF NOT EXISTS decided_at timestamptz DEFAULT NOW();
