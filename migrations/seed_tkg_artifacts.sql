-- TKG Galaxy Beauties Artifacts
SET LOCAL search_path TO maya_rp;
INSERT INTO maya_rp.artifacts (session_id, name, type, rarity, description, bonus) VALUES
    (3, 'Seraphina Vey - Starchild Compass', 'relic', 'legendary', 'Navigates by instinct. Can predict solar activity.', 15),
    (3, 'Mira - Vein Station Echo', 'data_core', 'epic', 'Omniscient within Vein Network. Knows every transit.', 12),
    (3, 'Aeliana - Oracle Probability Thread', 'relic', 'legendary', 'Sees futures with 89% accuracy.', 15),
    (3, 'Nyx - Shadow Weaver Cloak', 'armor', 'epic', 'Controls shadows. Phase through matter.', 10),
    (3, 'Celestine Voss - Stellar Forge Hammer', 'tool', 'rare', 'Forges materials in stellar cores.', 8),
    (3, 'Lyra - Harmony Resonator', 'energy_cell', 'rare', 'Emotional frequency modulator. Calms crowds.', 7),
    (3, 'Isara - Tide Caller Pearl', 'energy_cell', 'epic', 'Controls wave patterns. Oceanic mastery.', 10),
    (3, 'Kaelen - Echo Shard', 'data_core', 'rare', 'Minutes of past conversations replayed perfectly.', 6),
    (3, 'Sylva - Rootweaver Seed', 'biological', 'rare', 'Grows plants anywhere. Terraforming accelerator.', 7),
    (3, 'Veyna - Void Lens', 'energy_cell', 'epic', 'Sees through any material up to 500m.', 11)
ON CONFLICT DO NOTHING;

-- Production lines on Pelabuhan
INSERT INTO maya_rp.production_lines (colony_id, name, recipe_id, status, efficiency)
SELECT c.id, 'Pelabuhan Alloy Line', r.id, 'running', 0.85
FROM maya_rp.recipes r, (SELECT id FROM maya_rp.colonies WHERE name='Pelabuhan' AND session_id=3 LIMIT 1) c
WHERE r.name='Alloy Ingot Smelting'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.production_lines WHERE name='Pelabuhan Alloy Line')
UNION ALL
SELECT c.id, 'Pelabuhan Fuel Refinery', r.id, 'idle', 0.75
FROM maya_rp.recipes r, (SELECT id FROM maya_rp.colonies WHERE name='Pelabuhan' AND session_id=3 LIMIT 1) c
WHERE r.name='Refined Fuel Production'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.production_lines WHERE name='Pelabuhan Fuel Refinery')
UNION ALL
SELECT c.id, 'Pelabuhan Medical Bay', r.id, 'running', 1.0
FROM maya_rp.recipes r, (SELECT id FROM maya_rp.colonies WHERE name='Pelabuhan' AND session_id=3 LIMIT 1) c
WHERE r.name='Medical Supply Pack'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.production_lines WHERE name='Pelabuhan Medical Bay');

-- Technologies tree — from TKG tech levels
INSERT INTO maya_rp.technologies (session_id, name, field, tier, researched, research_progress, prerequisites, unlocks) VALUES
    (3, 'Fusion Power I', 'energy', 1, true, 100, '[]', '{"buildings":["Fusion Reactor Mk1"]}'),
    (3, 'Basic Alloy Smelting', 'materials', 1, true, 100, '[]', '{"recipes":["Alloy Ingot Smelting"]}'),
    (3, 'Hull Reinforcement', 'defense', 2, true, 100, '[]', '{"modules":["Composite Armor M1"]}'),
    (3, 'FTL Communications', 'computing', 2, true, 100, '[]', '{"buildings":["Ansible Array"]}'),
    (3, 'Point Defense Grid', 'defense', 2, true, 80, '[]', '{"weapons":["PD-1 Swatter"]}'),
    (3, 'Advanced Propulsion', 'propulsion', 3, true, 65, '[]', '{"modules":["Fusion Torch M2"]}'),
    (3, 'Durasteel Metallurgy', 'materials', 3, true, 50, '[]', '{"recipes":["Durasteel Forging"]}'),
    (3, 'Quantum Computing', 'computing', 4, false, 20, '[]', '{"modules":["Targeting Computer"]}'),
    (3, 'Vein Navigation Theory', 'vein_science', 4, false, 15, '[]', '{"ship_classes":["Vein Navigator"]}'),
    (3, 'Ghost Signal Cryptography', 'xenotechnology', 5, false, 5, '[]', '{"buildings":["Ghost Signal Decryptor"]}'),
    (3, 'Anti-Cloak Sensor Grid', 'defense', 4, false, 35, '[]', '{"modules":["Ghost Signal Array"]}'),
    (3, 'Eden-class Bioengineering', 'bioengineering', 5, false, 30, '[]', '{"ship_classes":["Eden-class"]}'),
    (3, 'Bisik Subsurface Analysis', 'xenogeology', 4, false, 60, '[]', '{"buildings":["Bisik Research Station"]}'),
    (3, 'Dream State Theory', 'psychic', 6, false, 0, '[]', '{"abilities":["Dream-State Link"]}'),
    (3, 'Pool Biotechnology', 'biomedical', 5, false, 25, '[]', '{"modules":["Pool Healing Bay"]}'),
    (3, 'Swarm Countermeasures', 'military_tactics', 5, false, 40, '[]', '{"weapons":["Bug War Missile"]}'),
    (3, 'Reconstruction Bond Finance', 'economics', 3, true, 100, '[]', '{"buildings":["Bond Market"]}'),
    (3, 'Vein Network Cartography', 'vein_science', 3, true, 80, '[]', '{"abilities":["Sector Mapping"]}'),
    (3, 'Heaven AI Coordination', 'artificial_intelligence', 5, false, 50, '[]', '{"buildings":["Heaven Command Node"]}'),
    (3, 'The Silent Choir Linguistics', 'xenology', 6, false, 0, '[]', '{"abilities":["Choir Translation"]}')
ON CONFLICT DO NOTHING;

-- Weapons blueprints
INSERT INTO maya_rp.weapon_blueprints (name, category, base_damage, base_range, slot_size, tier_required, credit_cost, research_cost) VALUES
    ('PD-3 Beehive Blueprint', 'Point Defense', 12, 1200, 'L', 5, 15000, 5000),
    ('Bug War Missile Blueprint', 'Missile', 40, 7000, 'M', 4, 25000, 8000),
    ('Ghost Signal Decryptor Array', 'Special', 0, 0, 'H', 5, 50000, 20000)
ON CONFLICT DO NOTHING;

-- Stealth unit types (spy planes)
INSERT INTO maya_rp.stealth_unit_types (name, base_cost_alloys, cloak_level, max_lanes, abilities) VALUES
    ('Bisik Recon Drone', 2000, 70, 2, '{"scan":"deep","hack":false,"anomaly":true}'),
    ('Pool Observation Probe', 1500, 55, 3, '{"scan":"biological","hack":false}')
ON CONFLICT DO NOTHING;

SELECT 'artifacts: ' || COUNT(*) FROM maya_rp.artifacts WHERE session_id=3;
SELECT 'production_lines: ' || COUNT(*) FROM maya_rp.production_lines;
SELECT 'technologies: ' || COUNT(*) FROM maya_rp.technologies WHERE session_id=3;
SELECT 'weapon_blueprints: ' || COUNT(*) FROM maya_rp.weapon_blueprints;
SELECT 'stealth_types: ' || COUNT(*) FROM maya_rp.stealth_unit_types;
