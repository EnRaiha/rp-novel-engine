-- A weapon upgrade had nowhere to record that it was applied, so `apply_upgrade` charged the
-- treasury and left no trace: call it twice and the King pays twice for one fitting.
BEGIN;
SET LOCAL search_path TO maya_rp;

ALTER TABLE weapon_upgrades ADD COLUMN IF NOT EXISTS applied_at timestamptz;
COMMENT ON COLUMN weapon_upgrades.applied_at IS
  'When this fitting was bought and fitted. NULL means still available, and the only state that may be charged for';

COMMIT;
