-- 083: hot-path indexes (QA PERF-1, 2026-08-14)
-- events grew to 14.5K rows with no secondary index; every "recent events"
-- query full-sorted the table. ships had only its pkey despite
-- session_id/status filters on every status command.
CREATE INDEX IF NOT EXISTS idx_events_session_happened ON maya_rp.events (session_id, happened_at DESC);
CREATE INDEX IF NOT EXISTS idx_ships_session_status ON maya_rp.ships (session_id, status);
