-- 087-human-likeness-degree.sql
-- Human Standard Compat — DEGREE system + MODIFICATION
-- Rule: species layak kalau human_like_pct >= 80 DAN compatible_anatomy = true
--       (80% wajah & badan seperti manusia, anatomi masih manusia)
--       Modifikasi per-character boleh naikkan degree (e.g., zerg di-humanize)
-- Runs as owner: maya

-- Degree of human-likeness (0-100): % wajah & badan yang menyerupai manusia
ALTER TABLE maya_rp.species_catalog ADD COLUMN IF NOT EXISTS human_like_pct INT DEFAULT 0;

-- Per-character modification: character yang dimodifikasi (di-humanize) boleh lulus
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS modified BOOLEAN DEFAULT false;

-- Index
CREATE INDEX IF NOT EXISTS idx_species_humanlike ON maya_rp.species_catalog(human_like_pct);
