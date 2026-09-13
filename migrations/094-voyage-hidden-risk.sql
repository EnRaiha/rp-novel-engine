-- 094: voyage hidden-thread risk modifiers (2026-08-15)
-- Hidden threads (smuggler routes) carry interception risk on arrival.
--   via_hidden   — voyage crossed planes via a hidden_thread lane
--   risk_roll    — d100 stored on arrival (NULL = not yet rolled)
--   interdicted  — roll <= 35: smuggler run caught; losses logged in events
ALTER TABLE maya_rp.voyages
  ADD COLUMN IF NOT EXISTS via_hidden BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS risk_roll INTEGER,
  ADD COLUMN IF NOT EXISTS interdicted BOOLEAN NOT NULL DEFAULT FALSE;
