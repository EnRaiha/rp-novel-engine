-- MIGRATION: SYSTEM-ID NORMALIZATION — point units at territory_id (FK), not name strings.
-- Units (ships, characters, campaigns, raids, grids) reference territory by FK.
-- System rename/move = update territory ONLY; units stay valid.
-- Pattern: unit → territory_id → (name, coords, faction) — single source of truth.

-- 1. SHIPS
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS territory_id INT;
ALTER TABLE maya_rp.ships
    ADD CONSTRAINT fk_ships_territory FOREIGN KEY (territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 2. CHARACTERS
ALTER TABLE maya_rp.characters ADD COLUMN IF NOT EXISTS scene_territory_id INT;
ALTER TABLE maya_rp.characters
    ADD CONSTRAINT fk_characters_scene_territory FOREIGN KEY (scene_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 3. CAMPAIGNS
ALTER TABLE maya_rp.campaigns ADD COLUMN IF NOT EXISTS target_territory_id INT;
ALTER TABLE maya_rp.campaigns
    ADD CONSTRAINT fk_campaigns_target_territory FOREIGN KEY (target_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 4. INCOMING RAIDS
ALTER TABLE maya_rp.incoming_raids ADD COLUMN IF NOT EXISTS target_territory_id INT;
ALTER TABLE maya_rp.incoming_raids
    ADD CONSTRAINT fk_incoming_raids_target_territory FOREIGN KEY (target_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 5. ANTI CLOAK GRIDS
ALTER TABLE maya_rp.anti_cloak_grids ADD COLUMN IF NOT EXISTS territory_id INT;
ALTER TABLE maya_rp.anti_cloak_grids
    ADD CONSTRAINT fk_anti_cloak_grids_territory FOREIGN KEY (territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;
