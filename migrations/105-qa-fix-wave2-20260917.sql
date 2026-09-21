-- 105: QA fix wave 2 (2026-09-17)
-- Closes the schema-side defects found by the SQL prepare scan
-- (wiki/rp-dev/qa-20260916, BUG-C3 / C4 / C6 / C7). Additive only: no
-- existing column is retyped or dropped, no row is rewritten.
-- Owner: maya.  Apply: PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>

-- ── 1. combat_results: live-battle columns ────────────────────────────────
-- modules/battle.py (BattleEngine, ported from Rust) keeps a battle row open
-- with status='active' and closes it with outcome/ended_at; environment.py
-- already reads ended_at for its 72-hour engagement window. ship_states is the
-- live hull/shield snapshot so a mid-battle reload (attempt_retreat) can
-- rebuild the fleets instead of fighting with empty ones.
ALTER TABLE maya_rp.combat_results
  ADD COLUMN IF NOT EXISTS status           text NOT NULL DEFAULT 'completed',
  ADD COLUMN IF NOT EXISTS outcome          text,
  ADD COLUMN IF NOT EXISTS player_formation text,
  ADD COLUMN IF NOT EXISTS ended_at         timestamptz,
  ADD COLUMN IF NOT EXISTS ship_states      jsonb;

CREATE INDEX IF NOT EXISTS idx_combat_results_live
  ON maya_rp.combat_results (session_id, status);

-- ── 2. battle log / phases / aftermath (battle_id -> combat_results.id) ───
CREATE TABLE IF NOT EXISTS maya_rp.battle_log_entries (
  id          serial PRIMARY KEY,
  battle_id   integer NOT NULL REFERENCES maya_rp.combat_results(id) ON DELETE CASCADE,
  turn_number integer NOT NULL,
  actor       text,
  action      text,
  result      text,
  damage      integer,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_battle_log_entries_battle
  ON maya_rp.battle_log_entries (battle_id, turn_number);

CREATE TABLE IF NOT EXISTS maya_rp.battle_phases (
  id            serial PRIMARY KEY,
  battle_id     integer NOT NULL REFERENCES maya_rp.combat_results(id) ON DELETE CASCADE,
  phase_number  integer NOT NULL,
  phase_name    text,
  player_tactic text,
  enemy_tactic  text,
  damage_dealt  integer,
  damage_taken  integer,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_battle_phases_battle
  ON maya_rp.battle_phases (battle_id, phase_number);

CREATE TABLE IF NOT EXISTS maya_rp.battle_aftermath (
  id                serial PRIMARY KEY,
  battle_id         integer NOT NULL REFERENCES maya_rp.combat_results(id) ON DELETE CASCADE,
  loot_credits      bigint,
  reputation_change integer,
  narrative         text,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_battle_aftermath_battle
  ON maya_rp.battle_aftermath (battle_id);

-- ── 3. academy: graduations had nowhere to land ───────────────────────────
CREATE TABLE IF NOT EXISTS maya_rp.certifications (
  id         serial PRIMARY KEY,
  session_id integer REFERENCES maya_rp.sessions(id),
  crew_id    integer NOT NULL REFERENCES maya_rp.crew_roster(id) ON DELETE CASCADE,
  cert_name  text NOT NULL,
  tier       integer NOT NULL DEFAULT 1,
  field      text,
  awarded_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS certifications_crew_cert_key
  ON maya_rp.certifications (crew_id, cert_name);
CREATE INDEX IF NOT EXISTS idx_certifications_session
  ON maya_rp.certifications (session_id);

-- ── 4. mystery: clue -> investigation link + the template that seeded it ──
-- clues keys on (source, source_type, text, connects_to_clue) with no case
-- link, so an investigation could never count its own clues. investigations
-- keeps the template name so deduce() can read the template's registered
-- min_clues_for_deduction instead of a hardcoded threshold.
ALTER TABLE maya_rp.clues
  ADD COLUMN IF NOT EXISTS investigation_id integer
  REFERENCES maya_rp.investigations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_clues_investigation
  ON maya_rp.clues (investigation_id, revealed);

ALTER TABLE maya_rp.investigations
  ADD COLUMN IF NOT EXISTS template_name text,
  ADD COLUMN IF NOT EXISTS difficulty integer NOT NULL DEFAULT 5;
