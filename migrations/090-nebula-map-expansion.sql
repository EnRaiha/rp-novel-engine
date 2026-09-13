-- 090: Nebula Map Expansion — Upper Veil (top) + Lower Veil (bottom), 500×500 each (2026-08-14)
-- King's directive: two new nebulae above and below the current map.
--   - FEW chokepoints: central (Setia) controls both sides of each gate.
--   - SEVERAL hidden passages: unmarked routes (one top↔bottom secret thread).
--   - New factions for both nebulae + pirate dens with queen & king + characters.

-- 1. schema: z-layer (z=2 current map, z=1 bottom veil, z=3 top veil),
--    hidden flag, gate/passage links
ALTER TABLE maya_rp.sectors ADD COLUMN IF NOT EXISTS z_coord integer DEFAULT 2;
ALTER TABLE maya_rp.sectors ADD COLUMN IF NOT EXISTS hidden boolean DEFAULT false;
ALTER TABLE maya_rp.sectors ADD COLUMN IF NOT EXISTS connects_to integer;

-- fix stale sectors sequence (max id 1750 vs 625 rows)
SELECT setval('maya_rp.sectors_id_seq', (SELECT MAX(id) FROM maya_rp.sectors));

-- 2. central gate anchors (Setia controls the central side of every connection)
INSERT INTO maya_rp.sectors (name, x_coord, y_coord, z_coord, star_type, controlled_by, hazard_level, hidden)
VALUES
  ('Upper Gate Anchor', 25, 12, 2, 'main_sequence', 'Setia Empire', 0.3, false),
  ('Storm Anchor', 25, 8, 2, 'red_giant', 'Setia Empire', 0.4, false),
  ('Lower Gate Anchor', 12, 25, 2, 'main_sequence', 'Setia Empire', 0.3, false),
  ('Abyss Anchor', 8, 25, 2, 'red_giant', 'Setia Empire', 0.5, false),
  ('Thread Anchor North', 25, 20, 2, 'neutron', 'Setia Empire', 0.7, false),
  ('Thread Anchor South', 20, 25, 2, 'neutron', 'Setia Empire', 0.7, false);

-- 3. TOP NEBULA — The Upper Veil
INSERT INTO maya_rp.sectors (name, x_coord, y_coord, star_type, controlled_by, hazard_level, z_coord, hidden, connects_to)
VALUES
  -- home systems
  ('Skyhold', 100, 400, 'main_sequence', 'Skyward Concordat', 0.2, 3, false, NULL),
  ('Aether Bazaar', 250, 350, 'main_sequence', 'Aether Cartels', 0.2, 3, false, NULL),
  ('Glass Sanctum', 400, 250, 'white_dwarf', 'Choir of Glass', 0.3, 3, false, NULL),
  ('Storm Hall', 150, 100, 'red_giant', 'Stormcaller Clans', 0.4, 3, false, NULL),
  -- pirate dens
  ('Stormwing Eyrie', 80, 60, 'main_sequence', 'Stormwing Corsairs', 0.5, 3, false, NULL),
  ('Glass Reach Spire', 380, 380, 'white_dwarf', 'Glass Reach Reavers', 0.5, 3, false, NULL),
  ('Hollow Wind Nest', 300, 100, 'main_sequence', 'Hollow Wind Buccaneers', 0.4, 3, false, NULL),
  -- chokepoints: Setia controls the nebula side too
  ('Aether Gate', 20, 250, 'main_sequence', 'Setia Empire', 0.3, 3, false,
   (SELECT id FROM maya_rp.sectors WHERE name='Upper Gate Anchor')),
  ('Storm Gate', 30, 100, 'red_giant', 'Setia Empire', 0.4, 3, false,
   (SELECT id FROM maya_rp.sectors WHERE name='Storm Anchor')),
  -- hidden passages
  ('Ghost Thread', 450, 450, 'neutron', NULL, 0.9, 3, true,
   (SELECT id FROM maya_rp.sectors WHERE name='Murk Thread')),
  ('Worm Passage', 10, 480, 'neutron', NULL, 0.8, 3, true,
   (SELECT id FROM maya_rp.sectors WHERE name='Thread Anchor North')),
  -- filler systems
  ('Veil Drift Station', 300, 250, 'main_sequence', NULL, 0.3, 3, false, NULL),
  ('Cloudfall Reach', 450, 150, 'main_sequence', 'Skyward Concordat', 0.3, 3, false, NULL),
  ('Highmark', 180, 300, 'main_sequence', NULL, 0.2, 3, false, NULL);

-- 4. BOTTOM NEBULA — The Lower Veil
INSERT INTO maya_rp.sectors (name, x_coord, y_coord, star_type, controlled_by, hazard_level, z_coord, hidden, connects_to)
VALUES
  -- home systems
  ('Abyssal Throne', 400, 100, 'red_giant', 'Abyssal Theocracy', 0.4, 1, false, NULL),
  ('Harbor of the Drowned', 250, 150, 'main_sequence', 'Drowned Commonwealth', 0.3, 1, false, NULL),
  ('Obsidian Vault', 100, 350, 'white_dwarf', 'Obsidian Guild', 0.3, 1, false, NULL),
  ('Lantern Court', 450, 350, 'main_sequence', 'Lantern Court', 0.2, 1, false, NULL),
  -- pirate dens
  ('Abyssal Trench Hold', 350, 50, 'red_giant', 'Abyssal Marauders', 0.6, 1, false, NULL),
  ('Lantern Ghost Shoal', 480, 250, 'white_dwarf', 'Lantern Wraiths', 0.5, 1, false, NULL),
  ('Riftjaw Maw', 150, 450, 'neutron', 'Riftjaw Corsairs', 0.6, 1, false, NULL),
  -- chokepoints
  ('Drowned Gate', 20, 250, 'main_sequence', 'Setia Empire', 0.3, 1, false,
   (SELECT id FROM maya_rp.sectors WHERE name='Lower Gate Anchor')),
  ('Abyss Gate', 30, 100, 'red_giant', 'Setia Empire', 0.4, 1, false,
   (SELECT id FROM maya_rp.sectors WHERE name='Abyss Anchor')),
  -- hidden passages (Murk Thread is the top↔bottom secret)
  ('Murk Thread', 450, 450, 'neutron', NULL, 0.9, 1, true,
   (SELECT id FROM maya_rp.sectors WHERE name='Ghost Thread')),
  ('Deep Thread', 10, 480, 'neutron', NULL, 0.8, 1, true,
   (SELECT id FROM maya_rp.sectors WHERE name='Thread Anchor South')),
  -- filler systems
  ('Tide Shadow Station', 300, 300, 'main_sequence', NULL, 0.3, 1, false, NULL),
  ('Belowmark', 180, 200, 'main_sequence', NULL, 0.2, 1, false, NULL),
  ('Silt Drift', 60, 400, 'white_dwarf', 'Obsidian Guild', 0.3, 1, false, NULL);

-- 5. civilian factions — 4 top, 4 bottom
INSERT INTO maya_rp.factions
  (session_id, name, standing, trust, treasury, economic_strength, trade_aggressiveness,
   reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, status)
VALUES
  (3,'Skyward Concordat','neutral',10,90000000,8,0.4,20,60,
   '{"personality": "proud, martial, disciplined"}','{"goal": "control the upper gates"}', false,'active'),
  (3,'Aether Cartels','friendly',20,150000000,12,0.8,15,70,
   '{"personality": "mercantile, neutral, smiling"}','{"goal": "tax every trade lane"}', false,'active'),
  (3,'Choir of Glass','neutral',5,60000000,6,0.1,10,40,
   '{"personality": "isolationist, liturgical"}','{"goal": "keep the sanctum unbroken"}', false,'active'),
  (3,'Stormcaller Clans','hostile',0,40000000,5,0.3,-10,30,
   '{"personality": "aggressive, honor-bound, storm-worshipping"}','{"goal": "raid the trade lanes"}', false,'active'),
  (3,'Abyssal Theocracy','hostile',0,70000000,7,0.2,-15,45,
   '{"personality": "fanatical, patient, deep"}','{"goal": "drown the light above"}', false,'active'),
  (3,'Drowned Commonwealth','neutral',10,80000000,9,0.5,10,50,
   '{"personality": "pragmatic, communal, tide-marked"}','{"goal": "trade with the upper sea"}', false,'active'),
  (3,'Obsidian Guild','neutral',15,120000000,10,0.6,25,65,
   '{"personality": "mercantile, secretive, exact"}','{"goal": "monopolize the dark alloys"}', false,'active'),
  (3,'Lantern Court','friendly',25,110000000,11,0.5,30,55,
   '{"personality": "graceful, duplicitous, candlelit"}','{"goal": "light every court and collect the debts"}', false,'active');

-- 6. six new pirate factions (wild & free) with dens + queens + kings
INSERT INTO maya_rp.factions
  (session_id, name, standing, trust, treasury, economic_strength, trade_aggressiveness,
   reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, pirate_aggressiveness,
   pirate_fleet_power, pirate_reputation, slave_trade_reputation, pirate_group, status)
VALUES
  (3,'Stormwing Corsairs','hostile',0,8000000,3,0.2,-40,8,
   '{"personality": "aggressive, airborne, pack-hunting", "tier": 4, "fear_generated": 4.5}',
   '{"goal": "own the upper winds"}', true, 0.8, 1400, 60, 80,'free','active'),
  (3,'Glass Reach Reavers','hostile',0,6000000,2,0.15,-35,6,
   '{"personality": "vindictive, crystalline, patient", "tier": 4, "fear_generated": 4.0}',
   '{"goal": "shatter the choir lanes"}', true, 0.7, 1100, 55, 75,'free','active'),
  (3,'Hollow Wind Buccaneers','hostile',0,5000000,2,0.2,-30,5,
   '{"personality": "greedy, hollow, drifting", "tier": 4, "fear_generated": 3.5}',
   '{"goal": "fill the hollow hold"}', true, 0.6, 900, 45, 60,'free','active'),
  (3,'Abyssal Marauders','hostile',0,9000000,3,0.2,-45,9,
   '{"personality": "aggressive, deep-dwelling, pressure-hard", "tier": 4, "fear_generated": 4.8}',
   '{"goal": "drag prizes to the trench"}', true, 0.85, 1500, 65, 85,'free','active'),
  (3,'Lantern Wraiths','hostile',0,7000000,3,0.25,-50,7,
   '{"personality": "vindictive, ghostly, contract-hungry", "tier": 4, "fear_generated": 4.2}',
   '{"goal": "haunt the court lanes"}', true, 0.75, 1200, 60, 80,'free','active'),
  (3,'Riftjaw Corsairs','hostile',0,6500000,2,0.2,-38,6,
   '{"personality": "reckless, bite-first, salvage-mad", "tier": 4, "fear_generated": 4.0}',
   '{"goal": "chew the rift clean"}', true, 0.7, 1050, 50, 70,'free','active');

-- 7. pirate dens (regen 3/tick while queen or king lives)
INSERT INTO maya_rp.pirate_bases (faction_id, system_id, name, hidden, defenses, treasury, status, regen_per_tick, fleet_cap)
SELECT f.id, s.id, b.name, (b.name LIKE '%Ghost%' OR b.name LIKE '%Trench%'), 70, 2000000, 'active', 3, b.cap
FROM maya_rp.factions f
JOIN (VALUES
  ('Stormwing Corsairs','Stormwing Eyrie','Stormwing Eyrie', 80),
  ('Glass Reach Reavers','Glass Reach Spire','Glass Reach Spire', 70),
  ('Hollow Wind Buccaneers','Hollow Wind Nest','Hollow Wind Nest', 60),
  ('Abyssal Marauders','Abyssal Trench Hold','Abyssal Trench Hold', 90),
  ('Lantern Wraiths','Lantern Ghost Shoal','Lantern Ghost Shoal', 70),
  ('Riftjaw Corsairs','Riftjaw Maw','Riftjaw Maw', 75)) AS b(fname, sname, name, cap) ON b.fname = f.name
JOIN maya_rp.sectors s ON s.name = b.sname;

-- 8. flagships + T5 swarm for the six new dens
INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, tier, power_rating, status)
SELECT 3, s.fname, s.flag, 'Raider', 5, 180000, 'active'
FROM (VALUES
  ('Stormwing Corsairs','Stormwing Talon'),
  ('Glass Reach Reavers','Glass Splinter'),
  ('Hollow Wind Buccaneers','Hollow Gale'),
  ('Abyssal Marauders','Trench King'),
  ('Lantern Wraiths','Ghost Lantern'),
  ('Riftjaw Corsairs','Riftjaw Prime')) AS s(fname, flag);

INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, tier, power_rating, status)
SELECT 3, s.fname, s.prefix || ' #' || gs.n, 'Raider', 5,
       120000 + ((gs.n * 7) % 50) * 1000, 'active'
FROM (VALUES
  ('Stormwing Corsairs','Stormwing', 78),
  ('Glass Reach Reavers','Glass Fang', 68),
  ('Hollow Wind Buccaneers','Hollow Wind', 58),
  ('Abyssal Marauders','Trench Maw', 88),
  ('Lantern Wraiths','Lantern Shade', 68),
  ('Riftjaw Corsairs','Riftjaw', 73)) AS s(fname, prefix, n)
CROSS JOIN LATERAL generate_series(1, s.n) AS gs(n);

-- civilian fleets (20 T4 ships each)
INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, tier, power_rating, status)
SELECT 3, s.fname, s.prefix || ' #' || gs.n, 'Escort', 4,
       60000 + ((gs.n * 11) % 40) * 1000, 'active'
FROM (VALUES
  ('Skyward Concordat','Sky Pike', 20),
  ('Aether Cartels','Aether Ledger', 20),
  ('Choir of Glass','Glass Chorale', 20),
  ('Stormcaller Clans','Storm Lance', 20),
  ('Abyssal Theocracy','Abyss Censer', 20),
  ('Drowned Commonwealth','Tide Plow', 20),
  ('Obsidian Guild','Obsidian Wager', 20),
  ('Lantern Court','Lantern Taper', 20)) AS s(fname, prefix, n)
CROSS JOIN LATERAL generate_series(1, s.n) AS gs(n);

-- 9. characters: 16 civilian leaders
INSERT INTO maya_rp.characters
  (session_id, name, role, archetype, bond, status, species, faction_id, controlled_by,
   presence, scene_location, character_type, relationship_to_player, morality, last_seen_day)
SELECT 3, c.cname, c.role, 'leader', 0, 'active', 'human', f.id, 'faction',
       'available', c.home, 'npc', 0, c.mor, 2096
FROM maya_rp.factions f
JOIN (VALUES
  ('Skyward Concordat','Aeric Stormhold (Sky-Marshal)','Sky-Marshal of the Skyward Concordat','Skyhold',20),
  ('Skyward Concordat','Elys Cadence (Speaker)','Speaker of the Concordat Diet','Skyhold',25),
  ('Aether Cartels','Silas Aether (Cartel Master)','Cartel Master of the Aether Cartels','Aether Bazaar',10),
  ('Aether Cartels','Mirel Corvus (Grand Factor)','Grand Factor of the Aether Cartels','Aether Bazaar',15),
  ('Choir of Glass','Elena Crystaline (High Chorister)','High Chorister of the Choir of Glass','Glass Sanctum',30),
  ('Choir of Glass','Thel Vess (Shard Keeper)','Keeper of the Sanctum Shard','Glass Sanctum',30),
  ('Stormcaller Clans','Halvar Stormcaller (Storm-Chief)','Storm-Chief of the Stormcaller Clans','Storm Hall',5),
  ('Stormcaller Clans','Nym Riptide (Tide-Speaker)','Tide-Speaker of the Stormcaller Clans','Storm Hall',10),
  ('Abyssal Theocracy','Drevan Deep (Hierophant)','Deep Hierophant of the Abyssal Theocracy','Abyssal Throne',5),
  ('Abyssal Theocracy','Ishara Murk (Dark Warden)','Warden of the Dark','Abyssal Throne',5),
  ('Drowned Commonwealth','Kestor Halcyon (Tidal Lord)','Tidal Lord of the Drowned Commonwealth','Harbor of the Drowned',20),
  ('Drowned Commonwealth','Bren Drownmere (Harbor Chancellor)','Harbor Chancellor of the Drowned Commonwealth','Harbor of the Drowned',20),
  ('Obsidian Guild','Ossian Obsidian (Guildmaster)','Guildmaster of the Obsidian Guild','Obsidian Vault',10),
  ('Obsidian Guild','Ferra Shard (Guild Scribe)','Scribe of the Obsidian Guild','Obsidian Vault',15),
  ('Lantern Court','Lucera Hale (Lantern Queen)','Lantern Queen of the Lantern Court','Lantern Court',15),
  ('Lantern Court','Devrin Wick (Court Marshal)','Marshal of the Lantern Court','Lantern Court',10)
) AS c(fname, cname, role, home, mor) ON c.fname = f.name;

-- 10. characters: 12 pirate queens + kings
INSERT INTO maya_rp.characters
  (session_id, name, role, archetype, bond, status, species, faction_id, controlled_by,
   presence, scene_location, character_type, relationship_to_player, morality, last_seen_day)
SELECT 3, c.cname, c.role, 'pirate', 0, 'active', 'human', f.id, 'faction',
       'available', c.home, 'npc', 0, 15, 2096
FROM maya_rp.factions f
JOIN (VALUES
  ('Stormwing Corsairs','Aeris Stormwing (Pirate Queen)','Pirate Queen of the Stormwing Corsairs','Stormwing Eyrie'),
  ('Stormwing Corsairs','Vane Cloudbreak (Pirate King)','Pirate King of the Stormwing Corsairs','Stormwing Eyrie'),
  ('Glass Reach Reavers','Seraphine Glass (Pirate Queen)','Pirate Queen of the Glass Reach Reavers','Glass Reach Spire'),
  ('Glass Reach Reavers','Kael Reach (Pirate King)','Pirate King of the Glass Reach Reavers','Glass Reach Spire'),
  ('Hollow Wind Buccaneers','Tessa Hollow (Pirate Queen)','Pirate Queen of the Hollow Wind Buccaneers','Hollow Wind Nest'),
  ('Hollow Wind Buccaneers','Ren Kite (Pirate King)','Pirate King of the Hollow Wind Buccaneers','Hollow Wind Nest'),
  ('Abyssal Marauders','Nereida Abyss (Pirate Queen)','Pirate Queen of the Abyssal Marauders','Abyssal Trench Hold'),
  ('Abyssal Marauders','Drek Tidebreak (Pirate King)','Pirate King of the Abyssal Marauders','Abyssal Trench Hold'),
  ('Lantern Wraiths','Ilyra Lantern (Pirate Queen)','Pirate Queen of the Lantern Wraiths','Lantern Ghost Shoal'),
  ('Lantern Wraiths','Orin Dusklight (Pirate King)','Pirate King of the Lantern Wraiths','Lantern Ghost Shoal'),
  ('Riftjaw Corsairs','Selka Riftjaw (Pirate Queen)','Pirate Queen of the Riftjaw Corsairs','Riftjaw Maw'),
  ('Riftjaw Corsairs','Bronn Undertow (Pirate King)','Pirate King of the Riftjaw Corsairs','Riftjaw Maw')
) AS c(fname, cname, role, home) ON c.fname = f.name;

-- 11. the kingdom learns of the veils
INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance)
VALUES
  (3, NOW() - INTERVAL '90 minutes', 'anomaly', 'Two veils mapped above and below',
   'Cartography division confirms two vast nebulae — the Upper Veil and the Lower Veil — each five hundred spans across, above and below the known map.', '["map","nebula","veil"]', 5),
  (3, NOW() - INTERVAL '80 minutes', 'government', 'The gates are ours',
   'Four gate systems secured: Aether, Storm, Drowned, and Abyss. Both sides of each chokepoint fly the Setia banner.', '["map","gates","setia"]', 4),
  (3, NOW() - INTERVAL '70 minutes', 'rumour', 'Hidden threads between the veils',
   'Deep-space pilots whisper of unmarked passages — a Ghost Thread, a Murk Thread, a Worm Passage — routes that do not appear on any chart.', '["rumour","hidden","passages"]', 3),
  (3, NOW() - INTERVAL '60 minutes', 'faction', 'Fourteen powers stir in the veils',
   'Two nebulae, fourteen new powers: Concordats, Cartels, Choirs, Courts — and six new pirate packs with queens and kings.', '["faction","veils","powers"]', 4);
