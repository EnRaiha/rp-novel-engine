-- 054-character-profiles.sql
-- Structured Character Profile System — JSONB columns for appearance, wardrobe, outfit, inventory
-- Auto-dresses characters based on Pacing Director mode
-- ============================================================

-- 1a. Physical Appearance & Voice (Static, set once)
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS profile_jsonb JSONB DEFAULT '{}';

-- 1b. Wardrobe Closet (Array of available outfits with tags for auto-dress)
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS wardrobe_jsonb JSONB DEFAULT '[]';

-- 1c. What they are wearing RIGHT NOW
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS current_outfit JSONB DEFAULT '{}';

-- 1d. What they are carrying (with slot: held/holstered/worn/visible)
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS inventory_jsonb JSONB DEFAULT '[]';
