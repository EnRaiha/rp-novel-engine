-- MIGRATION 069: FK normalization — remaining string-based system refs.
-- Adds territory_id FKs + backfills from name strings.
-- Pattern: unit → territory_id → (name, coords) — single source of truth.

-- 1. PLANETS: system_name -> territory_id
ALTER TABLE maya_rp.planets ADD COLUMN IF NOT EXISTS territory_id INT;
ALTER TABLE maya_rp.planets
    ADD CONSTRAINT fk_planets_territory FOREIGN KEY (territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 2. GOVERNOR APPLICANTS: home_system/assigned_system -> FKs
ALTER TABLE maya_rp.governor_applicants ADD COLUMN IF NOT EXISTS home_territory_id INT;
ALTER TABLE maya_rp.governor_applicants
    ADD CONSTRAINT fk_governor_applicants_home FOREIGN KEY (home_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;
ALTER TABLE maya_rp.governor_applicants ADD COLUMN IF NOT EXISTS assigned_territory_id INT;
ALTER TABLE maya_rp.governor_applicants
    ADD CONSTRAINT fk_governor_applicants_assigned FOREIGN KEY (assigned_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 3. YARD CAPACITY: location -> territory_id
ALTER TABLE maya_rp.yard_capacity ADD COLUMN IF NOT EXISTS territory_id INT;
ALTER TABLE maya_rp.yard_capacity
    ADD CONSTRAINT fk_yard_capacity_territory FOREIGN KEY (territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 4. CORPORATE CONTRACTS: target_system -> territory_id
ALTER TABLE maya_rp.corporate_contracts ADD COLUMN IF NOT EXISTS target_territory_id INT;
ALTER TABLE maya_rp.corporate_contracts
    ADD CONSTRAINT fk_corporate_contracts_target FOREIGN KEY (target_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;

-- 5. Empty-but-string tables (add FK for future use): defense_installations,
--    horror_events, sieges, artifact_history
ALTER TABLE maya_rp.defense_installations ADD COLUMN IF NOT EXISTS territory_id INT;
ALTER TABLE maya_rp.defense_installations
    ADD CONSTRAINT fk_defense_installations_territory FOREIGN KEY (territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;
ALTER TABLE maya_rp.horror_events ADD COLUMN IF NOT EXISTS territory_id INT;
ALTER TABLE maya_rp.horror_events
    ADD CONSTRAINT fk_horror_events_territory FOREIGN KEY (territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;
ALTER TABLE maya_rp.sieges ADD COLUMN IF NOT EXISTS target_territory_id INT;
ALTER TABLE maya_rp.sieges
    ADD CONSTRAINT fk_sieges_target_territory FOREIGN KEY (target_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;
ALTER TABLE maya_rp.artifact_history ADD COLUMN IF NOT EXISTS from_territory_id INT;
ALTER TABLE maya_rp.artifact_history ADD COLUMN IF NOT EXISTS to_territory_id INT;
ALTER TABLE maya_rp.artifact_history
    ADD CONSTRAINT fk_artifact_history_from FOREIGN KEY (from_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;
ALTER TABLE maya_rp.artifact_history
    ADD CONSTRAINT fk_artifact_history_to FOREIGN KEY (to_territory_id)
    REFERENCES maya_rp.territory(id) ON DELETE SET NULL;
