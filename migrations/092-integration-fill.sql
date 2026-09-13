-- 092: integration fill — veil territories, faction relations, gate connections (2026-08-14)
-- The veils had no economic layer (0 territory rows) and no diplomacy graph
-- (0 faction_relations) — economy/news/governor modules were blind to them.
-- Also: gate/passage systems had no sector_connections so voyage can't use them.

-- 1. territory rows for veil civilizations + gates (z=3 top, z=1 bottom)
INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction, population,
                               development_level, status, tax_rate, max_population)
VALUES
  (3,'Skyhold','Skyward Concordat',2800000000,32,'controlled',0.18,6000000000),
  (3,'Aether Bazaar','Aether Cartels',4200000000,38,'controlled',0.15,9000000000),
  (3,'Glass Sanctum','Choir of Glass',1200000000,26,'controlled',0.10,3000000000),
  (3,'Storm Hall','Stormcaller Clans',900000000,20,'controlled',0.12,2000000000),
  (3,'Abyssal Throne','Abyssal Theocracy',3500000000,30,'controlled',0.20,8000000000),
  (3,'Harbor of the Drowned','Drowned Commonwealth',2600000000,34,'controlled',0.16,5500000000),
  (3,'Obsidian Vault','Obsidian Guild',2000000000,36,'controlled',0.14,4500000000),
  (3,'Lantern Court','Lantern Court',3100000000,33,'controlled',0.17,7000000000),
  (3,'Silverleaf Enclave','Skyward Concordat',800000000,24,'controlled',0.15,2000000000),
  (3,'Highmarket Exchange','Aether Cartels',1500000000,30,'controlled',0.14,3500000000),
  (3,'Upper Gate Anchor','Setia Empire',400000000,18,'controlled',0.10,1000000000),
  (3,'Lower Gate Anchor','Setia Empire',400000000,18,'controlled',0.10,1000000000);

-- 2. faction_relations: veil powers know each other + the middle
INSERT INTO maya_rp.faction_relations (session_id, faction_a, faction_b, standing, trade_volume, military_tension, last_interaction)
SELECT 3, a.id, b.id, r.standing, r.trade, r.tension, r.note
FROM (VALUES
  ('Skyward Concordat','Aether Cartels','friendly',4000,0.1,'trade corridor'),
  ('Skyward Concordat','Choir of Glass','neutral',500,0.2,'shared frontier'),
  ('Skyward Concordat','Stormcaller Clans','hostile',0,0.6,'raids on the lanes'),
  ('Aether Cartels','Choir of Glass','friendly',2500,0.1,'glass exports'),
  ('Aether Cartels','Stormcaller Clans','suspicious',300,0.5,'escort fees unpaid'),
  ('Abyssal Theocracy','Drowned Commonwealth','hostile',0,0.5,'tide disputes'),
  ('Abyssal Theocracy','Obsidian Guild','neutral',800,0.3,'dark alloy tolls'),
  ('Drowned Commonwealth','Obsidian Guild','friendly',3500,0.1,'guild financing'),
  ('Drowned Commonwealth','Lantern Court','friendly',3000,0.2,'harbor contracts'),
  ('Obsidian Guild','Lantern Court','neutral',2000,0.2,'candle auctions'),
  ('Lantern Court','Abyssal Theocracy','suspicious',400,0.4,'stray sermons'),
  ('Skyward Concordat','Setia Empire','neutral',1000,0.3,'gate tolls'),
  ('Aether Cartels','Setia Empire','friendly',6000,0.1,'trade through the gates'),
  ('Choir of Glass','Setia Empire','neutral',300,0.2,'quiet observation'),
  ('Stormcaller Clans','Setia Empire','hostile',0,0.5,'storm raids'),
  ('Abyssal Theocracy','Setia Empire','hostile',0,0.5,'the dark watches up'),
  ('Drowned Commonwealth','Setia Empire','neutral',1500,0.3,'toll agreements'),
  ('Obsidian Guild','Setia Empire','neutral',2200,0.2,'alloy contracts'),
  ('Lantern Court','Setia Empire','friendly',2800,0.2,'courtesy of courts'),
  ('Blacktide Armada','Setia Empire','hostile',0,0.7,'black sails on the rim'),
  ('Silt Reaver Legion','Setia Empire','hostile',0,0.6,'legion drills'),
  ('Stormwing Corsairs','Skyward Concordat','hostile',0,0.6,'eyrie raids'),
  ('Glass Reach Reavers','Choir of Glass','hostile',0,0.7,'shattered choir ships'),
  ('Abyssal Marauders','Drowned Commonwealth','hostile',0,0.7,'trench ambushes'),
  ('Lantern Wraiths','Lantern Court','hostile',0,0.6,'ghosts at the court') 
) AS r(name, partner, standing, trade, tension, note)
JOIN maya_rp.factions a ON a.name = r.name
JOIN maya_rp.factions b ON b.name = r.partner;

-- 3. sector_connections for the gates + hidden threads (voyage can use them now)
INSERT INTO maya_rp.sector_connections (session_id, from_sector_id, to_sector_id, distance, travel_time_hours, lane_type)
SELECT 3, a.id, b.id, CASE WHEN a.hidden THEN 240 ELSE 40 END, CASE WHEN a.hidden THEN 96 ELSE 18 END, 'gate'
FROM (VALUES
  ('Aether Gate','Upper Gate Anchor'),
  ('Storm Gate','Storm Anchor'),
  ('Drowned Gate','Lower Gate Anchor'),
  ('Abyss Gate','Abyss Anchor'),
  ('Ghost Thread','Murk Thread'),
  ('Worm Passage','Thread Anchor North'),
  ('Deep Thread','Thread Anchor South')) AS c(from_name, to_name)
JOIN maya_rp.sectors a ON a.name = c.from_name
JOIN maya_rp.sectors b ON b.name = c.to_name;

-- 4. events: the veils join the economy and the diplomatic map
INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance)
VALUES
  (3, NOW() - INTERVAL '10 minutes', 'economy', 'Veil trade begins to flow',
   'Customs at the four gates logged the first veil caravans — Aether silk, Obsidian alloy, Lantern glass. The ledgers of two worlds just touched ours.', '["economy","veils","trade"]', 3),
  (3, NOW() - INTERVAL '5 minutes', 'diplomacy', 'Veil courts open channels',
   'Nine veil powers now hold relations with the middle: three friendly, four neutral, and the dark ones watching from below.', '["diplomacy","veils","relations"]', 3);
