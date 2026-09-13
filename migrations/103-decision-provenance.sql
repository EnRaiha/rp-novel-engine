-- 103-decision-provenance.sql — Decision Provenance Layer (Fasa 1, Semantica plan 2026-08-18)
-- Extend existing cabinet_decrees (NOT a new parallel table) + unified decision_stream view.

-- 1) Extended columns on cabinet_decrees (existing decision table)
ALTER TABLE maya_rp.cabinet_decrees
  ADD COLUMN IF NOT EXISTS parent_id     INT REFERENCES maya_rp.cabinet_decrees(id),
  ADD COLUMN IF NOT EXISTS game_day      INT,
  ADD COLUMN IF NOT EXISTS event_ids     INT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS state_before  JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS state_after   JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_decrees_parent ON maya_rp.cabinet_decrees (parent_id);
CREATE INDEX IF NOT EXISTS idx_decrees_game_day ON maya_rp.cabinet_decrees (game_day);
CREATE INDEX IF NOT EXISTS idx_decrees_status ON maya_rp.cabinet_decrees (status);

-- 2) Backfill game_day from issued_at via sessions.game_day (best effort: game_day unknown per timestamp,
--    use the session's CURRENT game_day as anchor — timestamps after that are capped at current).
--    (Proper historical backfill is done by the seed script; this is a safe floor.)
UPDATE maya_rp.cabinet_decrees d
SET game_day = COALESCE(d.game_day, s.game_day)
FROM maya_rp.sessions s
WHERE d.session_id = s.id AND d.game_day IS NULL;

-- 3) View: unified decision stream (decrees + grand_plan items)
CREATE OR REPLACE VIEW maya_rp.decision_stream AS
SELECT
  'decree'::text                          AS kind,
  id::bigint                              AS decision_id,
  parent_id,
  game_day,
  issued_by                               AS actor,
  decree_type                             AS decision_type,
  title,
  description,
  status,
  priority,
  secrecy_level,
  impact_deltas,
  event_ids,
  state_before,
  state_after,
  issued_at AS occurred_at
FROM maya_rp.cabinet_decrees
UNION ALL
SELECT
  'plan'::text                            AS kind,
  id::bigint                              AS decision_id,
  NULL::int                               AS parent_id,
  NULL::int                               AS game_day,
  'engine'::text                          AS actor,
  phase                                   AS decision_type,
  item_name                               AS title,
  notes                                   AS description,
  status,
  'standard'::text                        AS priority,
  'public'::text                          AS secrecy_level,
  jsonb_build_object('cost', cost_credits) AS impact_deltas,
  '{}'::int[]                             AS event_ids,
  '{}'::jsonb                             AS state_before,
  '{}'::jsonb                             AS state_after,
  created_at AS occurred_at
FROM maya_rp.grand_plan;
