-- 049-megastructures-ports.sql
-- Megastructures & Port Type Class — endgame infrastructure.
-- Designed with fantasy tiers (mythic → common), multi-phase construction, port upgrades.

-- ============================================================
-- 0. Schema extensions needed by this and subsequent migrations
-- ============================================================
ALTER TABLE maya_rp.resources
    ADD COLUMN IF NOT EXISTS rare_earth INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS starsteel INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS void_crystal INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS aetherium INT DEFAULT 0;

ALTER TABLE maya_rp.territory
    ADD COLUMN IF NOT EXISTS morale INT DEFAULT 50;

-- ============================================================
-- 1. Megastructure Types
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.megastructure_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    fantasy_tier VARCHAR(20),   -- mythic, legendary, epic, rare
    construction_phases JSONB,  -- [{phase:1, cost:{}, time_days:N}, ...]
    total_cost_credits BIGINT,
    total_cost_resources JSONB,
    benefits JSONB,             -- {"production_mult":2.0, "research_bonus":50}
    research_required VARCHAR(100),
    unlocks VARCHAR(100),
    size INT DEFAULT 1           -- 1-10, system plot size
);

INSERT INTO maya_rp.megastructure_types
    (name, description, fantasy_tier, construction_phases, total_cost_credits,
     total_cost_resources, benefits, research_required, unlocks, size)
VALUES
    ('Dyson Sphere', 'A sphere surrounding a star, harnessing its energy.',
     'legendary',
     '[{"phase":1,"cost":{"alloys":100000,"fuel":50000,"dream_essence":100},"time_days":365},{"phase":2,"cost":{"alloys":200000,"rare_earth":1000},"time_days":730}]',
     5000000, '{"alloys":300000,"fuel":50000,"dream_essence":100,"rare_earth":1000}',
     '{"energy_production":1000000,"research_bonus":200}', 'dyson_tech', 'star_harvesting', 3),

    ('Ringworld', 'A massive ring habitat with habitable surface.',
     'legendary',
     '[{"phase":1,"cost":{"alloys":150000,"food":50000},"time_days":500},{"phase":2,"cost":{"alloys":250000,"dream_essence":50},"time_days":800}]',
     6000000, '{"alloys":400000,"food":50000,"dream_essence":50}',
     '{"population_capacity":50000000,"production_bonus":1.5}', 'ringworld_tech', 'habitat_expansion', 4),

    ('Worldforge', 'A planet-sized forge that can manufacture anything.',
     'epic',
     '[{"phase":1,"cost":{"alloys":80000,"fuel":20000},"time_days":200},{"phase":2,"cost":{"alloys":150000,"rare_earth":500},"time_days":400}]',
     3000000, '{"alloys":230000,"fuel":20000,"rare_earth":500}',
     '{"production_mult":3.0,"alloy_production":5000}', 'worldforge_tech', 'mass_production', 2),

    ('Aether Nexus', 'A focal point for magical energy, amplifying all spellcraft.',
     'mythic',
     '[{"phase":1,"cost":{"dream_essence":200,"aetherium":50},"time_days":300},{"phase":2,"cost":{"dream_essence":500,"void_crystal":10},"time_days":600}]',
     4000000, '{"dream_essence":700,"aetherium":50,"void_crystal":10}',
     '{"research_mult":2.0,"psi_power":100,"morale_bonus":20}', 'aether_tech', 'magic_unleashed', 2),

    ('Stellar Forge', 'A forge built around a dying star to create exotic materials.',
     'epic',
     '[{"phase":1,"cost":{"alloys":120000,"fuel":30000},"time_days":250},{"phase":2,"cost":{"starsteel":100,"void_crystal":5},"time_days":500}]',
     3500000, '{"alloys":120000,"fuel":30000,"starsteel":100,"void_crystal":5}',
     '{"starsteel_production":10,"rare_earth_production":50}', 'stellar_forge_tech', 'exotic_manufacturing', 2),

    ('Celestial Archive', 'A repository of all knowledge, past and future.',
     'mythic',
     '[{"phase":1,"cost":{"credits":1000000,"rare_earth":200},"time_days":400},{"phase":2,"cost":{"dream_essence":300,"void_crystal":1},"time_days":800}]',
     8000000, '{"credits":1000000,"rare_earth":200,"dream_essence":300,"void_crystal":1}',
     '{"research_speed_mult":3.0}', 'archive_tech', 'omniscience', 1);

-- ============================================================
-- 2. Player Megastructure Construction
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.megastructure_construction (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    megastructure_type_id INT REFERENCES maya_rp.megastructure_types(id) ON DELETE CASCADE,
    sector_id INT REFERENCES maya_rp.sectors(id) ON DELETE SET NULL,
    territory_id INT REFERENCES maya_rp.territory(id) ON DELETE SET NULL,
    current_phase INT DEFAULT 1,
    progress_pct INT DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW(),
    estimated_completion TIMESTAMP,
    status VARCHAR(20) DEFAULT 'construction',  -- construction, paused, completed
    resources_allocated JSONB
);

-- ============================================================
-- 3. Port Types
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.port_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    category VARCHAR(20),          -- civilian, military, research, trade, mixed
    build_cost_credits INT,
    build_cost_resources JSONB,
    upkeep_credits INT,
    benefits JSONB,
    upgrades JSONB,                -- list of upgrade path names
    description TEXT
);

INSERT INTO maya_rp.port_types
    (name, category, build_cost_credits, build_cost_resources, upkeep_credits,
     benefits, upgrades, description)
VALUES
    ('Spaceport', 'civilian', 50000, '{"alloys":500}', 1000,
     '{"trade_bonus":0.2,"population_growth":0.1}', '["large_spaceport","shipyard"]',
     'Basic spaceport for trade and passenger traffic.'),

    ('Trade Hub', 'trade', 100000, '{"alloys":1000,"rare_earth":20}', 2500,
     '{"trade_bonus":0.5,"tax_bonus":0.2}', '["mega_trade_hub"]',
     'Major trade nexus.'),

    ('Military Bastion', 'military', 150000, '{"alloys":2000,"fuel":500}', 5000,
     '{"defense_power":500,"fleet_repair":2}', '["fortress","naval_base"]',
     'Fortified military port.'),

    ('Research Station', 'research', 80000, '{"alloys":800,"rare_earth":50}', 2000,
     '{"research_bonus":0.3,"sensor_range":1.5}', '["advanced_lab"]',
     'Scientific outpost.'),

    ('Shipyard', 'military', 200000, '{"alloys":3000,"rare_earth":100}', 8000,
     '{"build_speed":0.5,"repair_speed":2}', '["mega_shipyard"]',
     'Massive construction facility.'),

    ('Arcane Port', 'mixed', 150000, '{"dream_essence":50,"aetherium":10}', 4000,
     '{"magic_bonus":1.5,"psi_power":20}', '["void_port"]',
     'Port attuned to magical energies.'),

    ('Colony Hub', 'civilian', 120000, '{"alloys":1500,"food":500}', 3000,
     '{"population_growth":0.3,"stability":0.2}', '["arcology"]',
     'Center of colonial administration.');

-- ============================================================
-- 4. Ports (instances)
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.ports (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    territory_id INT REFERENCES maya_rp.territory(id) ON DELETE CASCADE,
    port_type_id INT REFERENCES maya_rp.port_types(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    level INT DEFAULT 1,
    built_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active',  -- active, damaged, destroyed
    upgrades_applied JSONB DEFAULT '[]'
);

-- ============================================================
-- 5. Port Upgrades (tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.port_upgrades (
    id SERIAL PRIMARY KEY,
    port_id INT REFERENCES maya_rp.ports(id) ON DELETE CASCADE,
    upgrade_name VARCHAR(100),
    applied_at TIMESTAMP DEFAULT NOW(),
    cost_credits INT,
    cost_resources JSONB
);

-- ============================================================
-- 6. Views
-- ============================================================
CREATE OR REPLACE VIEW maya_rp.megastructure_status AS
SELECT mc.id, mt.name, mt.fantasy_tier, mc.current_phase, mc.progress_pct,
       mc.estimated_completion, mc.status,
       s.name AS sector_name, t.name AS territory_name
FROM maya_rp.megastructure_construction mc
JOIN maya_rp.megastructure_types mt ON mt.id = mc.megastructure_type_id
LEFT JOIN maya_rp.sectors s ON s.id = mc.sector_id
LEFT JOIN maya_rp.territory t ON t.id = mc.territory_id;

CREATE OR REPLACE VIEW maya_rp.port_overview AS
SELECT p.id, p.name, pt.name AS port_type, pt.category, p.level, p.status,
       t.name AS territory_name, p.built_at, p.upgrades_applied
FROM maya_rp.ports p
JOIN maya_rp.port_types pt ON pt.id = p.port_type_id
JOIN maya_rp.territory t ON t.id = p.territory_id;

-- ============================================================
-- 7. Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_mega_const_session ON maya_rp.megastructure_construction(session_id);
CREATE INDEX IF NOT EXISTS idx_mega_const_status ON maya_rp.megastructure_construction(status);
CREATE INDEX IF NOT EXISTS idx_ports_session ON maya_rp.ports(session_id);
CREATE INDEX IF NOT EXISTS idx_ports_territory ON maya_rp.ports(territory_id);
CREATE INDEX IF NOT EXISTS idx_port_upgrades_port ON maya_rp.port_upgrades(port_id);

-- ============================================================
-- 8. Migration tracking
-- ============================================================
INSERT INTO maya_rp.migration_hashes (filename, sha256, applied_at)
VALUES ('049-megastructures-ports.sql', encode(sha256('049-megastructures-ports'::bytea), 'hex'), NOW())
ON CONFLICT (filename) DO NOTHING;
