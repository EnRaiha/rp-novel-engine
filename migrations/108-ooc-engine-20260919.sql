-- 108: OOC engine — System state, rules, audit provenance, milestones, exemptions, observer suspicion
-- Additive only. Owner: maya.
--   Apply: PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>
--   Or via the runner: python3 scripts/migrate.py   (registers in maya_rp._migrations)
--
-- The OOC engine has two planes (design: wiki/rp-dev/OOC-SYSTEM-DESIGN-2026-09-19.md §13):
--   harness plane (DSH plugin)  — prompt placement + audit of outgoing tool arguments, stateless
--   engine plane  (core/ooc.py) — authoritative state, prose audit beside core/guard.py, economy
-- This migration creates the ONE store both planes read: session-scoped, one writer (the engine).
--
-- Rules are data, authored per trait (`aloof` / `mentor` / `tyrant` / `general`); a persona is a
-- composition of traits, so a rule carries the trait it came from. Campaign-scope rules
-- (trait IS NULL, session_id IS NULL) apply to every persona.
-- Raw matched text is NEVER stored: only a sha256 fingerprint plus its length (privacy; the
-- audit trail is queryable without retaining prose).

-- ---------------------------------------------------------------- state
CREATE TABLE IF NOT EXISTS maya_rp.ooc_system_state (
  session_id      integer PRIMARY KEY,
  arc_stage       text NOT NULL DEFAULT 'lockdown'
                    CHECK (arc_stage IN ('lockdown','selective','confrontation')),
  deviation       integer NOT NULL DEFAULT 0 CHECK (deviation BETWEEN 0 AND 100),
  roleplay_points integer NOT NULL DEFAULT 0 CHECK (roleplay_points >= 0),
  audits          integer NOT NULL DEFAULT 0 CHECK (audits >= 0),
  findings        integer NOT NULL DEFAULT 0 CHECK (findings >= 0),
  debuff          text,
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- rules
CREATE TABLE IF NOT EXISTS maya_rp.ooc_rules (
  id           text PRIMARY KEY,
  scope        text NOT NULL CHECK (scope IN ('campaign','session')),
  session_id   integer REFERENCES maya_rp.ooc_system_state(session_id) ON DELETE CASCADE,
  trait        text,                     -- 'aloof' | 'mentor' | 'tyrant' | 'general' | NULL = campaign-wide
  kind         text NOT NULL CHECK (kind IN
                 ('forbidden_lexicon','somatic_lock','modern_phrasing','scripted_beat')),
  layer        text NOT NULL DEFAULT 'both' CHECK (layer IN ('somatic','dialogue','both')),
  pattern      text NOT NULL,
  is_regex     boolean NOT NULL DEFAULT false,   -- literal patterns stay escapable; regex is bounded at match time
  delta        integer NOT NULL CHECK (delta BETWEEN 1 AND 100),
  enabled      boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ooc_rules_scope_exclusive
    CHECK ((scope = 'campaign') = (session_id IS NULL))
);
CREATE INDEX IF NOT EXISTS ooc_rules_lookup_idx
  ON maya_rp.ooc_rules (enabled, layer, kind, trait);

-- ---------------------------------------------------------------- audit provenance (TTL: prune > 30 days)
CREATE TABLE IF NOT EXISTS maya_rp.ooc_audit_events (
  id              bigserial PRIMARY KEY,
  session_id      integer NOT NULL,
  rule_id         text REFERENCES maya_rp.ooc_rules(id) ON DELETE SET NULL,  -- NULL = no rule matched
  layer           text NOT NULL CHECK (layer IN ('somatic','dialogue','both','tool')),
  disposition     text NOT NULL CHECK (disposition IN ('flagged','exempt','skipped','no_match','rule_error')),
  skip_reason     text,                  -- 'no_rule_matched' | 'own_tool' | 'exempt' | 'stage_muted'
  match_sha256    text,                  -- fingerprint only
  match_len       integer,
  delta           integer NOT NULL DEFAULT 0,
  deviation_after integer NOT NULL CHECK (deviation_after BETWEEN 0 AND 100),
  suspicion_delta integer NOT NULL DEFAULT 0,
  turn_ref        text,                  -- session/turn anchor the audit belongs to
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ooc_audit_events_session_idx
  ON maya_rp.ooc_audit_events (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ooc_audit_events_created_idx
  ON maya_rp.ooc_audit_events (created_at);          -- prune target

-- ---------------------------------------------------------------- milestones / scripted beats
CREATE TABLE IF NOT EXISTS maya_rp.ooc_milestones (
  id            bigserial PRIMARY KEY,
  session_id    integer NOT NULL,
  name          text NOT NULL,
  trait         text,
  stage         text NOT NULL CHECK (stage IN ('lockdown','selective','confrontation')),
  required      boolean NOT NULL DEFAULT false,     -- a mandatory canon beat for timeline stability
  rpp_reward    integer NOT NULL DEFAULT 0 CHECK (rpp_reward >= 0),
  latch_ruleset text,                              -- ruleset kept on after the milestone fires
  completed_at  timestamptz,
  expires_at    timestamptz,
  UNIQUE (session_id, name)
);

-- ---------------------------------------------------------------- exemption economy (RPP spend)
CREATE TABLE IF NOT EXISTS maya_rp.ooc_exemptions (
  id           bigserial PRIMARY KEY,
  session_id   integer NOT NULL,
  rule_id      text NOT NULL REFERENCES maya_rp.ooc_rules(id) ON DELETE CASCADE,
  action_key   text NOT NULL,            -- 'gentle_touch' | 'audit_mute' | ...
  condition    text,                     -- 'scene:medical' | 'location:private_quarters'
  cost_rpp     integer NOT NULL CHECK (cost_rpp > 0),
  permanent    boolean NOT NULL DEFAULT true,
  expires_at   timestamptz,
  purchased_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, rule_id, action_key)
);

-- ---------------------------------------------------------------- observer suspicion (NPC, never the System)
CREATE TABLE IF NOT EXISTS maya_rp.ooc_suspicion (
  session_id    integer NOT NULL,
  observer_id   integer NOT NULL REFERENCES maya_rp.characters(id) ON DELETE CASCADE,
  suspicion     integer NOT NULL DEFAULT 0 CHECK (suspicion BETWEEN 0 AND 100),
  last_reason   text,
  last_event_id bigint REFERENCES maya_rp.ooc_audit_events(id) ON DELETE SET NULL,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (session_id, observer_id)
);

-- ---------------------------------------------------------------- session rows
-- State rows are created by the engine on first audit; nothing is seeded here.
-- TKG runs session 3; the plugin default is 0 until it points at the engine.
INSERT INTO maya_rp.ooc_system_state (session_id)
SELECT 3
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.ooc_system_state WHERE session_id = 3);
