-- 050-infrastructure-overhaul.sql
-- Enhanced mining, refineries, stations, factories, farms, defense, logistics, arcane structures.
CREATE TABLE IF NOT EXISTS maya_rp.infrastructure_types (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,  -- mining, refinery, station, factory, farm, defense, logistics, arcane
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    fantasy_tier VARCHAR(20),      -- common, uncommon, rare, epic, legendary
    build_cost_credits INT,
    build_cost_resources JSONB,
    upkeep_credits INT,
    upkeep_resources JSONB,
    construction_time_days INT,
    effects JSONB,
    required_tech VARCHAR(100),
    size INT DEFAULT 1,
    slots_used INT DEFAULT 1
);

INSERT INTO maya_rp.infrastructure_types
    (category, name, description, fantasy_tier, build_cost_credits, build_cost_resources,
     upkeep_credits, upkeep_resources, construction_time_days, effects, required_tech, size, slots_used)
VALUES
-- MINING
('mining', 'Surface Mine', 'Extracts basic minerals from planetary crust.',
 'common', 10000, '{"alloys":200}', 200, '{}', 5,
 '{"mining_mult":1.2,"alloy_production":50}', '', 1, 1),
('mining', 'Deep Core Mine', 'Rich deposits deep underground.',
 'uncommon', 30000, '{"alloys":800,"rare_earth":10}', 500, '{"fuel":20}', 10,
 '{"mining_mult":2.0,"alloy_production":150,"rare_earth_production":5}', 'deep_mining_tech', 2, 2),
('mining', 'Asteroid Harvester', 'Mines asteroid belts for rare minerals.',
 'rare', 50000, '{"alloys":1200,"fuel":300}', 800, '{"fuel":50}', 15,
 '{"mining_mult":1.8,"rare_earth_production":10,"alloy_production":100}', 'asteroid_tech', 2, 2),
('mining', 'Gas Giant Harvester', 'Extracts fuel and exotic gases.',
 'rare', 80000, '{"alloys":2000,"rare_earth":30}', 1200, '{"fuel":100}', 20,
 '{"fuel_production":500,"rare_earth_production":5,"dream_essence":1}', 'gas_harvest_tech', 3, 3),
('mining', 'Arcane Crystal Mine', 'Mines magical crystals for arcane purposes.',
 'epic', 120000, '{"alloys":3000,"aetherium":20}', 2000, '{"dream_essence":10}', 30,
 '{"dream_essence_production":5,"aetherium_production":2}', 'arcane_mining_tech', 3, 3),

-- REFINERIES
('refinery', 'Basic Refinery', 'Processes raw ore into usable alloys.',
 'common', 15000, '{"alloys":300}', 300, '{}', 6,
 '{"alloy_bonus":50}', '', 1, 1),
('refinery', 'Advanced Smelter', 'High-efficiency alloy production.',
 'uncommon', 40000, '{"alloys":1000,"rare_earth":5}', 600, '{"fuel":30}', 12,
 '{"alloy_bonus":150}', 'smelting_tech', 2, 2),
('refinery', 'Fuel Processor', 'Converts raw fuel into high-grade propellant.',
 'rare', 60000, '{"alloys":1500,"fuel":400}', 800, '{"fuel":60}', 14,
 '{"fuel_bonus":200}', 'fuel_tech', 2, 2),
('refinery', 'Alchemical Crucible', 'Magically transmutes materials.',
 'epic', 100000, '{"alloys":2500,"dream_essence":30}', 1500, '{"dream_essence":5}', 25,
 '{"dream_essence_production":2}', 'alchemy_tech', 3, 3),
('refinery', 'Stellar Forge Refinery', 'Processes starsteel and exotic materials.',
 'legendary', 250000, '{"alloys":5000,"starsteel":10}', 3000, '{"fuel":100,"dream_essence":10}', 40,
 '{"starsteel_production":5,"void_crystal_production":1}', 'stellar_forge_tech', 4, 4),

-- STATIONS
('station', 'Orbital Habitat', 'Space-based habitation.',
 'common', 20000, '{"alloys":400}', 500, '{}', 8,
 '{"population_bonus":1000}', '', 2, 2),
('station', 'Research Station', 'Orbital laboratory.',
 'uncommon', 50000, '{"alloys":1000,"rare_earth":10}', 800, '{"fuel":20}', 12,
 '{"research_bonus":10}', 'research_tech', 2, 2),
('station', 'Defense Platform', 'Weapons platform for system defense.',
 'rare', 80000, '{"alloys":2000,"fuel":200}', 1200, '{"fuel":50}', 18,
 '{"defense_power":500}', 'defense_tech', 3, 3),
('station', 'Trade Station', 'Hub for interstellar commerce.',
 'rare', 100000, '{"alloys":2500,"rare_earth":20}', 1500, '{"fuel":30}', 20,
 '{"trade_bonus":10}', 'trade_tech', 3, 3),
('station', 'Arcane Observatory', 'Studies cosmic magic and dimensional rifts.',
 'epic', 150000, '{"alloys":3000,"aetherium":15,"dream_essence":20}', 2000, '{"dream_essence":5}', 28,
 '{"research_bonus":20,"dream_essence_production":3}', 'arcane_tech', 3, 3),
('station', 'Mega Shipyard', 'Massive orbital construction facility.',
 'legendary', 300000, '{"alloys":8000,"starsteel":5}', 5000, '{"fuel":200}', 45,
 '{"build_speed_mult":0.5,"ship_cost_reduction":0.2}', 'mega_engineering', 5, 5),

-- FACTORIES
('factory', 'Assembly Plant', 'Produces manufactured goods.',
 'common', 12000, '{"alloys":250}', 250, '{}', 5,
 '{"credits_bonus":100}', '', 1, 1),
('factory', 'Industrial Complex', 'Large-scale manufacturing.',
 'uncommon', 40000, '{"alloys":1000,"fuel":100}', 600, '{"fuel":30}', 12,
 '{"alloy_bonus":100,"credits_bonus":300}', 'industrial_tech', 2, 2),
('factory', 'Nanite Forge', 'Precision micro-assembly.',
 'rare', 80000, '{"alloys":2000,"rare_earth":20}', 1000, '{"fuel":50}', 18,
 '{"research_bonus":15}', 'nanite_tech', 2, 2),

-- FARMS
('farm', 'Hydroponic Farm', 'Food production.',
 'common', 8000, '{"alloys":200}', 150, '{}', 4,
 '{"food_bonus":100}', '', 1, 1),
('farm', 'Bio-dome', 'Large-scale agriculture.',
 'uncommon', 25000, '{"alloys":600,"food":100}', 400, '{"food":20}', 8,
 '{"food_bonus":300}', 'bio_tech', 2, 2),
('farm', 'Mana Grove', 'Magical plantation for dream essence.',
 'epic', 60000, '{"alloys":1500,"dream_essence":10}', 800, '{"dream_essence":2}', 16,
 '{"dream_essence_production":2,"food_bonus":100}', 'mana_tech', 2, 2),

-- DEFENSE
('defense', 'Shield Generator', 'Planetary shield.',
 'uncommon', 40000, '{"alloys":1000,"rare_earth":5}', 500, '{"fuel":20}', 10,
 '{"defense_power":200}', 'shield_tech', 2, 2),
('defense', 'Ion Cannon', 'Anti-ship defensive cannon.',
 'rare', 80000, '{"alloys":2000,"rare_earth":10}', 800, '{"fuel":50}', 14,
 '{"defense_power":500}', 'ion_tech', 3, 3),
('defense', 'Arcane Ward', 'Magical barrier.',
 'epic', 120000, '{"alloys":3000,"aetherium":10,"dream_essence":20}', 1200, '{"dream_essence":5}', 20,
 '{"defense_power":400,"morale_bonus":10}', 'arcane_ward_tech', 3, 3),

-- LOGISTICS
('logistics', 'Cargo Depot', 'Storage and distribution hub.',
 'common', 15000, '{"alloys":300}', 200, '{}', 5,
 '{"trade_bonus":5}', '', 1, 1),
('logistics', 'Logistics Hub', 'Advanced distribution network.',
 'uncommon', 40000, '{"alloys":1000,"fuel":100}', 500, '{"fuel":20}', 10,
 '{"trade_bonus":10}', 'logistics_tech', 2, 2),

-- ARCANE
('arcane', 'Dream Spire', 'Amplifies dream essence extraction.',
 'epic', 150000, '{"alloys":3000,"dream_essence":50,"aetherium":20}', 2500, '{"dream_essence":10}', 30,
 '{"dream_essence_production":5,"research_bonus":10}', 'dream_tech', 3, 3),
('arcane', 'Void Gate', 'Stable wormhole for instant travel.',
 'legendary', 500000, '{"alloys":10000,"void_crystal":5,"starsteel":20}', 10000, '{"dream_essence":20}', 60,
 '{"trade_bonus":50}', 'void_gate_tech', 5, 5);

-- ============================================================
-- 2. Installed Infrastructure (per territory / sector)
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.infrastructure_instances (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    infrastructure_type_id INT REFERENCES maya_rp.infrastructure_types(id) ON DELETE CASCADE,
    territory_id INT REFERENCES maya_rp.territory(id) ON DELETE CASCADE,
    sector_id INT REFERENCES maya_rp.sectors(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    level INT DEFAULT 1,
    status VARCHAR(20) DEFAULT 'active',  -- active, damaged, destroyed, under_construction
    built_at TIMESTAMP DEFAULT NOW(),
    last_upgrade TIMESTAMP,
    upgrades_applied JSONB DEFAULT '[]',
    production_bonus NUMERIC DEFAULT 1.0
);

-- ============================================================
-- 3. Resource Production Log
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.infrastructure_production (
    id SERIAL PRIMARY KEY,
    infrastructure_id INT REFERENCES maya_rp.infrastructure_instances(id) ON DELETE CASCADE,
    resource_type VARCHAR(50) NOT NULL,
    amount_produced INT DEFAULT 0,
    produced_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 4. Views
-- ============================================================
CREATE OR REPLACE VIEW maya_rp.infrastructure_overview AS
SELECT ii.id, ii.name, it.name AS type_name, it.category, it.fantasy_tier,
       ii.level, ii.status, t.name AS territory_name, s.name AS sector_name,
       ii.built_at, ii.upgrades_applied
FROM maya_rp.infrastructure_instances ii
JOIN maya_rp.infrastructure_types it ON it.id = ii.infrastructure_type_id
LEFT JOIN maya_rp.territory t ON t.id = ii.territory_id
LEFT JOIN maya_rp.sectors s ON s.id = ii.sector_id;

-- ============================================================
-- 5. Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_infra_inst_session ON maya_rp.infrastructure_instances(session_id);
CREATE INDEX IF NOT EXISTS idx_infra_inst_territory ON maya_rp.infrastructure_instances(territory_id);
CREATE INDEX IF NOT EXISTS idx_infra_inst_status ON maya_rp.infrastructure_instances(status);
CREATE INDEX IF NOT EXISTS idx_infra_prod_infra ON maya_rp.infrastructure_production(infrastructure_id);

-- ============================================================
-- 6. Migration tracking
-- ============================================================
INSERT INTO maya_rp.migration_hashes (filename, sha256, applied_at)
VALUES ('050-infrastructure-overhaul.sql', encode(sha256('050-infrastructure-overhaul'::bytea), 'hex'), NOW())
ON CONFLICT (filename) DO NOTHING;
