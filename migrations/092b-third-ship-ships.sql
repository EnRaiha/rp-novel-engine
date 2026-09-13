-- 092b-third-ship-ships.sql — register ships with explicit columns.
INSERT INTO maya_rp.ships
    (id, session_id, name, class_id, ship_type, mass, length_m, hull, hull_current,
     speed, crew, fighter_capacity, location, status, tier, veteran_kills, rank,
     experience, cell_capacity, security_tier, is_colony_ship, colonists, weapon_slots,
     shield_generators, engine_type, combat_modules, role, power_rating, sub_class,
     battle_honors, legacy_score, crew_current, crew_required, undercrewed_penalty,
     scars_jsonb, ship_rank, min_clearance)
VALUES
    (1662, 3, 'Starforged-03 — The Third Ship', 17, 'worldship', 2000000000, 15000000,
     2000000000, 2000000000, 5, 0, 0,
     'The New Place — Main Bay (fleet secured)', 'active', 11, 0, 'Claimed',
     0, 0, 0, FALSE, 0, 300, 100, 'Starforged-Prime', '[]'::jsonb, 'capital',
     2000000000, 'Worldship', 9999, 0, 500000, 0, 0, '[]'::jsonb, 'Worldship', 5),
    (1663, 3, 'Athena', 18, 'portal_ship', 2000000000, 20000,
     2000000, 2000000, 20, 0, 0,
     'Third Ship — Docked (new core installed)', 'active', 11, 0, 'General',
     0, 0, 0, FALSE, 0, 30, 50, 'Athena-Hybrid', '[]'::jsonb, 'capital',
     2500000, 'Portal Ship', 9999, 0, 20000, 0, 0, '[]'::jsonb, 'General', 5);