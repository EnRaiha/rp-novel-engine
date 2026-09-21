-- 107: QA fix wave 3 (2026-09-17) — counter-espionage tables
-- Additive only. Owner: maya.
--   Apply: PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>
--
-- modules/council.py (CounterEspionage, ported from the Rust crate) reads and
-- writes two relations that were never created, so scan_for_plots(),
-- assign_agent() and thwart_plot() could not run at all. No existing table
-- carries their shape: `counter_intel_ops` is faction-vs-faction operations and
-- `intel_reports` is a report inbox.

CREATE TABLE IF NOT EXISTS maya_rp.conspiracies (
  id            serial PRIMARY KEY,
  session_id    integer NOT NULL REFERENCES maya_rp.sessions(id),
  plot_type     text NOT NULL,
  target        text,
  current_phase text,
  difficulty    integer NOT NULL DEFAULT 5,
  status        text NOT NULL DEFAULT 'active',
  details       jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conspiracies_session
  ON maya_rp.conspiracies (session_id, status);

-- One counter-intel network per session (the module calls it game_id; the
-- engine convention is session_id + an upsert so the singleton row is created
-- on first assignment instead of the UPDATE matching zero rows).
CREATE TABLE IF NOT EXISTS maya_rp.intel_network (
  session_id      integer PRIMARY KEY REFERENCES maya_rp.sessions(id),
  agents_assigned jsonb NOT NULL DEFAULT '[]'::jsonb,
  quality         integer NOT NULL DEFAULT 0,
  last_scan       timestamptz
);
