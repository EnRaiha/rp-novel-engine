-- 091: Lower Veil wild frontier + Upper Veil civilization (2026-08-14)
-- King's directive:
--   - BOTTOM (z=1) = uncharted & wild: 5 more pirate packs, ~500 ships each
--     (T3~T5 mix); existing 3 bottom packs upgraded to 500 too.
--   - TOP (z=3) = civilized but not as wide as the middle: denser settled
--     worlds, pirates stay fringe.

-- 1. five new bottom dens (z=1)
INSERT INTO maya_rp.sectors (name, x_coord, y_coord, star_type, controlled_by, hazard_level, z_coord, hidden)
VALUES
  ('Silt Reaver Pit', 200, 480, 'main_sequence', 'Silt Reaver Legion', 0.7, 1, false),
  ('Pressure Cult Deep', 450, 30, 'red_giant', 'Pressure Cult Corsairs', 0.8, 1, false),
  ('Blacktide Rift', 60, 60, 'neutron', 'Blacktide Armada', 0.7, 1, false),
  ('Drowned Fang Hold', 480, 420, 'white_dwarf', 'Drowned Fang Marauders', 0.6, 1, false),
  ('Wrecklight Shoal', 350, 480, 'neutron', 'Wrecklight Freebooters', 0.6, 1, false);

-- 2. five new wild pirate factions (bottom frontier)
INSERT INTO maya_rp.factions
  (session_id, name, standing, trust, treasury, economic_strength, trade_aggressiveness,
   reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, pirate_aggressiveness,
   pirate_fleet_power, pirate_reputation, slave_trade_reputation, pirate_group, status)
VALUES
  (3,'Silt Reaver Legion','hostile',0,20000000,4,0.2,-55,9,
   '{"personality": "aggressive, burial-mad, legion-drilled", "tier": 5, "fear_generated": 5.5}',
   '{"goal": "bury every rival in silt"}', true, 0.9, 4000, 70, 85,'free','active'),
  (3,'Pressure Cult Corsairs','hostile',0,18000000,4,0.2,-60,8,
   '{"personality": "fanatical, deep-dwelling, squeeze-slow", "tier": 5, "fear_generated": 5.0}',
   '{"goal": "crush what the dark touches"}', true, 0.85, 3800, 68, 80,'free','active'),
  (3,'Blacktide Armada','hostile',0,25000000,5,0.3,-50,12,
   '{"personality": "aggressive, black-sailed, tide-swallowing", "tier": 5, "fear_generated": 5.8}',
   '{"goal": "drown the lanes in black"}', true, 0.9, 4500, 72, 90,'free','active'),
  (3,'Drowned Fang Marauders','hostile',0,16000000,3,0.2,-45,7,
   '{"personality": "vindictive, fang-first, salvage-mad", "tier": 5, "fear_generated": 4.8}',
   '{"goal": "sink the traders shallow"}', true, 0.8, 3500, 62, 75,'free','active'),
  (3,'Wrecklight Freebooters','hostile',0,14000000,3,0.25,-40,6,
   '{"personality": "greedy, wreck-drawn, lantern-mad", "tier": 5, "fear_generated": 4.5}',
   '{"goal": "strip every wrecklight dry"}', true, 0.75, 3200, 58, 70,'free','active');

-- 3. dens for the five new packs (regen 8/tick, cap 500)
INSERT INTO maya_rp.pirate_bases (faction_id, system_id, name, hidden, defenses, treasury, status, regen_per_tick, fleet_cap)
SELECT f.id, s.id, b.name, (b.name LIKE '%Pressure%'), 85, 5000000, 'active', 8, 500
FROM maya_rp.factions f
JOIN (VALUES
  ('Silt Reaver Legion','Silt Reaver Pit','Silt Reaver Pit'),
  ('Pressure Cult Corsairs','Pressure Cult Deep','Pressure Cult Deep'),
  ('Blacktide Armada','Blacktide Rift','Blacktide Rift'),
  ('Drowned Fang Marauders','Drowned Fang Hold','Drowned Fang Hold'),
  ('Wrecklight Freebooters','Wrecklight Shoal','Wrecklight Shoal')) AS b(fname, sname, name) ON b.fname = f.name
JOIN maya_rp.sectors s ON s.name = b.sname;

-- 4. queens + kings for the five new packs
INSERT INTO maya_rp.characters
  (session_id, name, role, archetype, bond, status, species, faction_id, controlled_by,
   presence, scene_location, character_type, relationship_to_player, morality, last_seen_day)
SELECT 3, c.cname, c.role, 'pirate', 0, 'active', 'human', f.id, 'faction',
       'available', c.home, 'npc', 0, 15, 2096
FROM maya_rp.factions f
JOIN (VALUES
  ('Silt Reaver Legion','Morva Silt (Pirate Queen)','Pirate Queen of the Silt Reaver Legion','Silt Reaver Pit'),
  ('Silt Reaver Legion','Krag Silt (Pirate King)','Pirate King of the Silt Reaver Legion','Silt Reaver Pit'),
  ('Pressure Cult Corsairs','Umbral Deep (Pirate Queen)','Pirate Queen of the Pressure Cult Corsairs','Pressure Cult Deep'),
  ('Pressure Cult Corsairs','Thorin Depths (Pirate King)','Pirate King of the Pressure Cult Corsairs','Pressure Cult Deep'),
  ('Blacktide Armada','Maris Blacktide (Pirate Queen)','Pirate Queen of the Blacktide Armada','Blacktide Rift'),
  ('Blacktide Armada','Ulric Blacktide (Pirate King)','Pirate King of the Blacktide Armada','Blacktide Rift'),
  ('Drowned Fang Marauders','Syl Drownfang (Pirate Queen)','Pirate Queen of the Drowned Fang Marauders','Drowned Fang Hold'),
  ('Drowned Fang Marauders','Dren Fang (Pirate King)','Pirate King of the Drowned Fang Marauders','Drowned Fang Hold'),
  ('Wrecklight Freebooters','Illia Wrecklight (Pirate Queen)','Pirate Queen of the Wrecklight Freebooters','Wrecklight Shoal'),
  ('Wrecklight Freebooters','Oden Wrecklight (Pirate King)','Pirate King of the Wrecklight Freebooters','Wrecklight Shoal')
) AS c(fname, cname, role, home) ON c.fname = f.name;

-- 5. 500 ships per new pack — T3~T5 mix
INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, tier, power_rating, status)
SELECT 3, s.fname, s.prefix || ' #' || gs.n,
       CASE WHEN gs.n <= 150 THEN 'Corvette'
            WHEN gs.n <= 350 THEN 'Escort'
            ELSE 'Raider' END,
       CASE WHEN gs.n <= 150 THEN 3
            WHEN gs.n <= 350 THEN 4
            ELSE 5 END,
       CASE WHEN gs.n <= 150 THEN 45000 + ((gs.n * 7) % 20) * 1000
            WHEN gs.n <= 350 THEN 65000 + ((gs.n * 11) % 35) * 1000
            ELSE 120000 + ((gs.n * 7) % 50) * 1000 END,
       'active'
FROM (VALUES
  ('Silt Reaver Legion','Silt Fang', 500),
  ('Pressure Cult Corsairs','Pressure Maw', 500),
  ('Blacktide Armada','Black Tide', 500),
  ('Drowned Fang Marauders','Drowned Fang', 500),
  ('Wrecklight Freebooters','Wrecklight', 500)) AS s(fname, prefix, n)
CROSS JOIN LATERAL generate_series(1, s.n) AS gs(n);

-- 6. upgrade existing three bottom packs to 500 cap + top-up their fleets
UPDATE maya_rp.pirate_bases SET regen_per_tick = 8, fleet_cap = 500
WHERE name IN ('Abyssal Trench Hold', 'Lantern Ghost Shoal', 'Riftjaw Maw');

INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, tier, power_rating, status)
SELECT 3, s.fname, s.prefix || ' #' || gs.n,
       CASE WHEN gs.n <= 130 THEN 'Corvette'
            WHEN gs.n <= 280 THEN 'Escort'
            ELSE 'Raider' END,
       CASE WHEN gs.n <= 130 THEN 3
            WHEN gs.n <= 280 THEN 4
            ELSE 5 END,
       CASE WHEN gs.n <= 130 THEN 45000 + ((gs.n * 7) % 20) * 1000
            WHEN gs.n <= 280 THEN 65000 + ((gs.n * 11) % 35) * 1000
            ELSE 120000 + ((gs.n * 7) % 50) * 1000 END,
       'active'
FROM (VALUES
  ('Abyssal Marauders','Trench Fill', 411),
  ('Lantern Wraiths','Lantern Fill', 431),
  ('Riftjaw Corsairs','Rift Fill', 426)) AS s(fname, prefix, n)
CROSS JOIN LATERAL generate_series(1, s.n) AS gs(n);

-- 7. upper veil civilization: denser settled worlds (z=3, narrow but deep)
INSERT INTO maya_rp.sectors (name, x_coord, y_coord, star_type, controlled_by, hazard_level, z_coord, hidden)
VALUES
  ('Silverleaf Enclave', 120, 280, 'main_sequence', 'Skyward Concordat', 0.1, 3, false),
  ('Highmarket Exchange', 280, 200, 'main_sequence', 'Aether Cartels', 0.1, 3, false),
  ('Choir Bell Spire', 350, 320, 'white_dwarf', 'Choir of Glass', 0.2, 3, false),
  ('Stormbreak Academy', 90, 180, 'main_sequence', 'Skyward Concordat', 0.1, 3, false),
  ('Veil Spire University', 220, 400, 'main_sequence', 'Aether Cartels', 0.1, 3, false),
  ('Cloudstep Retreat', 420, 180, 'main_sequence', 'Aether Cartels', 0.1, 3, false);

-- 8. the kingdom hears the shape of the veils
INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance)
VALUES
  (3, NOW() - INTERVAL '40 minutes', 'military', 'The Lower Veil is lawless',
   'Survey of the Lower Veil: eight pirate packs, five hundred hulls apiece, no law but the trench. The bottom of the map is a wilderness with teeth.', '["map","bottom","pirates","wild"]', 5),
  (3, NOW() - INTERVAL '30 minutes', 'government', 'The Upper Veil is settled',
   'The Upper Veil is civilized — academies, exchanges, garden worlds — a settled realm, narrower than the middle but deep with trade and law.', '["map","top","civilization"]', 3),
  (3, NOW() - INTERVAL '20 minutes', 'intel', 'Frontier packs rebuild faster than the rim',
   'Bottom-veil dens regenerate at double the rim rate. Analysts suspect the deep water breeds crews faster than the stars.', '["intel","bottom","regen"]', 3);
