-- 097: voyage exotic-transit columns (2026-08-15)
-- Wires wormhole jumps, black-hole slingshots and time dilation into voyages.
--   transit_kind    — 'regular' | 'wormhole' | 'slingshot' | 'hidden'
--   transit_name    — wormhole/BH name used
--   dilation_days   — EXTRA game days booked by time dilation (1 ship-day = N game)
--   collapse_roll   — wormhole decay roll on arrival (NULL if not wormhole)
ALTER TABLE maya_rp.voyages
  ADD COLUMN IF NOT EXISTS transit_kind TEXT NOT NULL DEFAULT 'regular',
  ADD COLUMN IF NOT EXISTS transit_name TEXT,
  ADD COLUMN IF NOT EXISTS dilation_days INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS collapse_roll INTEGER;
