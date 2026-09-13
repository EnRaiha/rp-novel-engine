-- 093-eden-register.sql — Register the 30 existing EDEN-class ships (canon: Class 4, Tier 5).
-- 24 with the Kingdom at Mastika; 6 assigned to the sponsored wolves (1 per faction).
-- EDEN = hydroponic ring, 30K hull, feeds a fleet. Space-greenhouse (climate decks, living soil).

-- Class: EDEN (Class 4, Tier 5 support)
INSERT INTO maya_rp.ship_classes
    (id, class_name, category, base_mass, base_length, base_crew, base_hull, base_speed,
     module_slots, weapon_slots, scale_factor, special_rules)
VALUES
    (19, 'EDEN', 'support', 80000, 600, 80, 30000, 8,
     10, '0', 1.15, '["hydroponic","greenhouse","food"]')
ON CONFLICT (id) DO NOTHING;

-- 30 ships: EDEN-01..24 at Mastika (kingdom), EDEN-25..30 with the wolves
DO $$
DECLARE
  i INT;
  wid INT := 1664;  -- ship id start
BEGIN
  FOR i IN 1..24 LOOP
    INSERT INTO maya_rp.ships
        (id, session_id, name, class_id, ship_type, mass, length_m, hull, hull_current,
         speed, crew, fighter_capacity, location, status, tier, veteran_kills, rank,
         experience, cell_capacity, security_tier, is_colony_ship, colonists, weapon_slots,
         shield_generators, engine_type, combat_modules, role, power_rating, sub_class,
         battle_honors, legacy_score, crew_current, crew_required, undercrewed_penalty,
         scars_jsonb, ship_rank, min_clearance)
    VALUES
        (wid, 3, 'EDEN-' || LPAD(i::text, 2, '0'), 19, 'eden_class', 80000, 600,
         30000, 30000, 8, 80, 0,
         'Mastika — parked, food production active', 'active', 5, 0, 'Deployed',
         0, 0, 0, FALSE, 0, 0, 2, 'EDEN-Hydro', '[]'::jsonb, 'support',
         5000, 'Space-Greenhouse', 0, 0, 80, 0, 0, '[]'::jsonb, 'Deployed', 3);
    wid := wid + 1;
  END LOOP;
  -- Wolves' EDEN (6)
  FOR i IN 25..30 LOOP
    INSERT INTO maya_rp.ships
        (id, session_id, name, class_id, ship_type, mass, length_m, hull, hull_current,
         speed, crew, fighter_capacity, location, status, tier, veteran_kills, rank,
         experience, cell_capacity, security_tier, is_colony_ship, colonists, weapon_slots,
         shield_generators, engine_type, combat_modules, role, power_rating, sub_class,
         battle_honors, legacy_score, crew_current, crew_required, undercrewed_penalty,
         scars_jsonb, ship_rank, min_clearance)
    VALUES
        (wid, 3, 'EDEN-' || LPAD(i::text, 2, '0'), 19, 'eden_class', 80000, 600,
         30000, 30000, 8, 80, 0,
         'Wolves territory — sponsored food security (deniable asset)', 'active', 5, 0, 'Deployed',
         0, 0, 0, FALSE, 0, 0, 2, 'EDEN-Hydro', '[]'::jsonb, 'support',
         5000, 'Space-Greenhouse', 0, 0, 80, 0, 0, '[]'::jsonb, 'Deployed', 3);
    wid := wid + 1;
  END LOOP;
END $$;

-- Event
INSERT INTO maya_rp.events (session_id, event_type, title, description, happened_at)
VALUES (3, 'register',
        '🌾 30 EDEN REGISTERED — 24 KINGDOM + 6 WOLVES (Day 1383)',
        'Existing EDEN fleet registered in engine: 30 hulls (Class 4, Tier 5, hydroponic ring, 30K hull, space-greenhouse). EDEN-01..24 at Mastika (kingdom food production); EDEN-25..30 with the sponsored wolves (deniable food security). Keep 30 count (no 40). New 200-ship tiered program (T6x100/T7x60/T8x40) remains queued. Fairy Courts contact approved for advanced seedlings + genetic R&D.',
        now());