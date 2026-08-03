-- 059: Materials catalog seed — real-world + fantasy (TKG) materials.
-- The `materials` table was EMPTY (audit 31 Jul): recipes reference names
-- with no definitions. This seeds definitions for every name used by
-- stockpiles, recipes, and manufacturing — plus lore materials for later tiers.

INSERT INTO maya_rp.materials (name, category, base_value, tech_tier) VALUES
-- ── REAL-WORLD: raw ────────────────────────────────────────────────
('Raw Ore',        'raw',       1.0,  1),
('Iron Ore',       'raw',       0.8,  1),
('Copper',         'raw',       1.2,  1),
('Silicon',        'raw',       0.9,  1),
('Carbon',         'raw',       0.6,  1),
('Hydrogen',       'raw',       0.4,  1),
('Water Ice',      'raw',       0.5,  1),
('Titanium Ore',   'raw',       2.5,  2),
('Aluminum Ore',   'raw',       1.1,  1),
('Gold',           'raw',       8.0,  2),
('Platinum',       'raw',      12.0,  3),
('Rare Earth',     'raw',       6.0,  2),
-- ── REAL-WORLD: processed ──────────────────────────────────────────
('Alloy Ingot',    'processed', 3.5,  2),
('Refined Fuel',   'processed', 2.3,  2),
('Durasteel',      'processed', 5.0,  3),
('Hull Plate',     'processed', 6.5,  3),
('Power Cell',     'processed', 4.0,  2),
('Circuit',        'processed', 7.0,  2),
('Electronics',    'processed', 8.5,  3),
('Sensor Array',   'processed', 9.0,  3),
('Catalyst',       'processed', 5.5,  2),
('Glass',          'processed', 1.5,  1),
('Ceramic',        'processed', 2.0,  2),
('Polymer',        'processed', 2.8,  2),
('Graphene Sheet', 'processed', 15.0, 4),
('Cold Fusion Core','processed', 60.0, 4),
-- ── REAL-WORLD: medical ────────────────────────────────────────────
('Antiseptic',     'medical',   4.5,  2),
('Biopolymer',     'medical',   6.0,  2),
('Med Pack',       'medical',   8.0,  2),
('Medical Supplies','medical', 10.0,  2),
('Gene Serum',     'medical',  40.0,  4),
('Regen Gel',      'medical',  25.0,  3),
-- ── FANTASY / TKG: minerals & exotic ───────────────────────────────
('Vein Crystal',   'fantasy',   25.0,  3),
('Star Iron',      'fantasy',   30.0,  3),
('Moon Silver',    'fantasy',   35.0,  3),
('Blood Amber',    'fantasy',   28.0,  3),
('Ember Coal',     'fantasy',   18.0,  2),
('Starfall Alloy', 'fantasy',   55.0,  4),
('Night Dew',      'fantasy',   22.0,  3),
('Abyss Pearl',    'fantasy',   80.0,  4),
('Phoenix Ash',    'fantasy',   65.0,  4),
('Spectral Bloom', 'fantasy',   45.0,  3),
-- ── ARCANE / POOL-TOUCHED ──────────────────────────────────────────
('Dream Essence',  'arcane',   150.0,  5),
('Pool Water',     'arcane',   120.0,  5),
('Ghost Echo',     'arcane',   200.0,  5),
('Void Silk',      'arcane',   180.0,  5),
('Choir Relic',    'arcane',   500.0,  5),
('Warp Dust',      'arcane',   300.0,  5)
ON CONFLICT (name) DO NOTHING;

-- Engine read access (idempotent).
GRANT SELECT ON maya_rp.materials TO rp_engine;
