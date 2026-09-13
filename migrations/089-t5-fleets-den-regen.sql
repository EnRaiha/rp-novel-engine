-- 089: T5 fleets + den regeneration for the 10 new wild pirates (2026-08-14)
-- King's directive: each new wild pirate pack fields 200-300 T5 units;
-- each den regenerates while its Pirate Queen or King lives. Growth caps
-- at fleet_cap; killing both leaders stops regeneration.

-- 1. den regeneration columns
ALTER TABLE maya_rp.pirate_bases ADD COLUMN IF NOT EXISTS regen_per_tick integer DEFAULT 0;
ALTER TABLE maya_rp.pirate_bases ADD COLUMN IF NOT EXISTS fleet_cap integer DEFAULT 300;

-- 2. new packs become tier-5 powers
UPDATE maya_rp.factions SET
  pirate_fleet_power = v.power,
  ai_personality = '{"tier": 5, "personality": "aggressive, opportunistic, expansionist", "fear_generated": 6.0, "governed_territories": 0}'
FROM (VALUES
  ('Maw Teeth Fleet', 2800),
  ('Starlight Reavers', 2200),
  ('Ashwind Corsairs', 2500),
  ('Blackwater Marauders', 2000),
  ('Redspine Raiders', 3000),
  ('Nightfall Butchers', 2300),
  ('Ironwake Reavers', 2100),
  ('Sunken Star Brigands', 2000),
  ('Gale Runner Freebooters', 2600),
  ('Crimson Shoals Pirates', 2400)) AS v(name, power)
WHERE maya_rp.factions.name = v.name AND maya_rp.factions.is_pirate;

-- 3. den regen: 5 ships/tick, cap per pack size
UPDATE maya_rp.pirate_bases SET regen_per_tick = 5, fleet_cap = v.cap
FROM (VALUES
  ('Maw Teeth Anchorage', 280),
  ('Starlight Shoal', 220),
  ('Ashwind Boneyard', 250),
  ('Blackwater Reach', 200),
  ('Redspine Perch', 300),
  ('Nightfall Slip', 230),
  ('Ironwake Graveyard', 210),
  ('Sunken Star Hollow', 200),
  ('Gale Runner Wake', 260),
  ('Crimson Shoals Cut', 240)) AS v(name, cap)
WHERE maya_rp.pirate_bases.name = v.name;

-- 4. T5 swarm per pack (200-300 units each; existing 2 ships stay as flagships)
INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, tier, power_rating, status)
SELECT 3, s.fname, s.prefix || ' #' || gs.n, 'Raider', 5,
       120000 + ((gs.n * 7) % 50) * 1000, 'active'
FROM (VALUES
  ('Maw Teeth Fleet','Maw Tooth', 278),
  ('Starlight Reavers','Star Thief', 218),
  ('Ashwind Corsairs','Ash Hound', 248),
  ('Blackwater Marauders','Drowned Bell', 198),
  ('Redspine Raiders','Spine Splitter', 298),
  ('Nightfall Butchers','Grim Larder', 228),
  ('Ironwake Reavers','Wake Harrow', 208),
  ('Sunken Star Brigands','Drowned Crown', 198),
  ('Gale Runner Freebooters','Gale Answer', 258),
  ('Crimson Shoals Pirates','Shoal Bleeder', 238)) AS s(fname, prefix, n)
CROSS JOIN LATERAL generate_series(1, s.n) AS gs(n);

-- 5. the rim notices
INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance)
VALUES
  (3, NOW() - INTERVAL '3 hours', 'military', 'Ten wolf-packs muster on the rim',
   'Listening posts counted ten new raider swarms on the rim — hundreds of T5 hulls each, led by queens and kings. The frontier just got teeth.', '["military","pirate","t5"]', 5),
  (3, NOW() - INTERVAL '2 hours', 'intel', 'Pirate dens rebuild while their leaders live',
   'Pattern analysis: raider dens regenerate losses within days — but only while their queen or king still flies. Kill the crown, kill the swarm.', '["intel","pirate","regen"]', 4),
  (3, NOW() - INTERVAL '1 hour', 'rumour', 'The packs answer to no one',
   'Free Port brokers confirm: the ten new packs pay no tolls and fly no patron''s banner. Wild and free — for now.', '["rumour","pirate","wild"]', 2);
