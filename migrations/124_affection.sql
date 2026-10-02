-- ═══════════════════════════════════════════════════════════════════
-- AFFECTION — the fourth relationship field, and the one that was missing
--
-- The King's carryover has three parts: wives start with 3 to 5 affection toward Izzat,
-- anyone he killed or wronged carries 3 to 5 aggro, and everyone who lived well keeps 100
-- loyalty. The first two landed on `bond_level` by mistake. `bond_level` is the marriage
-- bond, and the King ruled on 2026-10-02 that the wives are not married yet because the
-- marriages do not happen until Maya arrives. So the affection was reverted and had no home.
--
-- Four fields, four meanings:
--   bond_level  the marriage bond. 0 until the marriage happens.
--   affection   how warm a person is toward Izzat. The carryover sets wives to 4.
--   loyalty     whether they stay. 100 for the 226 who lived well.
--   aggro       how much they want him hurt. 4 for the 14 he killed or wronged.
--
-- Kept on the same small scale as `aggro`, because the carryover names both in the same breath.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET search_path TO maya_rp;

ALTER TABLE characters ADD COLUMN IF NOT EXISTS affection integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN characters.affection IS
  'Warmth toward Izzat, 0-100. Distinct from bond_level (marriage), loyalty (staying) and aggro (hostility)';

COMMIT;
