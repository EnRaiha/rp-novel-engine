-- 101: combat_results tactical_state_id optional (2026-08-15)
-- battle.run_tick() generates autonomous CAMPAIGN engagements with no
-- tactical_state (that's for manual battles only) — the NOT NULL column
-- crashed every tick that rolled an engagement. Drop the constraint.
ALTER TABLE maya_rp.combat_results
  ALTER COLUMN tactical_state_id DROP NOT NULL;
