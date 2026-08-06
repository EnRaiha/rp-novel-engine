-- 085-character-profile-enrichment.sql
-- Character schema: background + appearance (galaxy beauty standard) + description (profile)
-- Runs as owner: maya

-- Background — backstory penuh
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS background TEXT;

-- Appearance — physical description, GALAXY BEAUTY STANDARD (human standard)
-- Policy: hanya yang mencapai standard kecantikan galaksi disimpan dalam catalog;
-- yang terlalu ugly/monster dikeluarkan (filter GM).
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS appearance TEXT;

-- Description — profile lengkap (personality, manner, relationship)
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS description TEXT;

-- Beauty standard flag — 1 = galaxy beauty (layak catalog), 0 = tidak (tersembunyi/dibuang)
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS beauty_standard BOOLEAN DEFAULT false;
