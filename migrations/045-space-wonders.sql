-- 045-space-wonders.sql
-- Space Wonders: planet types, space animals, anomalies, discoveries
-- Designed in RP-Session-3, migration 045

-- ============================================================
-- 1. Planet Types Catalog
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.planet_types_catalog (
    name VARCHAR(50) PRIMARY KEY,
    description TEXT,
    habitability_min NUMERIC DEFAULT 0,
    habitability_max NUMERIC DEFAULT 100,
    special_events TEXT[], -- array of event triggers available on this type
    resource_modifiers JSONB DEFAULT '{}', -- e.g. {"alloys": 1.5, "fuel": 0.8}
    rarity VARCHAR(20) DEFAULT 'common'
);

INSERT INTO maya_rp.planet_types_catalog (name, description, habitability_min, habitability_max, special_events, resource_modifiers, rarity) VALUES
('Terran', 'Earth-like world. Ideal for colonization.', 60, 100, '{fertile_soil, pristine_ecosystem}', '{"food": 1.5, "alloys": 1.0, "research": 1.2}', 'common'),
('Ocean', 'Water world with vast oceans and island chains.', 40, 80, '{submerged_ruins, rare_fish, tidal_disaster}', '{"food": 2.0, "fuel": 0.5, "alloys": 0.6}', 'common'),
('Desert', 'Arid world with extreme temperatures.', 20, 50, '{sandstorm, ancient_ruins, oasis}', '{"fuel": 1.3, "alloys": 1.1, "food": 0.3}', 'common'),
('Tundra', 'Frozen world with sparse vegetation.', 10, 40, '{ice_caves, cryo_deposits, glacial_melt}', '{"research": 1.3, "alloys": 1.2, "food": 0.4}', 'common'),
('Volcanic', 'Molten hellscape with rich mineral veins.', 0, 20, '{eruption, lava_tube, rare_crystals}', '{"alloys": 2.0, "fuel": 1.5, "food": 0}', 'uncommon'),
('Gas Giant', 'Massive gaseous planet. No surface. Harvestable.', 0, 0, '{storm_harvest, atmospheric_rare_gas, lightning_field}', '{"fuel": 3.0, "research": 1.5, "alloys": 0}', 'uncommon'),
('Barren', 'Dead rock. Minimal resources but stable.', 0, 10, '{meteor_impact, cave_system, mineral_vein}', '{"alloys": 1.5, "fuel": 0.5, "food": 0}', 'common'),
('Gaia', 'Perfect world. Rare and valuable.', 90, 100, '{paradise_found, ancient_garden, harmony}', '{"food": 2.5, "alloys": 1.5, "research": 1.5, "fuel": 1.5}', 'epic'),
('Tomb', 'Scorched and lifeless. Possible past civilization.', 0, 5, '{fallen_empire_relic, toxic_cloud, prewar_vault}', '{"research": 2.0, "alloys": 0.5, "food": 0}', 'rare'),
('Ringworld', 'Artificial ring. Massive surface area.', 50, 100, '{alien_architecture, control_center, section_collapse}', '{"research": 3.0, "alloys": 2.0, "food": 1.5, "fuel": 2.0}', 'legendary');

-- ============================================================
-- 2. Planet Special Features
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.planet_features (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    planet_type VARCHAR(50) REFERENCES maya_rp.planet_types_catalog(name),
    description TEXT,
    effect JSONB, -- effect on gameplay
    rarity VARCHAR(20) DEFAULT 'common'
);

INSERT INTO maya_rp.planet_features (name, planet_type, description, effect, rarity) VALUES
('Fertile Soil', 'Terran', 'Crops grow 30% faster.', '{"food_mult": 1.3}', 'common'),
('Pristine Ecosystem', 'Terran', 'Unique flora and fauna for research.', '{"research_bonus": 10}', 'uncommon'),
('Submerged Ruins', 'Ocean', 'Ancient structures beneath the waves.', '{"archaeology_bonus": 15}', 'uncommon'),
('Rare Fish', 'Ocean', 'Exotic aquatic life prized by collectors.', '{"trade_value": 500}', 'common'),
('Sandstorm Belt', 'Desert', 'Constant storms hinder operations.', '{"build_time_penalty": -0.2}', 'common'),
('Ancient Ruins', 'Desert', 'Artifacts buried beneath the sand.', '{"artifact_chance": 0.3}', 'rare'),
('Ice Caves', 'Tundra', 'Natural formations with rare crystals.', '{"rare_earth_bonus": 1.5}', 'uncommon'),
('Cryo Deposits', 'Tundra', 'Frozen gases for fuel refinement.', '{"fuel_mult": 1.4}', 'common'),
('Lava Tube Network', 'Volcanic', 'Stable tunnels for mining operations.', '{"alloys_mult": 1.3}', 'uncommon'),
('Rare Crystal Formations', 'Volcanic', 'Precious crystals used in advanced tech.', '{"research_bonus": 20, "trade_value": 1000}', 'rare'),
('Atmospheric RNG', 'Gas Giant', 'Rare gases for exotic fuel.', '{"fuel_mult": 1.5}', 'uncommon'),
('Lightning Field', 'Gas Giant', 'Constant electrical storms. Dangerous but valuable.', '{"energy_bonus": 25, "danger": 0.1}', 'rare'),
('Meteor Impact Site', 'Barren', 'Recent impact exposed rich mineral veins.', '{"alloys_mult": 1.4}', 'common'),
('Deep Cave System', 'Barren', 'Extensive caves may harbor secrets.', '{"exploration_bonus": 10}', 'uncommon'),
('Paradise Found', 'Gaia', 'Perfect ecosystem. Every resource abundant.', '{"all_mult": 1.5}', 'legendary'),
('Ancient Garden', 'Gaia', 'Remnants of a precursor botanical project.', '{"research_bonus": 30}', 'legendary'),
('Fallen Empire Relic', 'Tomb', 'Ruins of a dead civilization.', '{"tech_unlock_chance": 0.5}', 'legendary'),
('Pre-War Vault', 'Tomb', 'Underground bunker with preserved tech.', '{"artifact_guaranteed": true}', 'epic'),
('Alien Architecture', 'Ringworld', 'Non-human construction techniques.', '{"research_bonus": 50}', 'legendary'),
('Control Center', 'Ringworld', 'Ringworld control systems still operational.', '{"sector_effect": "ring_control"}', 'legendary');

-- ============================================================
-- 3. Space Animals
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.space_animals (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    species VARCHAR(100) NOT NULL,
    description TEXT,
    habitat VARCHAR(50), -- nebula, asteroid, deep_space, gas_giant, etc.
    aggression INT DEFAULT 5, -- 1-10
    taming_difficulty INT DEFAULT 5, -- 1-10
    resource_value JSONB DEFAULT '{"credits": 100}', -- what you get from hunting
    special_ability TEXT, -- if tamed, what it does
    rarity VARCHAR(20) DEFAULT 'common'
);

INSERT INTO maya_rp.space_animals (name, species, description, habitat, aggression, taming_difficulty, resource_value, special_ability, rarity) VALUES
('Void Leviathan', 'Cetus Galactica', 'A colossal space whale that drifts through nebulae.', 'nebula', 3, 8, '{"credits": 5000, "rare_earth": 10, "fuel": 2000}', 'Navigation boost when tamed', 'epic'),
('Solar Drake', 'Ignis Volantis', 'A serpentine creature that feeds on solar radiation.', 'star', 7, 9, '{"credits": 8000, "rare_earth": 15, "research": 50}', 'Solar energy harvesting', 'legendary'),
('Crystal Scorpion', 'Crystallis Scolopendra', 'A crystalline lifeform found in asteroid belts.', 'asteroid', 6, 6, '{"credits": 2000, "alloys": 500, "rare_earth": 5}', 'Asteroid mining bonus', 'uncommon'),
('Nebula Jellyfish', 'Aether Medusa', 'Translucent jellyfish that drifts through gas clouds.', 'nebula', 2, 4, '{"credits": 500, "fuel": 300}', 'Sensor improvement', 'common'),
('Void Kraken', 'Abyssus Polypus', 'A massive tentacled beast lurking in deep space.', 'deep_space', 9, 10, '{"credits": 15000, "rare_earth": 25, "alloys": 2000, "artifact_chance": 0.5}', 'Ultimate combat pet', 'legendary'),
('Plasma Eel', 'Fulgur Anguilla', 'An eel that swims through solar plasma.', 'star', 5, 7, '{"credits": 3000, "fuel": 1000, "research": 20}', 'Energy weapon enhancement', 'rare'),
('Rust Beetle', 'Ferrum Coleopteran', 'A metallic beetle that eats hull fragments.', 'asteroid', 4, 3, '{"credits": 300, "alloys": 200}', 'Hull repair', 'common'),
('Phase Shifter', 'Quantuum Chimaera', 'An unstable creature that flickers in and out of phase.', 'deep_space', 8, 9, '{"credits": 6000, "research": 40, "rare_earth": 12}', 'Cloaking field', 'legendary'),
('Gas Bag', 'Hydrogen Saccus', 'A balloon-like creature filled with harvestable gas.', 'gas_giant', 1, 2, '{"credits": 200, "fuel": 500}', 'Fuel production', 'common'),
('Swarm', 'Nanobotis Hive', 'A cloud of nanite-like organisms.', 'asteroid', 6, 5, '{"credits": 1000, "research": 30}', 'Research speed boost', 'uncommon');

-- ============================================================
-- 4. Space Anomalies
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.space_anomalies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL, -- wormhole, temporal, gravitational, cosmic, quantum
    description TEXT,
    discovery_trigger VARCHAR(50), -- scan_low, scan_high, explore, combat, event
    reward_pool JSONB DEFAULT '{"credits": 500}',
    danger_level INT DEFAULT 1, -- 1-10
    effects JSONB, -- permanent effects on system/empire
    active BOOLEAN DEFAULT TRUE,
    rarity VARCHAR(20) DEFAULT 'common'
);

INSERT INTO maya_rp.space_anomalies (name, type, description, discovery_trigger, reward_pool, danger_level, effects, active, rarity) VALUES
('Wormhole', 'wormhole', 'A stable tunnel through spacetime to another system.', 'scan_high', '{"research": 100, "exploration": "new_system"}', 2, '{"wormhole_destination": null}', TRUE, 'rare'),
('Temporal Rift', 'temporal', 'A tear in time. Past and future bleed through.', 'explore', '{"credits": 3000, "research": 200, "artifact_chance": 0.7}', 6, '{"time_distortion": true}', TRUE, 'legendary'),
('Gravity Well', 'gravitational', 'Extreme gravitational anomaly. Warps space around it.', 'scan_low', '{"alloys": 1000, "fuel": 500}', 4, '{"gravity_modifier": 1.5}', TRUE, 'uncommon'),
('Cosmic String', 'cosmic', 'A one-dimensional defect in spacetime. Infinite density.', 'scan_high', '{"research": 500, "rare_earth": 20}', 8, '{"energy_harvest": true}', TRUE, 'legendary'),
('Quantum Flux', 'quantum', 'Reality fluctuates. Matter appears and disappears.', 'explore', '{"credits": 2000, "alloys": 500, "rare_earth": 5}', 5, '{"quantum_instability": true}', TRUE, 'rare'),
('Dark Matter Concentratio', 'gravitational', 'A pocket of dense dark matter affecting local gravity.', 'scan_low', '{"research": 150, "fuel": 200}', 3, '{"research_bonus": 15}', TRUE, 'uncommon'),
('Pulsar Beacon', 'cosmic', 'A rotating neutron star emitting periodic signals.', 'scan_high', '{"research": 300, "rare_earth": 10}', 1, '{"navigation_bonus": true}', TRUE, 'rare'),
('Event Horizon Echo', 'temporal', 'Residual energy from a past singularity event.', 'explore', '{"credits": 5000, "research": 400}', 9, '{"danger_warning": true}', TRUE, 'legendary'),
('Nebula Bloom', 'cosmic', 'A nebula with unusual organic compounds.', 'explore', '{"food": 2000, "research": 100, "rare_earth": 3}', 2, '{"biological_bonus": true}', TRUE, 'common'),
('Void Whisper', 'quantum', 'Unintelligible signals from the void between galaxies.', 'scan_high', '{"research": 1000, "artifact_chance": 0.9}', 10, '{"void_connection": true}', TRUE, 'legendary');

-- ============================================================
-- 5. Discoveries & Encounters
-- ============================================================
CREATE TABLE IF NOT EXISTS maya_rp.discoveries (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    type VARCHAR(30) NOT NULL, -- planet, animal, anomaly, artifact
    target_id INT NOT NULL, -- FK to the specific table
    discovered_at TIMESTAMP DEFAULT NOW(),
    explored BOOLEAN DEFAULT FALSE,
    explored_at TIMESTAMP,
    results JSONB -- outcome of exploration
);

CREATE TABLE IF NOT EXISTS maya_rp.animal_encounters (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES maya_rp.sessions(id) ON DELETE CASCADE,
    animal_id INT REFERENCES maya_rp.space_animals(id) ON DELETE CASCADE,
    system_id INT REFERENCES maya_rp.sectors(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'active', -- active, hunted, tamed, fled
    encountered_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    outcome VARCHAR(50)
);

-- ============================================================
-- 6. Planet table enhancements
-- ============================================================
ALTER TABLE maya_rp.planets
    ADD COLUMN IF NOT EXISTS planet_type VARCHAR(50) REFERENCES maya_rp.planet_types_catalog(name),
    ADD COLUMN IF NOT EXISTS features JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS surveyed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS resource_modifiers JSONB DEFAULT '{}';

-- ============================================================
-- 7. Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_discoveries_session ON maya_rp.discoveries(session_id);
CREATE INDEX IF NOT EXISTS idx_discoveries_type ON maya_rp.discoveries(type);
CREATE INDEX IF NOT EXISTS idx_animal_encounters_session ON maya_rp.animal_encounters(session_id);
CREATE INDEX IF NOT EXISTS idx_animal_encounters_status ON maya_rp.animal_encounters(status);
CREATE INDEX IF NOT EXISTS idx_planets_type ON maya_rp.planets(planet_type);

-- ============================================================
-- 8. Migration tracking
-- ============================================================
INSERT INTO maya_rp.migration_hashes (filename, sha256, applied_at)
VALUES ('045-space-wonders.sql', encode(sha256('045-space-wonders'::bytea), 'hex'), NOW())
ON CONFLICT (filename) DO NOTHING;
