-- 051-space-horror-bugs.sql
-- Complete Space Bug Infestation system with containment, war, and eradication.
-- ============================================================
-- 0. Crisis events table (needed by horror system)
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.crisis_events (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    crisis_type VARCHAR(50) NOT NULL,
    severity INT DEFAULT 1,
    started_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    description TEXT
);

-- ============================================================
-- 1. Infestation Stages
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.infestation_stages (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    spread_rate NUMERIC DEFAULT 1.0,
    consumption_rate NUMERIC DEFAULT 1.0,
    threat_level INT DEFAULT 1,
    visibility VARCHAR(20),        -- hidden, discovered, obvious, overwhelming
    requires_containment BOOLEAN DEFAULT FALSE
);

INSERT INTO maya_rp.infestation_stages
    (name, description, spread_rate, consumption_rate, threat_level, visibility, requires_containment)
VALUES
    ('Spore Drift', 'Microscopic spores drifting through space. Undetectable.',
     0.1, 0, 1, 'hidden', FALSE),
    ('Colony Seed', 'A small colony has taken root on a surface.',
     0.5, 5, 2, 'discovered', FALSE),
    ('Infestation', 'Active infestation consuming resources and growing.',
     1.5, 20, 4, 'discovered', TRUE),
    ('Hive Mind', 'A central intelligence has formed. Coordinated attacks.',
     3.0, 50, 6, 'obvious', TRUE),
    ('Swarm', 'Massive fleets of bio-ships. System-wide threat.',
     5.0, 100, 8, 'obvious', TRUE),
    ('Galactic Plague', 'Multi-system infestation. Extinction-level event.',
     10.0, 500, 10, 'overwhelming', TRUE);

-- ============================================================
-- 2. Infestation Instances
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.infestation_instances (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    sector_id INT REFERENCES maya_rp.sectors(id) ON DELETE CASCADE,
    territory_id INT REFERENCES maya_rp.territory(id) ON DELETE CASCADE,
    stage_id INT REFERENCES maya_rp.infestation_stages(id) ON DELETE CASCADE,
    biomass INT DEFAULT 100,
    spread_progress INT DEFAULT 0,
    discovered BOOLEAN DEFAULT FALSE,
    discovered_at TIMESTAMP,
    contained BOOLEAN DEFAULT FALSE,
    containment_level INT DEFAULT 0,
    last_spread TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    destroyed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active'  -- active, contained, destroyed, eradicated
);

-- ============================================================
-- 3. Containment Measures
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.containment_measures (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    category VARCHAR(50),  -- quarantine, barrier, defensive, biological, psychic
    effectiveness NUMERIC DEFAULT 1.0,
    cost_credits INT,
    cost_resources JSONB,
    research_required VARCHAR(100),
    build_time_days INT
);

INSERT INTO maya_rp.containment_measures
    (name, description, category, effectiveness, cost_credits, cost_resources,
     research_required, build_time_days)
VALUES
    ('System Quarantine', 'Lock down all travel to/from an infested sector.',
     'quarantine', 0.6, 50000, '{"fuel":500}', 'quarantine_tech', 5),
    ('Orbital Barrier', 'Defensive grid to prevent spore spread.',
     'barrier', 0.7, 100000, '{"alloys":2000,"rare_earth":50}', 'barrier_tech', 10),
    ('Planetary Shield', 'Protects a planet from infestation.',
     'defensive', 0.9, 150000, '{"alloys":3000,"rare_earth":100}', 'shield_tech', 15),
    ('Flame Wall', 'Superheated plasma barrier in space.',
     'defensive', 0.8, 80000, '{"alloys":1500,"fuel":1000}', 'plasma_tech', 8),
    ('Void Bomb', 'Annihilates biomass in a radius.',
     'biological', 0.9, 200000, '{"void_crystal":5,"dream_essence":20}', 'void_tech', 20),
    ('Psychic Barrier', 'Repels infestation using psychic energy.',
     'psychic', 0.85, 120000, '{"dream_essence":50,"rare_earth":30}', 'psi_tech', 12),
    ('Starfire Purge', 'Cleanses a system using stellar energy.',
     'biological', 0.95, 300000, '{"starsteel":10,"dream_essence":100}', 'starfire_tech', 30);

-- ============================================================
-- 4. Bug War Assets
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.bug_war_assets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    type VARCHAR(50),     -- ship, weapon, module, research
    description TEXT,
    cost_credits INT,
    cost_resources JSONB,
    research_required VARCHAR(100),
    effect JSONB,
    build_time_days INT
);

INSERT INTO maya_rp.bug_war_assets
    (name, type, description, cost_credits, cost_resources,
     research_required, effect, build_time_days)
VALUES
    ('Flame Frigate', 'ship', 'Specialized ship with plasma throwers.',
     25000, '{"alloys":500,"fuel":200}', 'plasma_tech',
     '{"bug_damage_mult":2.0}', 10),
    ('Bio-Weapon Ship', 'ship', 'Deploys biological agents against infestation.',
     30000, '{"alloys":400,"dream_essence":10}', 'bio_tech',
     '{"spread_reduction":0.5,"biomass_damage":100}', 12),
    ('Purifier Squadron', 'ship', 'Elite fighter wing for bug elimination.',
     20000, '{"alloys":300,"fuel":100}', 'fighter_tech',
     '{"bug_damage_mult":3.0}', 8),
    ('Containment Satellite', 'module', 'Orbital station for monitoring.',
     15000, '{"alloys":200,"rare_earth":10}', 'sensor_tech',
     '{"containment_bonus":0.3}', 6),
    ('Bio-Scanner Module', 'module', 'Detects infestation before it spreads.',
     10000, '{"alloys":150,"rare_earth":5}', 'sensor_tech',
     '{"detection_bonus":0.5}', 4);

-- ============================================================
-- 5. Eradication Campaigns
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.eradication_campaigns (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    target_infestation_id INT REFERENCES maya_rp.infestation_instances(id) ON DELETE CASCADE,
    campaign_name VARCHAR(100),
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    progress INT DEFAULT 0,
    strategy VARCHAR(50),  -- bombardment, biological, psychic, systematic
    assets_assigned JSONB,
    status VARCHAR(20) DEFAULT 'active',  -- active, successful, failed
    casualties INT DEFAULT 0,
    resources_consumed JSONB
);

-- ============================================================
-- 6. Bug Events (narrative horror)
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.bug_events (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    infestation_id INT REFERENCES maya_rp.infestation_instances(id) ON DELETE CASCADE,
    event_type VARCHAR(50),  -- outbreak, spread, attack, mutation, containment_failure
    description TEXT,
    severity INT DEFAULT 1,
    happened_at TIMESTAMP DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE,
    resolution TEXT
);

-- ============================================================
-- 7. Bug Tech Tree
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.bug_tech_tree (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    research_cost INT,
    prerequisite_id INT REFERENCES maya_rp.bug_tech_tree(id) ON DELETE SET NULL,
    unlocks VARCHAR(100),
    unlock_type VARCHAR(50)  -- containment, asset, tactic, passive
);

INSERT INTO maya_rp.bug_tech_tree (name, description, research_cost, unlocks, unlock_type) VALUES
    ('Basic Containment', 'Learn how to slow bug spread.', 5000, 'System Quarantine', 'containment'),
    ('Advanced Barriers', 'Build effective barriers against infestation.', 10000, 'Orbital Barrier', 'containment'),
    ('Plasma Warfare', 'Weapons that burn bugs.', 8000, 'Flame Frigate', 'asset'),
    ('Biological Warfare', 'Weapons that target bug biology.', 12000, 'Bio-Weapon Ship', 'asset'),
    ('Psychic Resistance', 'Train psychic soldiers to fight bugs.', 15000, 'Psychic Barrier', 'containment'),
    ('Systematic Eradication', 'Plan and execute full bug elimination.', 20000, 'Starfire Purge', 'containment'),
    ('Void Annihilation', 'Use void technology to erase bugs.', 25000, 'Void Bomb', 'containment');

-- ============================================================
-- 8. Views
-- ============================================================
CREATE OR REPLACE VIEW maya_rp.infestation_threats AS
SELECT ii.id, ii.sector_id, s.name AS sector_name, ii.territory_id, t.name AS territory_name,
       st.name AS stage, st.threat_level, ii.biomass, ii.spread_progress,
       ii.contained, ii.containment_level, ii.discovered, ii.status, ii.created_at
FROM maya_rp.infestation_instances ii
LEFT JOIN maya_rp.sectors s ON s.id = ii.sector_id
LEFT JOIN maya_rp.territory t ON t.id = ii.territory_id
JOIN maya_rp.infestation_stages st ON st.id = ii.stage_id
WHERE ii.status NOT IN ('destroyed', 'eradicated');

-- ============================================================
-- 9. Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_infest_session ON maya_rp.infestation_instances(session_id);
CREATE INDEX IF NOT EXISTS idx_infest_status ON maya_rp.infestation_instances(status);
CREATE INDEX IF NOT EXISTS idx_infest_sector ON maya_rp.infestation_instances(sector_id);
CREATE INDEX IF NOT EXISTS idx_erad_campaign_session ON maya_rp.eradication_campaigns(session_id);
CREATE INDEX IF NOT EXISTS idx_erad_campaign_status ON maya_rp.eradication_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_bug_events_infest ON maya_rp.bug_events(infestation_id);

-- ============================================================
-- 10. Migration tracking
-- ============================================================
INSERT INTO maya_rp.migration_hashes (filename, sha256, applied_at)
VALUES ('051-space-horror-bugs.sql', encode(sha256('051-space-horror-bugs'::bytea), 'hex'), NOW())
ON CONFLICT (filename) DO NOTHING;
