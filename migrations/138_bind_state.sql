-- 138: the state tables name the session that owns them.
--
-- Eight tables hold campaign state with no session marker: seven take a NOT NULL column with default
-- 3, and `trait_assignments` takes a nullable one filled from its target.
--
-- Default 3 follows `125_trade_deals_session.sql`: every existing row is Setia Kingdom's. The joins
-- below were read on 2026-10-10, before this file was written:
--   pirate_zones 25 of 25 name a session-3 planet; production_lines 11 of 11 and research_labs 2 of
--   2 a session-3 colony; pool_bets 11 of 11 a session-3 pool; university_campuses 36 of 37 a
--   session-3 territory and 1 a NULL territory; academy_campuses 4 of 4 a NULL colony, so they take
--   the default with nothing to join. `resource_production.description` names session-3 territories
--   in prose, and no column joins, so 3 rests on the text alone.
--
-- The 49 NULL-session `sectors` are Setia's: 2 black holes, 2 white holes and 7 with a `connects_to`
-- link. Seven `sector_connections` of session 3 point at them, none of session 5, and no name clash
-- with a session-3 sector.
--
-- `trait_assignments.target_id` is polymorphic and has no FK. A colony row takes its colony's
-- session, a ship row its ship's session, and a row whose target is absent takes 3. All nine ship
-- rows name ship 7, 16 or 17, which are not in `ships`.
--
-- APPLIED 2026-10-10 as `maya`, recorded in `_migrations`. Safe to run twice: each column is guarded, the key swap compares the key definition
-- first, and each backfill matches only a NULL. `PENDING_BINDING` in `core/binding.py` names the
-- state tables this file does not bind.
--
-- Rollback: ALTER TABLE ... DROP COLUMN session_id on the eight tables; restore
-- PRIMARY KEY (source) on resource_production; UPDATE sectors SET session_id = NULL WHERE id BETWEEN
-- 1751 AND 1799. No value is lost: every backfilled value is 3 except the 3 colony rows that take 5.
BEGIN;
SET LOCAL search_path TO maya_rp;

-- 1. The default is right only while every row points into Setia Kingdom. A row that points
--    elsewhere stops the file here, before a column is added, instead of taking a wrong label.
DO $$
DECLARE bad integer;
BEGIN
    SELECT count(*) INTO bad FROM pirate_zones z
     WHERE NOT EXISTS (SELECT 1 FROM planets p WHERE p.id = z.system_id AND p.session_id = 3);
    IF bad > 0 THEN
        RAISE EXCEPTION 'pirate_zones: % rows name no session-3 planet', bad;
    END IF;

    SELECT count(*) INTO bad FROM production_lines l
     WHERE NOT EXISTS (SELECT 1 FROM colonies c WHERE c.id = l.colony_id AND c.session_id = 3);
    IF bad > 0 THEN
        RAISE EXCEPTION 'production_lines: % rows name no session-3 colony', bad;
    END IF;

    SELECT count(*) INTO bad FROM research_labs r
     WHERE NOT EXISTS (SELECT 1 FROM colonies c WHERE c.id = r.colony_id AND c.session_id = 3);
    IF bad > 0 THEN
        RAISE EXCEPTION 'research_labs: % rows name no session-3 colony', bad;
    END IF;

    SELECT count(*) INTO bad FROM pool_bets b
     WHERE NOT EXISTS (SELECT 1 FROM roll_pools p WHERE p.id = b.pool_id AND p.session_id = 3);
    IF bad > 0 THEN
        RAISE EXCEPTION 'pool_bets: % rows name no session-3 pool', bad;
    END IF;

    SELECT count(*) INTO bad FROM university_campuses u
     WHERE u.territory_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM territory t WHERE t.id = u.territory_id AND t.session_id = 3);
    IF bad > 0 THEN
        RAISE EXCEPTION 'university_campuses: % rows name a territory outside session 3', bad;
    END IF;
END $$;

-- The NULL-session sectors take 3 without a unique-key clash.
DO $$
DECLARE bad integer;
BEGIN
    SELECT count(*) INTO bad FROM sectors a
      JOIN sectors b ON b.name = a.name AND b.session_id = 3
     WHERE a.session_id IS NULL;
    IF bad > 0 THEN
        RAISE EXCEPTION 'sectors: % NULL-session rows clash with a session-3 name', bad;
    END IF;
END $$;

-- 2. Seven tables take the marker with the Setia default.
ALTER TABLE university_campuses ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;
ALTER TABLE academy_campuses ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;
ALTER TABLE pirate_zones ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;
ALTER TABLE resource_production ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;
ALTER TABLE production_lines ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;
ALTER TABLE research_labs ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;
ALTER TABLE pool_bets ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;

-- `trait_assignments` stays nullable: a target that no longer exists has no session to inherit.
ALTER TABLE trait_assignments ADD COLUMN IF NOT EXISTS session_id integer;

-- 3. `resource_production` keyed on `source` alone: one session's tax description can hold the
--    source text of another. The session joins the key. No FK points at this key.
DO $$
DECLARE
    pk_name text;
    pk_def text;
BEGIN
    SELECT c.conname, pg_get_constraintdef(c.oid) INTO pk_name, pk_def
      FROM pg_constraint c
     WHERE c.conrelid = 'resource_production'::regclass AND c.contype = 'p';
    IF pk_def IS DISTINCT FROM 'PRIMARY KEY (session_id, source)' THEN
        IF pk_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE resource_production DROP CONSTRAINT %I', pk_name);
        END IF;
        ALTER TABLE resource_production ADD PRIMARY KEY (session_id, source);
    END IF;
END $$;

-- 4. The 49 sectors with no marker: 2 black holes, 2 white holes, and 7 sector_connections of
--    session 3 point at them. They are Setia's map, not a shared gate.
UPDATE sectors SET session_id = 3 WHERE session_id IS NULL;

-- 5. Fill `trait_assignments` from the target, then give the leftovers to Setia.
UPDATE trait_assignments t SET session_id = c.session_id
  FROM colonies c
 WHERE t.target_type = 'colony' AND t.target_id = c.id AND t.session_id IS NULL;

UPDATE trait_assignments t SET session_id = s.session_id
  FROM ships s
 WHERE t.target_type = 'ship' AND t.target_id = s.id AND t.session_id IS NULL;

UPDATE trait_assignments SET session_id = 3 WHERE session_id IS NULL;

-- 6. One index per table, for the session filter every reader applies.
CREATE INDEX IF NOT EXISTS university_campuses_session_idx ON university_campuses (session_id);
CREATE INDEX IF NOT EXISTS academy_campuses_session_idx ON academy_campuses (session_id);
CREATE INDEX IF NOT EXISTS pirate_zones_session_idx ON pirate_zones (session_id);
CREATE INDEX IF NOT EXISTS production_lines_session_idx ON production_lines (session_id);
CREATE INDEX IF NOT EXISTS research_labs_session_idx ON research_labs (session_id);
CREATE INDEX IF NOT EXISTS pool_bets_session_idx ON pool_bets (session_id);
CREATE INDEX IF NOT EXISTS trait_assignments_session_idx ON trait_assignments (session_id);
-- The new primary key leads with `session_id`, so this index repeats it. Kept for one index per
-- bound table; a later cleanup can drop it.
CREATE INDEX IF NOT EXISTS resource_production_session_idx ON resource_production (session_id);

COMMIT;
