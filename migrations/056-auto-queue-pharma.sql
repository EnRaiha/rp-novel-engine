-- 056: Auto-Queue for shipyards + Setia Pharma government corporation
-- King's directive (Day 19): "Heaven Yard should have auto queue, since when it stop..."
-- + medical supplies shortage fix via government pharmaceutical corporation.

-- ── 1. Auto-queue standing orders ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maya_rp.auto_queue (
    id               SERIAL PRIMARY KEY,
    session_id       INT NOT NULL,
    yard             TEXT NOT NULL DEFAULT 'Heaven',
    ship_type        TEXT NOT NULL,
    hull_class       TEXT NOT NULL DEFAULT 'support',
    quota            INT NOT NULL DEFAULT 1,
    ship_name_prefix TEXT NOT NULL,
    alloy_cost       BIGINT NOT NULL DEFAULT 0,
    fuel_cost        BIGINT NOT NULL DEFAULT 0,
    credit_cost      BIGINT NOT NULL DEFAULT 0,
    build_time_hours INT NOT NULL DEFAULT 24,
    priority         INT NOT NULL DEFAULT 1,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Heaven Yard standing orders — the forge never sleeps.
INSERT INTO maya_rp.auto_queue
    (session_id, yard, ship_type, hull_class, quota, ship_name_prefix,
     alloy_cost, fuel_cost, credit_cost, build_time_hours, priority)
VALUES
    (3, 'Heaven', 'frigate',         'escort',  2, 'SE Sentry-',
     350000, 250000,  450000, 24, 2),
    (3, 'Heaven', 'medium_cruiser',  'cruiser', 1, 'SE Watchman-',
     900000, 700000, 1200000, 48, 2),
    (3, 'Heaven', 'heavy_cruiser',   'cruiser', 1, 'SE Warden-',
     1400000, 1100000, 2000000, 72, 2),
    (3, 'Heaven', 'science_vessel',  'support', 1, 'SE Surveyor-',
     350000, 250000,  500000, 48, 2),
    (3, 'Heaven', 'support',         'support', 1, 'SE Aux-',
     300000, 200000,  400000, 36, 3);

-- ── 2. Setia Pharma — government pharmaceutical corporation ──────────────
INSERT INTO maya_rp.corporations (name, faction_id, industry, treasury, profit_margin)
VALUES ('Setia Pharma', 1, 'pharmaceutical', 25000000, 0.12);

INSERT INTO maya_rp.corporate_assets (corporation_id, asset_type, location_id, value, income_per_day, status)
SELECT id, 'pharma_plant', 12, 20000000, 15000, 'active'
FROM maya_rp.corporations WHERE name = 'Setia Pharma';

INSERT INTO maya_rp.corporate_assets (corporation_id, asset_type, location_id, value, income_per_day, status)
SELECT id, 'medical_distribution_hub', 5, 8000000, 10000, 'active'
FROM maya_rp.corporations WHERE name = 'Setia Pharma';

-- Pharma production recipe: Med Pack + Power Cell → Medical Supplies (commodity)
INSERT INTO maya_rp.recipes (name, category, inputs, outputs, cycle_time_hours, tech_requirement)
VALUES ('Pharma Production', 'pharmaceutical',
        '{"Med Pack": 2, "Power Cell": 1}',
        '{"Medical Supplies": 10}', 1, '')
ON CONFLICT (name) DO NOTHING;

-- Setia Pharma line at Pelabuhan Prime
INSERT INTO maya_rp.production_lines (colony_id, name, recipe_id, status, efficiency)
SELECT 1, 'Setia Pharma Line 1', id, 'running', 1.0
FROM maya_rp.recipes WHERE name = 'Pharma Production';

-- ── 3. Seed material stockpiles — unblock the starved supply chain ───────
INSERT INTO maya_rp.material_stockpiles (session_id, colony_id, material_name, quantity)
VALUES
    (3, 1, 'Raw Ore',      5000),
    (3, 1, 'Power Cell',   2000),
    (3, 1, 'Carbon',       3000),
    (3, 1, 'Hydrogen',     5000),
    (3, 1, 'Catalyst',     1500),
    (3, 1, 'Antiseptic',   1000),
    (3, 1, 'Biopolymer',   2000),
    (3, 1, 'Durasteel',    2500),
    (3, 1, 'Alloy Ingot',  3000);

-- Unblock all Pelabuhan lines (Alloy, Medical Bay, Ship Hull) — raw flow restored.
UPDATE maya_rp.production_lines SET status = 'running'
WHERE colony_id = 1 AND status IN ('blocked', 'idle');

-- Market baseline: shortage stands until production catches up.
UPDATE maya_rp.commodities
SET supply = 300000, demand = 350000
WHERE session_id = 3 AND name = 'Medical Supplies';
