-- ═══════════════════════════════════════════════════════════════════
-- FACTION AXES — doctrine, origin, and the deterministic stance readout
-- Applied to production 2026-10-02; this file makes it reproducible.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET search_path TO maya_rp;

ALTER TABLE factions ADD COLUMN IF NOT EXISTS doctrine text DEFAULT 'unaligned';
ALTER TABLE factions ADD COLUMN IF NOT EXISTS origin text DEFAULT 'imposed';
ALTER TABLE factions ADD COLUMN IF NOT EXISTS stance text;
ALTER TABLE factions ADD COLUMN IF NOT EXISTS stance_score numeric;
ALTER TABLE factions ADD COLUMN IF NOT EXISTS stance_at timestamptz;

-- The five-axis canon: doctrine (science_tech/magic/balance/unaligned), aggression,
-- piracy, species, origin (natural/imposed/sponsored). Values live in
-- wiki/rp-dev/FACTIONS-AXES-2026-10-02.md.
COMMENT ON COLUMN factions.doctrine IS 'science_tech | magic | balance | unaligned';
COMMENT ON COLUMN factions.origin IS 'natural | imposed | sponsored';
COMMENT ON COLUMN factions.stance IS 'computed by scripts/faction_stance.py, never hand-written';

COMMIT;
