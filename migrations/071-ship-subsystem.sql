-- 071: Ship subsystem — power_rating + sub_class + sub-class variants
-- Fixes: class_id mismatch (role->class), hull below class base,
-- missing power_rating, and adds per-role variant sub-classes.

-- ── 1. ships: add power_rating + sub_class ─────────────────────────────
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS power_rating INT DEFAULT 0;
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS sub_class TEXT;

-- ── 2. ship_sub_classes: variant definitions per ship_type ─────────────
CREATE TABLE IF NOT EXISTS maya_rp.ship_sub_classes (
    id             SERIAL PRIMARY KEY,
    ship_type      TEXT NOT NULL,          -- role (interceptor, frigate, ...)
    sub_class      TEXT NOT NULL,          -- variant name (Light Interceptor, ...)
    hull_mult      NUMERIC(5,2) NOT NULL DEFAULT 1.00,
    speed_mult     NUMERIC(5,2) NOT NULL DEFAULT 1.00,
    crew_mult      NUMERIC(5,2) NOT NULL DEFAULT 1.00,
    power_mult     NUMERIC(5,2) NOT NULL DEFAULT 1.00,
    description    TEXT,
    UNIQUE (ship_type, sub_class)
);

-- ── 3. Seed variant sub-classes (2-3 per role) ─────────────────────────
INSERT INTO maya_rp.ship_sub_classes (ship_type, sub_class, hull_mult, speed_mult, crew_mult, power_mult, description) VALUES
-- Interceptors
('interceptor',     'Light Interceptor',   0.80, 1.20, 0.80, 0.90, 'Fast, fragile, swarm fighter'),
('interceptor',     'Interceptor',         1.00, 1.00, 1.00, 1.00, 'Standard fighter'),
('interceptor',     'Heavy Interceptor',   1.25, 0.85, 1.15, 1.15, 'Armored fighter'),
-- Scouts / recon
('spy_plane',       'Recon Drone',         0.85, 1.15, 0.80, 0.90, 'Fast light recon'),
('spy_plane',       'Deep Scan',           1.15, 0.90, 1.10, 1.10, 'Heavy sensor platform'),
-- Patrol
('patrol_boat',     'Patrol Cutter',       1.00, 1.00, 1.00, 1.00, 'Standard patrol'),
('patrol_boat',     'Customs Boat',        0.85, 1.10, 1.10, 0.90, 'Boarding / inspection'),
-- Frigates
('frigate',         'Escort Frigate',      0.90, 1.10, 0.90, 0.95, 'Anti-fighter escort'),
('frigate',         'Frigate',             1.00, 1.00, 1.00, 1.00, 'Line frigate'),
('frigate',         'Assault Frigate',     1.20, 0.90, 1.10, 1.15, 'Heavy guns'),
-- Cruisers
('medium_cruiser',  'Strike Cruiser',      1.00, 1.05, 1.00, 1.10, 'Offensive cruiser'),
('medium_cruiser',  'Escort Cruiser',      1.10, 0.95, 1.10, 1.00, 'Fleet escort cruiser'),
('heavy_cruiser',   'Line Cruiser',        1.00, 1.00, 1.00, 1.00, 'Batteline cruiser'),
('heavy_cruiser',   'Command Cruiser',     1.15, 0.90, 1.25, 1.15, 'Flag bridge'),
-- Battle cruisers
('battle_cruiser',  'Assault Battlecruiser', 1.00, 1.05, 1.00, 1.10, 'Brawler'),
('battle_cruiser',  'Command Battlecruiser', 1.15, 0.90, 1.25, 1.15, 'Flagship role'),
-- Bombers
('bomber',          'Dive Bomber',         0.90, 1.15, 0.90, 1.00, 'Precision strike'),
('bomber',          'Torpedo Bomber',      1.15, 0.85, 1.10, 1.15, 'Capital-killer'),
-- EW
('ew_ship',         'Jammer',              1.00, 1.00, 1.00, 1.10, 'ECM jamming'),
('ew_ship',         'Decoy',               0.85, 1.10, 0.90, 0.90, 'False signatures'),
-- Static defense
('orbital_fortress','Bastion',             1.00, 1.00, 1.00, 1.00, 'Heavy fortress'),
('orbital_fortress','Bunker',              1.15, 0.90, 1.10, 1.10, 'Armored keep'),
('missile_battery', 'Salvo Battery',       1.00, 1.00, 1.00, 1.10, 'Rapid volleys'),
('missile_battery', 'Siege Battery',       1.15, 0.90, 1.10, 1.15, 'Heavy ordnance'),
('pd_platform',     'Point Defense',       1.00, 1.00, 1.00, 1.00, 'PD turrets'),
('pd_platform',     'Flak',                0.90, 1.15, 0.90, 1.05, 'Area denial'),
('minelayer',       'Mine Layer',          1.00, 1.00, 1.00, 1.00, 'Standard mining'),
('minelayer',       'Minefield',           1.10, 0.90, 1.10, 1.10, 'Dense fields'),
('defense_monitor', 'Watch',               0.90, 1.10, 0.90, 0.95, 'Surveillance monitor'),
('defense_monitor', 'Sentinel',            1.10, 0.90, 1.10, 1.10, 'Armed monitor'),
-- Logistics
('supply_courier',  'Fast Courier',        0.85, 1.25, 0.85, 0.95, 'Priority freight'),
('supply_courier',  'Bulk Courier',        1.15, 0.85, 1.10, 1.05, 'Mass cargo'),
('cargo_freighter', 'Bulk Carrier',        1.00, 1.00, 1.00, 1.00, 'Freight'),
('cargo_freighter', 'Container',           1.10, 0.95, 1.05, 1.05, 'Modular cargo'),
('fuel_tanker',     'Fuel Tanker',         1.00, 1.00, 1.00, 1.00, 'Fuel'),
('fuel_tanker',     'Hydrogen Carrier',    1.15, 0.90, 1.10, 1.05, 'Reaction mass'),
('ammo_ship',       'Munitions',           1.00, 1.00, 1.00, 1.00, 'Ordnance stores'),
('ammo_ship',       'Ordnance',            1.10, 0.95, 1.05, 1.05, 'Deep magazines'),
('repair_tender',   'Repair Tender',       1.00, 1.00, 1.00, 1.00, 'Field repair'),
('repair_tender',   'Salvage',             1.10, 0.95, 1.10, 1.05, 'Recovery ops'),
('hospital_ship',   'Medical',             1.00, 1.00, 1.00, 1.00, 'Hospital'),
('hospital_ship',   'Evac',                0.85, 1.15, 1.10, 0.95, 'Casualty evacuation'),
('harvester',       'Ore Harvester',       1.00, 1.00, 1.00, 1.00, 'Mining'),
('harvester',       'Gas Skimmer',         0.85, 1.15, 0.90, 0.95, 'Gas giant ops'),
('refinery',        'Ore Refinery',        1.00, 1.00, 1.00, 1.00, 'Smelting'),
('refinery',        'Fuel Refinery',       1.10, 0.90, 1.10, 1.05, 'Fuel processing'),
-- Science
('science_vessel',  'Research',            1.00, 1.00, 1.00, 1.00, 'Lab ship'),
('science_vessel',  'Survey',              0.90, 1.10, 0.90, 0.95, 'Cartography'),
('science_small',   'Probe Tender',        1.00, 1.00, 1.00, 1.00, 'Small science'),
('science_medium',  'Field Lab',           1.00, 1.00, 1.00, 1.00, 'Mid science'),
('science_large',   'Deep Research',       1.00, 1.00, 1.00, 1.00, 'Flagship science'),
-- Yards
('arkship',         'Colony Ark',          1.00, 1.00, 1.00, 1.00, 'Mobile colony'),
('arkship',         'Mobile Foundry',      1.15, 0.90, 1.15, 1.10, 'Industrial ark'),
('heavy_shipyard',  'Assembly Yard',       1.00, 1.00, 1.00, 1.00, 'Heavy construction'),
('heavy_shipyard',  'Capital Yard',        1.15, 0.90, 1.15, 1.10, 'Capital-class slips'),
('fleet_yard',      'Fleet Yard',          1.00, 1.00, 1.00, 1.00, 'Fleet construction'),
('fleet_yard',      'Resupply Yard',       1.10, 0.95, 1.10, 1.05, 'Logistics hub'),
('light_dockyard',  'Repair Dock',         1.00, 1.00, 1.00, 1.00, 'Docking'),
('light_dockyard',  'Small Yard',          1.10, 0.95, 1.10, 1.05, 'Small craft slips'),
-- Capital
('escort_capital',  'Capital Escort',      1.00, 1.00, 1.00, 1.00, 'Capital screening'),
('escort_capital',  'Flagship Guard',      1.15, 0.90, 1.15, 1.10, 'Flagship escort'),
('capital-ship',    'Dreadnought',         1.00, 1.00, 1.00, 1.00, 'Flagship capital'),
('unknown_colossal','Colossal',            1.00, 1.00, 1.00, 1.00, 'Unknown colossal')
ON CONFLICT (ship_type, sub_class) DO NOTHING;

-- ── 4. GS integrated: sub-class names ──────────────────────────────────
INSERT INTO maya_rp.ship_sub_classes (ship_type, sub_class, hull_mult, speed_mult, crew_mult, power_mult, description) VALUES
('DRM', 'Phantom Dreadnought', 1.00, 1.00, 1.00, 1.00, 'Ghost Signal capital'),
('SPC', 'Ghost Frigate',       1.00, 1.00, 1.00, 1.00, 'Ghost Signal frigate'),
('SPC', 'Wraith Cruiser',      1.00, 1.00, 1.00, 1.00, 'Ghost Signal cruiser')
ON CONFLICT (ship_type, sub_class) DO NOTHING;

-- ── 5. Grants ──────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON maya_rp.ship_sub_classes TO rp_engine;
GRANT USAGE, SELECT ON SEQUENCE maya_rp.ship_sub_classes_id_seq TO rp_engine;
