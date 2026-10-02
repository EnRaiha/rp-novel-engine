-- ═══════════════════════════════════════════════════════════════════
-- MIGRATION BOOKKEEPING, second pass
--
-- 119_science_assassination.sql is applied and live in maya_rp, but it was never
-- recorded in maya_rp._migrations, so a rebuild that replays the table would skip it.
-- 123 is recorded here too, by the same rule: the table names what ran.
-- Nothing else changes. No schema, no data beyond the ledger rows.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET search_path TO maya_rp;

INSERT INTO _migrations (name) VALUES
  ('119_science_assassination.sql'),
  ('123_migration_bookkeeping.sql')
ON CONFLICT (name) DO NOTHING;

COMMIT;
