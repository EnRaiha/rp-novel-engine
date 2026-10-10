-- TKG Combat & Fleet Seed
SET LOCAL search_path TO maya_rp;

-- Faction ships: NPC vessels for each faction
INSERT INTO maya_rp.faction_ships (session_id, faction_id, class_name, tier, hull, speed, count) VALUES
    (3, (SELECT id FROM maya_rp.factions WHERE name='The Silent Choir'), 'Wraith Corvette', 3, 1200, 95, 15),
    (3, (SELECT id FROM maya_rp.factions WHERE name='The Silent Choir'), 'Choir Interceptor', 4, 2000, 80, 10),
    (3, (SELECT id FROM maya_rp.factions WHERE name='The Silent Choir'), 'Oracle Carrier', 5, 8000, 45, 3),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Ghost Signal'), 'Ghost Frigate', 3, 1500, 88, 20),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Ghost Signal'), 'Wraith Cruiser', 4, 4500, 65, 8),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Ghost Signal'), 'Phantom Dreadnought', 5, 18000, 35, 2),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Vein Collective'), 'Merchant Escort', 2, 800, 75, 25),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Vein Collective'), 'Vein Guard Cruiser', 3, 3500, 70, 12),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Vein Collective'), 'Collective Battlewagon', 4, 9000, 50, 4),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Iron Concord'), 'Hammer Frigate', 3, 2200, 72, 18),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Iron Concord'), 'Anvil Cruiser', 4, 6000, 55, 10),
    (3, (SELECT id FROM maya_rp.factions WHERE name='Iron Concord'), 'Forge Dreadnought', 5, 22000, 30, 2)
ON CONFLICT DO NOTHING;

-- Raid / encounter templates
INSERT INTO maya_rp.incoming_raids (session_id, faction_name, threat_level, fleet_size_estimate, target_system, status) VALUES
    (3, 'Ghost Signal', 4, 'Small patrol (3-5 ships)', 'Tempa', 'detected'),
    (3, 'The Silent Choir', 3, 'Recon probe (1-2 ships)', 'Bisik', 'monitoring')
ON CONFLICT DO NOTHING;

SELECT 'faction_ships: ' || COUNT(*) FROM maya_rp.faction_ships WHERE session_id=3;
SELECT 'incoming_raids: ' || COUNT(*) FROM maya_rp.incoming_raids WHERE session_id=3;
