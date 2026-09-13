-- 087: seed 10 wild & free pirate factions with pirate queens + kings (2026-08-14)
-- King's directive: wild pirates come with a queen AND a king.
-- Each faction gets: faction row (group=free), hidden base, 2 faction ships,
-- and 2 characters (Pirate Queen + Pirate King).

INSERT INTO maya_rp.factions
  (id, session_id, name, standing, trust, treasury, economic_strength, trade_aggressiveness,
   reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, pirate_aggressiveness,
   pirate_base_system_id, pirate_fleet_power, pirate_reputation, slave_trade_reputation,
   pirate_group, status)
VALUES
  (44,3,'Maw Teeth Fleet','hostile',0,3000000,3,0.2,-45,10,
   '{"personality": "aggressive, opportunistic, expansionist", "tier": 2, "fear_generated": 3.0}',
   '{"goal": "expand raiding corridor"}', true, 0.9, 1126, 1200, 60, 85,'free','active'),
  (45,3,'Starlight Reavers','hostile',0,1800000,4,0.3,-30,8,
   '{"personality": "greedy, opportunistic"}',
   '{"goal": "loot shipping lanes"}', true, 0.7, 1127, 700, 50, 70,'free','active'),
  (46,3,'Ashwind Corsairs','hostile',0,2200000,3,0.2,-40,9,
   '{"personality": "vindictive, reckless"}',
   '{"goal": "burn trade convoys"}', true, 0.8, 1128, 900, 55, 80,'free','active'),
  (47,3,'Blackwater Marauders','hostile',0,1400000,2,0.1,-50,6,
   '{"personality": "cautious, paranoid"}',
   '{"goal": "hold the black water"}', true, 0.6, 1129, 450, 45, 60,'free','active'),
  (48,3,'Redspine Raiders','hostile',0,2600000,3,0.2,-35,10,
   '{"personality": "aggressive, opportunistic"}',
   '{"goal": "claim salvage rights"}', true, 0.8, 1131, 1000, 55, 75,'free','active'),
  (49,3,'Nightfall Butchers','hostile',0,1200000,2,0.1,-55,5,
   '{"personality": "vindictive, reckless"}',
   '{"goal": "terrify border colonies"}', true, 0.85, 1126, 600, 65, 90,'free','active'),
  (50,3,'Ironwake Reavers','hostile',0,2000000,3,0.2,-40,8,
   '{"personality": "greedy, opportunistic"}',
   '{"goal": "strip derelict fleets"}', true, 0.7, 1128, 800, 50, 65,'free','active'),
  (51,3,'Sunken Star Brigands','hostile',0,1600000,2,0.15,-45,7,
   '{"personality": "cautious, paranoid"}',
   '{"goal": "ransom captured crews"}', true, 0.65, 1129, 500, 55, 85,'free','active'),
  (52,3,'Gale Runner Freebooters','hostile',0,2400000,4,0.35,-25,12,
   '{"personality": "greedy, opportunistic, expansionist"}',
   '{"goal": "run the long lanes"}', true, 0.75, 1127, 850, 40, 55,'free','active'),
  (53,3,'Crimson Shoals Pirates','hostile',0,1300000,2,0.1,-50,5,
   '{"personality": "vindictive, reckless"}',
   '{"goal": "bleed the shallows dry"}', true, 0.8, 1131, 550, 60, 80,'free','active');

-- Hidden pirate bases (one per new faction)
INSERT INTO maya_rp.pirate_bases (faction_id, system_id, name, hidden, defenses, treasury, status)
SELECT f.id, f.pirate_base_system_id, b.name, (b.name LIKE '%Nightfall%' OR b.name LIKE '%Sunken%'), 60, 800000, 'active'
FROM maya_rp.factions f
JOIN (VALUES
  ('Maw Teeth Fleet','Maw Teeth Anchorage'),
  ('Starlight Reavers','Starlight Shoal'),
  ('Ashwind Corsairs','Ashwind Boneyard'),
  ('Blackwater Marauders','Blackwater Reach'),
  ('Redspine Raiders','Redspine Perch'),
  ('Nightfall Butchers','Nightfall Slip'),
  ('Ironwake Reavers','Ironwake Graveyard'),
  ('Sunken Star Brigands','Sunken Star Hollow'),
  ('Gale Runner Freebooters','Gale Runner Wake'),
  ('Crimson Shoals Pirates','Crimson Shoals Cut')) AS b(fname, name) ON b.fname = f.name
WHERE f.is_pirate AND f.pirate_group='free' AND f.name IN (
  'Maw Teeth Fleet','Starlight Reavers','Ashwind Corsairs','Blackwater Marauders','Redspine Raiders',
  'Nightfall Butchers','Ironwake Reavers','Sunken Star Brigands','Gale Runner Freebooters','Crimson Shoals Pirates');

-- 2 raiding ships per new faction
INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, tier, power_rating, status)
SELECT 3, f.name, s.ship_name, s.class_name, s.tier, s.power_rating, 'active'
FROM maya_rp.factions f
JOIN (VALUES
  ('Maw Teeth Fleet','Maw Tooth','Raider',2,52000),
  ('Maw Teeth Fleet','Black Bite','Escort',2,31000),
  ('Starlight Reavers','Lumen''s Lure','Raider',2,47000),
  ('Starlight Reavers','Star Thief','Corvette',2,28000),
  ('Ashwind Corsairs','Ash Hound','Raider',2,55000),
  ('Ashwind Corsairs','Cinder Fang','Escort',2,33000),
  ('Blackwater Marauders','Drowned Bell','Raider',2,40000),
  ('Blackwater Marauders','Murky Oath','Corvette',2,24000),
  ('Redspine Raiders','Spine Splitter','Raider',3,78000),
  ('Redspine Raiders','Red Wake','Escort',2,36000),
  ('Nightfall Butchers','Grim Larder','Raider',2,49000),
  ('Nightfall Butchers','Dusk Knife','Corvette',2,30000),
  ('Ironwake Reavers','Wake Harrow','Raider',2,44000),
  ('Ironwake Reavers','Rust Covenant','Escort',2,27000),
  ('Sunken Star Brigands','Drowned Crown','Raider',2,38000),
  ('Sunken Star Brigands','Black Tide','Corvette',2,22000),
  ('Gale Runner Freebooters','Gale Answer','Raider',3,72000),
  ('Gale Runner Freebooters','Wind Debt','Escort',2,34000),
  ('Crimson Shoals Pirates','Shoal Bleeder','Raider',2,46000),
  ('Crimson Shoals Pirates','Keel Splitter','Corvette',2,26000)) AS s(fname, ship_name, class_name, tier, power_rating) ON s.fname = f.name
WHERE f.is_pirate AND f.name IN (
  'Maw Teeth Fleet','Starlight Reavers','Ashwind Corsairs','Blackwater Marauders','Redspine Raiders',
  'Nightfall Butchers','Ironwake Reavers','Sunken Star Brigands','Gale Runner Freebooters','Crimson Shoals Pirates');

-- Pirate Queens + Kings (characters)
INSERT INTO maya_rp.characters
  (session_id, name, role, archetype, bond, status, species, faction_id, controlled_by,
   presence, scene_location, character_type, relationship_to_player, morality, last_seen_day)
SELECT 3, c.cname, c.role, 'pirate', 0, 'active', 'human', f.id, 'faction',
       'available', c.base, 'npc', 0, 15, 2096
FROM maya_rp.factions f
JOIN (VALUES
  ('Maw Teeth Fleet','Rixa Maw (Pirate Queen)','Pirate Queen of the Maw Teeth Fleet','Maw Teeth Anchorage'),
  ('Maw Teeth Fleet','Harrow Blackmaw (Pirate King)','Pirate King of the Maw Teeth Fleet','Maw Teeth Anchorage'),
  ('Starlight Reavers','Lumen Cordis (Pirate Queen)','Pirate Queen of the Starlight Reavers','Starlight Shoal'),
  ('Starlight Reavers','Caster Vane (Pirate King)','Pirate King of the Starlight Reavers','Starlight Shoal'),
  ('Ashwind Corsairs','Ember Vos (Pirate Queen)','Pirate Queen of the Ashwind Corsairs','Ashwind Boneyard'),
  ('Ashwind Corsairs','Korr Ashwind (Pirate King)','Pirate King of the Ashwind Corsairs','Ashwind Boneyard'),
  ('Blackwater Marauders','Sable Marr (Pirate Queen)','Pirate Queen of the Blackwater Marauders','Blackwater Reach'),
  ('Blackwater Marauders','Dagon Vey (Pirate King)','Pirate King of the Blackwater Marauders','Blackwater Reach'),
  ('Redspine Raiders','Velka Spine (Pirate Queen)','Pirate Queen of the Redspine Raiders','Redspine Perch'),
  ('Redspine Raiders','Mord Rax (Pirate King)','Pirate King of the Redspine Raiders','Redspine Perch'),
  ('Nightfall Butchers','Nyx Fell (Pirate Queen)','Pirate Queen of the Nightfall Butchers','Nightfall Slip'),
  ('Nightfall Butchers','Karn Dusk (Pirate King)','Pirate King of the Nightfall Butchers','Nightfall Slip'),
  ('Ironwake Reavers','Vessa Ironwake (Pirate Queen)','Pirate Queen of the Ironwake Reavers','Ironwake Graveyard'),
  ('Ironwake Reavers','Torr Wake (Pirate King)','Pirate King of the Ironwake Reavers','Ironwake Graveyard'),
  ('Sunken Star Brigands','Mira Drown (Pirate Queen)','Pirate Queen of the Sunken Star Brigands','Sunken Star Hollow'),
  ('Sunken Star Brigands','Orpheus Vey (Pirate King)','Pirate King of the Sunken Star Brigands','Sunken Star Hollow'),
  ('Gale Runner Freebooters','Zephyr Gale (Pirate Queen)','Pirate Queen of the Gale Runner Freebooters','Gale Runner Wake'),
  ('Gale Runner Freebooters','Stryker Run (Pirate King)','Pirate King of the Gale Runner Freebooters','Gale Runner Wake'),
  ('Crimson Shoals Pirates','Sanguis Shoal (Pirate Queen)','Pirate Queen of the Crimson Shoals Pirates','Crimson Shoals Cut'),
  ('Crimson Shoals Pirates','Ruber Keel (Pirate King)','Pirate King of the Crimson Shoals Pirates','Crimson Shoals Cut')
) AS c(fname, cname, role, base) ON c.fname = f.name
WHERE f.is_pirate AND f.name IN (
  'Maw Teeth Fleet','Starlight Reavers','Ashwind Corsairs','Blackwater Marauders','Redspine Raiders',
  'Nightfall Butchers','Ironwake Reavers','Sunken Star Brigands','Gale Runner Freebooters','Crimson Shoals Pirates');
