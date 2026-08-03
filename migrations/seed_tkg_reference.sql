-- ═══════════════════════════════════════════════════════════════════
-- TKG REFERENCE DATA SEED
-- Sources: TKG setting-bible.md, book-05-the-bug-war.md, progression.md
-- ═══════════════════════════════════════════════════════════════════

BEGIN;
SET search_path TO maya_rp;

-- ═══════════════════════════════════════════════════════════════════
-- 1. WEAPONS — expanded from Book 05 Bug War + TKG fleet
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.weapons (name, kind, slot_size, damage, range_m, tier_min, tier_max, special_rules) VALUES
    -- Point Defense
    ('PD-1 Swatter',     'Point Defense', 'L',   5,  500,  1, 3, '{"anti_fighter":2,"anti_missile":1}'),
    ('PD-2 Interceptor', 'Point Defense', 'L',   8,  800,  3, 5, '{"anti_fighter":3,"anti_missile":2}'),
    ('PD-3 Beehive',     'Point Defense', 'L',  12, 1200,  5, 8, '{"anti_fighter":4,"anti_missile":3}'),
    -- Ballistic
    ('Mk1 Autocannon',   'Ballistic',     'M',  15, 2000,  1, 3, '{"type":"kinetic"}'),
    ('Mk2 Railgun',      'Ballistic',     'M',  30, 3500,  3, 5, '{"type":"kinetic","armor_penalty":10}'),
    ('Mk3 Gauss Rifle',  'Ballistic',     'H',  50, 5000,  5, 8, '{"type":"kinetic","armor_penalty":20}'),
    -- Beam
    ('Pulse Laser',      'Beam',          'L',  10, 3000,  1, 3, '{"type":"energy","accuracy_bonus":5}'),
    ('Medium Beam',      'Beam',          'M',  25, 4500,  3, 5, '{"type":"energy","accuracy_bonus":5}'),
    ('Heavy Beam',       'Beam',          'H',  45, 6000,  5, 8, '{"type":"energy","accuracy_bonus":5}'),
    -- Torpedo
    ('Mk1 Torpedo',      'Torpedo',       'M',  60, 8000,  1, 3, '{"type":"explosive","reload_penalty":-10}'),
    ('Mk2 Torpedo',      'Torpedo',       'H', 100,10000,  3, 5, '{"type":"explosive","reload_penalty":-15}'),
    ('Bug War Missile',  'Missile',       'M',  40, 7000,  4, 6, '{"type":"explosive","tracking":true,"note":"200 tubes used in Gate Operation"}'),
    -- Cannon (spinal mounts)
    ('Heavy Spinal Cannon', 'Cannon',     'SH', 200,15000,  5, 8, '{"type":"kinetic","fixed_arc":true,"armor_penalty":30}')
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 2. MODULES — TKG ship systems
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.modules (name, category, effect_type, effect_value, grade, tier_min, tier_max, cost_alloys, cost_credits, special_rules) VALUES
    -- Engines
    ('Fusion Torch M1',      'engine',     'speed',      10,  1,  1, 5, 200,  100,  '{}'),
    ('Fusion Torch M2',      'engine',     'speed',      20,  3,  3, 5, 500,  300,  '{}'),
    ('Ion Drive M3',         'engine',     'speed',      35,  5,  5, 8, 1200, 800,  '{}'),
    ('Vein Tap Drive',       'engine',     'speed',      50,  8,  7, 8, 3000, 2000, '{"special":"vein_harmony"}'),
    -- Shields
    ('Deflector Screen M1',  'shield',     'hull_boost', 15,  1,  1, 5, 300,  200,  '{}'),
    ('Deflector Screen M2',  'shield',     'hull_boost', 30,  3,  3, 5, 700,  500,  '{}'),
    ('Quantum Barrier',      'shield',     'hull_boost', 50,  5,  5, 8, 2000, 1500, '{"special":"phase_resist"}'),
    -- Sensors
    ('Long Range Scanner',   'sensor',     'detection',  15,  2,  2, 6, 400,  300,  '{}'),
    ('Ghost Signal Array',   'sensor',     'detection',  40,  7,  7, 8, 5000, 3000, '{"special":"precursor_trace"}'),
    -- Armor
    ('Composite Armor M1',   'armor',      'hull',       20,  1,  1, 5, 250,  150,  '{}'),
    ('Durasteel Plating',    'armor',      'hull',       40,  3,  3, 6, 800,  400,  '{}'),
    ('Reactive Armor',       'armor',      'hull',       60,  5,  6, 8, 2500, 1500, '{"special":"explosive_resist"}'),
    -- Weapons Support
    ('Auto-Loader M1',       'support',    'rof',        15,  2,  2, 4, 300,  200,  '{}'),
    ('Targeting Computer',   'support',    'accuracy',   20,  3,  3, 6, 600,  400,  '{}'),
    ('EW Package',           'support',    'jamming',    25,  4,  5, 7, 2000, 1000, '{}'),
    -- Special
    ('Eden-class Fabricator','special',    'production', 30,  6,  5, 8, 8000, 5000, '{"special":"colony_ship","note":"Eden class food production"}'),
    ('Pool Healing Bay',     'special',    'crew_regen', 20,  5,  5, 7, 4000, 3000, '{"special":"healing","note":"Treats 296 casualties"}')
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 3. STEALTH UNIT TYPES — spy planes from narrative
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.stealth_unit_types (name, base_cost_alloys, cloak_level, max_lanes, abilities) VALUES
    ('Ghost Eye Probe',    1500,  60, 3, '{"scan":"stealth","hack":false}'),
    ('Shadow Runner',      2500,  75, 2, '{"scan":"stealth","hack":true}'),
    ('Void Spectre',       5000,  90, 1, '{"scan":"stealth","hack":true,"intercept":true}'),
    ('Signal Drone',       800,   30, 5, '{"scan":"passive","relay":true}')
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 4. ALCHEMY RECIPES — from TKG universe materials
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.alchemy_recipes (name, category, inputs, outputs, catalyst, success_rate, tech_tier, lore_text) VALUES
    ('Vein Essence Distillation', 'refinement', '{"Void Crystal":3,"Vein Dust":5}', '{"Vein Essence":2}', 'Harmonic Resonator', 0.65, 3, 'The Vein leaves traces. Distill them to see the network''s true shape.'),
    ('Ghost Echo Binding',        'infusion',   '{"Ghost Echo":2,"Alloy Ingot":10}', '{"Bound Echo Alloy":5}', 'Precursor Key', 0.40, 5, 'Ghost Signal fragments can be bound into alloys that hum with intent.'),
    ('Dream Essence Extraction',  'extraction', '{"Dream Crystal":5,"Stabilizer":2}', '{"Dream Essence":3}', 'Nullifier', 0.70, 4, 'Extract the essence of dreams from crystallized psychic residue.'),
    ('Pool Water Purification',   'refinement', '{"Contaminated Water":10,"Catalyst":1}', '{"Pure Water":10,"Pool Salts":1}', 'None', 0.95, 2, 'The Pool''s waters can be purified and used for healing baths.'),
    ('Bisik Whisper Translation', 'mystic',    '{"Bisik Fragment":3,"Vein Essence":1}', '{"Translated Text":1,"Sector Data":2}', 'Oracle Matrix', 0.25, 7, 'The whispers from Bisik carry meaning. Translate them at great risk.'),
    ('Eden-class Growth Medium',  'production', '{"Biopolymer":10,"Nutrient Base":20,"Pure Water":5}', '{"Eden Growth Medium":15}', 'Fabricator Mold', 0.80, 6, 'The Eden class requires a custom growth medium. Each batch feeds millions.')
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 5. TRAINING PROGRAMS — from TKG fleet officer roles
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.training_programs (name, field, duration, skill_bonus, graduates_receive) VALUES
    ('Tactical Command',      'military_science', 120,  10, 'Field Commission - Lieutenant'),
    ('Fleet Navigation',      'navigation',       100,   8, 'Navigation Certification - Silver'),
    ('Engineering Core',      'engineering',      140,  12, 'Chief Engineer Certification'),
    ('Point Defense Ops',     'combat_systems',    80,   6, 'PD Operator Certification'),
    ('Medical Triage',        'medicine',         100,   8, 'Field Medic Certification'),
    ('Science Survey',        'xenobiology',      110,   9, 'Science Officer Commission'),
    ('Vein Navigation',       'vein_navigation',  160,  15, 'Vein Pilot Certification'),
    ('Intelligence Analysis', 'intel',            130,  11, 'Analyst Certification - Gold'),
    ('Crisis Management',     'leadership',        90,   7, 'Crisis Command Certification'),
    ('Diplomatic Corps',      'diplomacy',         90,   7, 'Envoy Certification'),
    ('Stealth Operations',    'covert_ops',       150,  14, 'Shadow Agent Certification'),
    ('Medical: Advanced',     'medicine',         180,  16, 'Chief Medical Officer Certification')
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 6. ACADEMY CAMPUSES — TKG fleet academies
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.academy_campuses (name, max_students, prestige, level) VALUES
    ('Karunia Fleet Academy', 200, 100, 3),
    ('Pelabuhan Naval School', 100, 50, 2),
    ('Stasiun TKG Command College', 150, 80, 3),
    ('Heaven AI Tactical Institute', 300, 200, 5)
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 7. UNIVERSITY CAMPUSES — research division
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.university_campuses (name, research_rate, level, prestige) VALUES
    ('Chen Institute of Sciences', 1.5, 4, 120),
    ('Bisik Anomaly Research Station', 2.0, 3, 90),
    ('Vein Network Observatory', 2.5, 5, 160),
    ('Ghost Signal Analysis Center', 3.0, 4, 140)
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 8. RECIPES — manufacturing
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.recipes (name, category, inputs, outputs, cycle_time_hours, tech_requirement) VALUES
    ('Alloy Ingot Smelting',  'refinement', '{"Raw Ore":5,"Power Cell":1}',   '{"Alloy Ingot":3}',   1, NULL),
    ('Durasteel Forging',    'refinement', '{"Alloy Ingot":3,"Carbon":1}',   '{"Durasteel":2}',     2, NULL),
    ('Refined Fuel',        'fuel',       '{"Hydrogen":5,"Catalyst":1}',     '{"Refined Fuel":5}',  1, NULL),
    ('Ship Hull Plate',     'construction','{"Durasteel":3,"Alloy Ingot":2}','{"Hull Plate":1}',    2, NULL),
    ('Sensor Array Kit',    'electronics', '{"Electronics":2,"Circuit":3}',  '{"Sensor Array":1}',  3, NULL),
    ('Medical Supply Pack',  'medical',    '{"Biopolymer":2,"Antiseptic":1}','{"Med Pack":5}',      1, NULL),
    ('Eden Growth Medium',  'special',     '{"Biopolymer":10,"Nutrient Base":20,"Pure Water":5}', '{"Eden Medium":15}', 5, NULL),
    ('Dream Crystal Synthesis','exotic',   '{"Void Crystal":2,"Stabilizer":1,"Energy":5}', '{"Dream Crystal":1}', 4, NULL)
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 9. RESEARCH PROJECTS — ongoing TKG research
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.research_projects (title, field, description, progress, target_progress, breakthrough_chance, campus_id) VALUES
    ('Vein Network Mapping', 'astrophysics', 'Map all active Vein Nodes within 200LY', 45, 100, 0.08, 1),
    ('Ghost Signal Decryption', 'xenotechnology', 'Decode the repeating signal from the core', 20, 200, 0.03, 4),
    ('Bisik Subsurface Survey', 'xenogeology', 'Map the subsurface structure of Bisik', 60, 100, 0.10, 2),
    ('Eden-class Optimization', 'bioengineering', 'Improve Eden-class growth medium efficiency', 30, 80, 0.12, 1),
    ('Dream State Mechanics', 'psychic_phenomena', 'Understand the mechanics of dream-state linking', 15, 150, 0.05, 3),
    ('Pool Healing Enhancement', 'biomedical', 'Increase Pool healing throughput and capacity', 50, 120, 0.07, 1),
    ('Anti-Cloak Detection II', 'defense_tech', 'Improve Ghost-class anti-cloak grid detection', 70, 100, 0.15, 3),
    ('Reconstruction Bond Modeling', 'economics', 'Model optimal bond repayment structures', 25, 60, 0.10, 1)
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 10. DISASTER TEMPLATES — cosmic and faction threats
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO maya_rp.disaster_templates (name, category, base_damage, severity_min, severity_max, duration_min, duration_max, trigger_conditions) VALUES
    ('Vein Collapse Event',  'cosmic',  500,  3,  8,  3,  7,  '{"node_proximity":"active"}'),
    ('Ghost Signal Surge',   'anomaly', 300,  2,  6,  2,  5,  '{"faction":"ghost_signal"}'),
    ('Pirate Raid',          'pirate',  200,  1,  5,  1,  3,  '{"territory":"unprotected"}'),
    ('Economic Recession',   'economic',150,  2,  6,  4,  8,  '{"credits":"low","morale":"declining"}'),
    ('Void Plague',          'plague',  400,  4,  9,  5,  10, '{"population":"dense","quarantine":"fail"}'),
    ('Swarm Incursion',      'cosmic',  800,  6,  10, 4,  8,  '{"bug_gate":"open"}'),
    ('Solar Storm',          'natural', 100,  1,  4,  1,  3,  '{"star_type":"active"}'),
    ('Cult Awakening',       'anomaly', 250,  3,  7,  3,  6,  '{"silent_choir":"active"}')
ON CONFLICT DO NOTHING;

COMMIT;

-- ═══════════════════════════════════════════════════════════════════
-- VERIFICATION
-- ═══════════════════════════════════════════════════════════════════
SELECT 'Weapons:' || COUNT(*) FROM maya_rp.weapons
UNION ALL SELECT 'Modules:' || COUNT(*) FROM maya_rp.modules
UNION ALL SELECT 'Stealth types:' || COUNT(*) FROM maya_rp.stealth_unit_types
UNION ALL SELECT 'Alchemy recipes:' || COUNT(*) FROM maya_rp.alchemy_recipes
UNION ALL SELECT 'Training programs:' || COUNT(*) FROM maya_rp.training_programs
UNION ALL SELECT 'Academy campuses:' || COUNT(*) FROM maya_rp.academy_campuses
UNION ALL SELECT 'University campuses:' || COUNT(*) FROM maya_rp.university_campuses
UNION ALL SELECT 'Recipes:' || COUNT(*) FROM maya_rp.recipes
UNION ALL SELECT 'Research projects:' || COUNT(*) FROM maya_rp.research_projects
UNION ALL SELECT 'Disaster templates:' || COUNT(*) FROM maya_rp.disaster_templates;
