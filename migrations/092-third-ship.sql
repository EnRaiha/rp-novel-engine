-- 092-third-ship.sql (fixed) — Register Third Ship + Athena.
-- All columns are INTEGER (max 2,147,483,647) — planet-scale kept within int32.

-- Class: Starforged (worldship) + Portal Ship
INSERT INTO maya_rp.ship_classes
    (id, class_name, category, base_mass, base_length, base_crew, base_hull, base_speed,
     module_slots, weapon_slots, scale_factor, special_rules)
VALUES
    (17, 'Starforged', 'worldship', 2000000000, 15000000, 500000, 2000000000, 5,
     50, '300', 1.0, '["portal","worldship","ai_mastermind"]'),
    (18, 'Portal Ship', 'capital', 2000000000, 20000, 20000, 2000000, 20,
     20, '30', 1.15, '["portal","ai_mastermind","hybrid"]')
ON CONFLICT (id) DO NOTHING;

-- The Third Ship — Starforged-03
INSERT INTO maya_rp.ships
    (id, session_id, name, class_id, ship_type, mass, length_m, hull, hull_current,
     speed, crew, fighter_capacity, location, status, tier, veteran_kills, rank,
     experience, cell_capacity, security_tier, is_colony_ship, colonists, weapon_slots,
     shield_generators, engine_type, combat_modules, role, power_rating, sub_class,
     battle_honors, legacy_score, crew_current, crew_required, undercrewed_penalty,
     scars_jsonb, ship_rank, min_clearance, territory_id, faction_id)
VALUES
    (1662, 3, 'Starforged-03 — The Third Ship', 17, 'worldship', 2000000000, 15000000,
     2000000000, 2000000000, 5, 0, 0,
     'The New Place — Main Bay (fleet secured)', 'active', 11, 0, 'Claimed',
     0, 0, 0, 1, false, 0, 300, 100, 'Starforged-Prime', '[]', 'capital',
     2000000000, 'Worldship', 9999,
     0, 500000, 0, '[]', 'Worldship', 5, NULL, NULL);

-- Athena — Class A portal ship
INSERT INTO maya_rp.ships
    (id, session_id, name, class_id, ship_type, mass, length_m, hull, hull_current,
     speed, crew, fighter_capacity, location, status, tier, veteran_kills, rank,
     experience, cell_capacity, security_tier, is_colony_ship, colonists, weapon_slots,
     shield_generators, engine_type, combat_modules, role, power_rating, sub_class,
     battle_honors, legacy_score, crew_current, crew_required, undercrewed_penalty,
     scars_jsonb, ship_rank, min_clearance, territory_id, faction_id)
VALUES
    (1663, 3, 'Athena', 18, 'portal_ship', 2000000000, 20000,
     2000000, 2000000, 20, 0, 0,
     'Third Ship — Docked (new core installed)', 'active', 11, 0, 'General',
     0, 0, 0, 1, false, 0, 30, 50, 'Athena-Hybrid', '[]', 'capital',
     2500000, 'Portal Ship', 9999,
     0, 20000, 0, '[]', 'General', 5, NULL, NULL);

-- Event
INSERT INTO maya_rp.events (session_id, event_type, title, description, happened_at)
VALUES (3, 'register',
        '🐘 THIRD SHIP + ATHENA REGISTERED (Day 1323)',
        'Third Ship (Starforged-03, Class Starforged, T11 worldship, 15,000 km, 2B hull, power 2B) '
        'claimed by the King — deck active, fleet secured in main bay. Athena (Class A portal ship, '
        'T11, 20 km, hybrid AI mastermind) docked with new core installed. Both live in engine ledger.',
        now());