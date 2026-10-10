-- ═══════════════════════════════════════════════════════════════════
-- 118 — MIGRATION BOOKKEEPING: record 111 to 118 in maya_rp._migrations
--
-- Why: migrations 111 to 117 are applied to the database and absent from
-- maya_rp._migrations, so scripts/migrate.py would re-run them on its next
-- sweep. This file records them, and itself, using the table's own shape:
--   id serial PRIMARY KEY, name text UNIQUE, applied_at timestamptz DEFAULT NOW()
--
-- Owner: maya. Apply by hand (the runner stops at 045 on a re-run anyway):
--   PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>
--
-- Bookkeeping only. No new column, no new table, no game data. `name` is the
-- exact filename, which is the value the runner writes too.
--
-- `applied_at` takes the column default, so it is the backfill instant, not the
-- original apply time. The original was never recorded and cannot be recovered.
--
-- Note for the runner: scripts/migrate.py inserts its own row after applying a
-- file, so when it reaches this file it will insert 118 twice and print one
-- duplicate-key error after the SQL has already committed. The rows land; only
-- the printed line is misleading.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET LOCAL search_path TO maya_rp;

INSERT INTO _migrations (name) VALUES
  ('111-character-assets.sql'),
  ('112-campaign-layer.sql'),
  ('113-character-knowledge.sql'),
  ('114-knowledge-rules.sql'),
  ('115_faction_axes.sql'),
  ('116_world_models.sql'),
  ('117_trust_numeric.sql'),
  ('118_migration_bookkeeping.sql')
ON CONFLICT (name) DO NOTHING;

COMMIT;
