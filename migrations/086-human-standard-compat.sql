-- 086-human-standard-compat.sql
-- Human Standard Compatibility Check — galaxy beauty filter
-- Setiap species kena lulus SEMUA check sebelum layak romance/intimacy:
--   ☑ Boob check (ada payudara)
--   ☑ Soft body check (lembut, bukan keras/kristal)
--   ☑ Transform check (boleh jadi bentuk badan manusia)
--   ☑ Booty check (ada punggung)
--   ☑ Anatomy check (badan lembut & anjal, anatomi manusia — compatible)
--   ☑ Elemental check: element/spirit/kristal = NO (tak compatible)
-- Runs as owner: maya

ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS has_breasts BOOLEAN DEFAULT false;
ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS soft_body BOOLEAN DEFAULT false;
ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS can_transform_human BOOLEAN DEFAULT false;
ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS has_buttocks BOOLEAN DEFAULT false;
ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS compatible_anatomy BOOLEAN DEFAULT false;
ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS romance_compatible BOOLEAN DEFAULT false;
ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS compat_notes TEXT DEFAULT '';

-- Index untuk filter cepat
CREATE INDEX IF NOT EXISTS idx_species_romance ON maya_rp.species_catalog(romance_compatible);
