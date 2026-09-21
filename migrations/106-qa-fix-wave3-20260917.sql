-- 106: QA fix wave 3 (2026-09-17) — remaining schema drift from the SQL prepare scan
-- Additive only. Owner: maya.
--   Apply: PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>

-- objectives.update_quarterly_progress() rewards a completed quarterly task with
-- research points on the session ledger ("Gacha blueprint reward"). `resources`
-- had no such column (only `territory.research_points`, which is per-territory),
-- so the reward write failed and the completion was silently unrewarded.
ALTER TABLE maya_rp.resources
  ADD COLUMN IF NOT EXISTS research_points bigint NOT NULL DEFAULT 0;
