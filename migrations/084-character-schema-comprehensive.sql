-- 084-character-schema-comprehensive.sql
-- Comprehensive Character Schema — full integration seluruh sistem
-- Species (ALL), faction, crew, romance, traits, clearance, beauty catalog
-- Runs as owner: maya

-- 1. SPECIES CATALOG — semua species dalam galaksi (dari novel corpus + engine)
CREATE TABLE IF NOT EXISTS maya_rp.species_catalog (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,               -- human, alien, hybrid, half_beast, succubus, demon, fairy,
                                             -- mechanical, spirit, clone, cyborg, zerg, dwarf, seeder, ghost
    category TEXT DEFAULT 'organic',         -- organic, supernatural, synthetic, hive, spirit
    base_strength INT DEFAULT 5,
    base_intelligence INT DEFAULT 5,
    base_charisma INT DEFAULT 5,
    lifespan_years INT DEFAULT 80,
    crew_role_bonus TEXT DEFAULT '',         -- contoh: 'engineering+2'
    clearance_default INT DEFAULT 1,         -- C1-C4 default; C5+ kena screening
    market_available BOOLEAN DEFAULT true,   -- boleh beli via crew market
    traits_common JSONB DEFAULT '[]',        -- trait biasa species
    notes TEXT DEFAULT ''
);

-- 2. CHARACTERS — unified, integrate semua subsistem
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS species_id INTEGER;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS faction_id INTEGER;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS crew_id INTEGER;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS ship_id INTEGER;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS clearance_level INT DEFAULT 1;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS screened BOOLEAN DEFAULT false;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS beauty_catalog_id INTEGER;  -- link ke galaxy-beauties
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS origin_system TEXT;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS bond_level INT DEFAULT 0;   -- duplikat romance bond
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS dream_essence_affinity NUMERIC DEFAULT 0;
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS last_seen_day INT;

-- 3. CHARACTER-SPECIES LINK (many-to-many untuk hybrid/evolved)
CREATE TABLE IF NOT EXISTS maya_rp.character_species (
    character_id INTEGER REFERENCES maya_rp.characters(id),
    species_id INTEGER REFERENCES maya_rp.species_catalog(id),
    purity_pct INT DEFAULT 100,              -- 100 = pure, <100 = hybrid
    PRIMARY KEY (character_id, species_id)
);

-- 4. TRAITS UNIFIED (semua trait source: species, quirk, scars, training)
CREATE TABLE IF NOT EXISTS maya_rp.character_traits (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES maya_rp.characters(id),
    trait TEXT NOT NULL,
    trait_type TEXT DEFAULT 'innate',        -- innate, species, quirk, scar, trained, medal
    source TEXT DEFAULT '',                  -- species:succubus, scar:gate7, medal:sacrifice
    value NUMERIC DEFAULT 0,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_char_traits ON maya_rp.character_traits(character_id, active);

-- 5. INTEGRATION INDEXES
CREATE INDEX IF NOT EXISTS idx_characters_species ON maya_rp.characters(species_id);
CREATE INDEX IF NOT EXISTS idx_characters_faction ON maya_rp.characters(faction_id);
CREATE INDEX IF NOT EXISTS idx_characters_clearance ON maya_rp.characters(clearance_level, screened);
CREATE INDEX IF NOT EXISTS idx_characters_crew ON maya_rp.characters(crew_id);
