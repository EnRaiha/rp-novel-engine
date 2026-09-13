-- 100: espionage outcome values fix (2026-08-15)
-- espionage.run_tick() resolves stale missions as 'went_dark'/'compromised'
-- but the CHECK constraint only allowed pending/success/failure/
-- critical_failure/detected/captured → every tick crashed.
-- Widen the constraint to accept the resolution values used in code.
ALTER TABLE maya_rp.espionage_missions
  DROP CONSTRAINT IF EXISTS espionage_missions_outcome_check;

ALTER TABLE maya_rp.espionage_missions
  ADD CONSTRAINT espionage_missions_outcome_check
  CHECK (outcome = ANY (ARRAY['pending','success','failure','critical_failure',
                             'detected','captured','went_dark','compromised']));
