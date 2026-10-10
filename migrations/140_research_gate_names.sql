-- 140: the four research gate columns hold `research_projects.name`, not a slug.
--
-- Columns: megastructure_types.research_required (6 rows), containment_measures.research_required
-- (7), bug_war_assets.research_required (5), infrastructure_types.required_tech (29, six of them
-- hold `''` and stay ungated). The 41 gated rows hold 36 distinct snake_case slugs. The gate
-- compares a catalogue value to `research_projects.name`, which holds display names, so every
-- gated row was refused.
--
-- Every project name below was checked against the live table with a SELECT before this file was
-- written (2026-10-10): 36 map rows, 36 catalogue slugs, no id that disagrees with its name, no
-- name held by two ids after the rename in step 3. 29 distinct projects take a slug; four of them
-- (`Extraction Automation`, `Automated Assembly Lines`, `Refinery Optimization`,
-- `Celestial Archive Decode`) are unlocked, so four infrastructure rows open on the apply.
--
-- Rows holding `''` keep it: the code reads `''` as no gate.
--
-- Mapping strength: S = project name or effect matches the catalogue row, M = same domain,
-- W = nearest available project, owner veto pending. The W rows are marked in the map below.
-- `ringworld_tech` takes `Frontier Expansion` because a Ringworld raises population capacity and
-- that project raises max population; the earlier pick, `Matter Synthesis`, has no population link.
--
-- NOT APPLIED. Safe to run twice: a value that already names its project matches no slug, the
-- rename is a no-op once done, and the constraint is added only when absent.
--
-- Rollback: read the map below in reverse (set each column back to the slug), rename id 27 back to
-- 'Hyperdrive Calibration', then drop constraint research_projects_name_key.
BEGIN;
SET search_path TO maya_rp;

-- 1. The 36 slugs and their projects. Weak rows carry `-- W`.
CREATE TEMP TABLE IF NOT EXISTS _research_gate_map (
    slug text PRIMARY KEY,
    project_name text NOT NULL
) ON COMMIT DROP;

INSERT INTO _research_gate_map (slug, project_name) VALUES
    ('aether_tech',        'Aetheric Theory'),
    ('archive_tech',       'Celestial Archive Decode'),
    ('stellar_forge_tech', 'Starsteel Forging'),
    ('dyson_tech',         'Fusion Reactor Design'),        -- W
    ('ringworld_tech',     'Frontier Expansion'),           -- W
    ('worldforge_tech',    'Mega-Foundry'),
    ('barrier_tech',       'Magitech Barrier'),
    ('shield_tech',        'Energy Shields'),
    ('psi_tech',           'Psionic Awakening'),
    ('plasma_tech',        'Plasma Cannons'),
    ('void_tech',          'Void Manipulation'),
    ('sensor_tech',        'Phased Array Sensors'),
    ('bio_tech',           'Gene Therapy'),
    ('quarantine_tech',    'Bureaucratic Reform'),          -- W
    ('starfire_tech',      'Entropy Warheads'),             -- W
    ('fighter_tech',       'Fleet Maneuver Doctrine'),      -- W
    ('deep_mining_tech',   'Deep Core Mining'),
    ('asteroid_tech',      'Extraction Automation'),
    ('gas_harvest_tech',   'Extraction Automation'),        -- W
    ('arcane_mining_tech', 'Aetheric Theory'),
    ('smelting_tech',      'Refinery Optimization'),
    ('fuel_tech',          'Fusion Reactor Design'),
    ('alchemy_tech',       'Matter Synthesis'),
    ('research_tech',      'Research AI'),
    ('defense_tech',       'Point Defense Matrix'),
    ('trade_tech',         'Trade Diplomacy'),
    ('arcane_tech',        'Aetheric Theory'),
    ('arcane_ward_tech',   'Magitech Barrier'),
    ('mega_engineering',   'Mega-Foundry'),
    ('industrial_tech',    'Automated Assembly Lines'),
    ('nanite_tech',        'Nanite Forges'),
    ('mana_tech',          'Aetheric Theory'),              -- W
    ('ion_tech',           'Kinetic Accelerators'),         -- W
    ('logistics_tech',     'Logistics Network'),
    ('dream_tech',         'Dreamweaving'),
    ('void_gate_tech',     'Void Jump Drive')
ON CONFLICT (slug) DO NOTHING;

-- 2. Every mapped project must exist and be named by exactly one row before anything is written.
DO $$
DECLARE bad text;
BEGIN
    SELECT string_agg(m.slug || ' -> ' || m.project_name, ', ') INTO bad
      FROM _research_gate_map m
     WHERE (SELECT count(*) FROM research_projects x WHERE x.name = m.project_name) <> 1;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'mapped project missing or not unique: %', bad;
    END IF;
END $$;

-- 3. Ids 9 and 27 are both 'Hyperdrive Calibration'. No table, view or tech_tree_path references
-- either id, so the newer row (27, propulsion) takes the disambiguated name. No row is removed.
UPDATE research_projects SET name = 'Hyperdrive Calibration II'
 WHERE id = 27 AND name = 'Hyperdrive Calibration';

-- 4. Two rows must not share a name once the gate compares names to this column.
DO $$
DECLARE dup text;
BEGIN
    SELECT string_agg(name, ', ') INTO dup
      FROM (SELECT name FROM research_projects GROUP BY name HAVING count(*) > 1) d;
    IF dup IS NOT NULL THEN
        RAISE EXCEPTION 'duplicate project names remain: %', dup;
    END IF;
END $$;

-- 5. `research_projects.name` becomes unique, so a gate value can never match two rows.
--
-- This block needs the table owner. The runner applies the file as `maya`; the test suite connects
-- as `rp_engine`, which holds UPDATE on the table but not ownership, so the tests run the same block
-- against a scratch copy between the two markers below. `ALTER TABLE ... ADD CONSTRAINT` has no
-- `IF NOT EXISTS`, so the block checks `pg_constraint` first.
-- owner-only begin
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'maya_rp.research_projects'::regclass
                      AND conname = 'research_projects_name_key') THEN
        EXECUTE 'ALTER TABLE maya_rp.research_projects ADD CONSTRAINT research_projects_name_key UNIQUE (name)';
    END IF;
END $$;
-- owner-only end

-- 6. Before the rewrite: every gate value is a mapped slug or already a project name. A new
-- catalogue row with an unmapped value stops the file here instead of leaving a silent slug.
DO $$
DECLARE bad text;
BEGIN
    SELECT string_agg(DISTINCT v, ', ') INTO bad FROM (
          SELECT research_required AS v FROM megastructure_types
    UNION ALL SELECT research_required FROM containment_measures
    UNION ALL SELECT research_required FROM bug_war_assets
    UNION ALL SELECT required_tech FROM infrastructure_types) s
     WHERE v IS NOT NULL AND v <> ''
       AND v NOT IN (SELECT slug FROM _research_gate_map)
       AND v NOT IN (SELECT name FROM research_projects);
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'gate value maps to no project: %', bad;
    END IF;
END $$;

-- 7. One statement per catalogue column. `''` rows match no slug and keep their value.
UPDATE megastructure_types t SET research_required = m.project_name
  FROM _research_gate_map m WHERE t.research_required = m.slug;

UPDATE containment_measures t SET research_required = m.project_name
  FROM _research_gate_map m WHERE t.research_required = m.slug;

UPDATE bug_war_assets t SET research_required = m.project_name
  FROM _research_gate_map m WHERE t.research_required = m.slug;

UPDATE infrastructure_types t SET required_tech = m.project_name
  FROM _research_gate_map m WHERE t.required_tech = m.slug;

-- 8. After the rewrite every non-empty gate value names exactly one project.
DO $$
DECLARE bad text;
BEGIN
    SELECT string_agg(DISTINCT v, ', ') INTO bad FROM (
          SELECT research_required AS v FROM megastructure_types
    UNION ALL SELECT research_required FROM containment_measures
    UNION ALL SELECT research_required FROM bug_war_assets
    UNION ALL SELECT required_tech FROM infrastructure_types) s
     WHERE v IS NOT NULL AND v <> ''
       AND (SELECT count(*) FROM research_projects rp WHERE rp.name = s.v) <> 1;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'gate value names no single project: %', bad;
    END IF;
END $$;

COMMIT;
