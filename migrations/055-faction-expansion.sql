-- 055-faction-expansion.sql
-- Adds 3 new factions to the TKG universe + territory + relations
-- ============================================================

-- 1. THE DEN — Pirate/Mercenary faction, hostile to everyone
INSERT INTO maya_rp.factions (session_id, name, standing, trust, fear_of_player, treasury, economic_strength, trade_aggressiveness, reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, pirate_aggressiveness, pirate_fleet_power)
SELECT 3, 'The Den', 'hostile', 'none', 80, 5000000, 0.8, 0.9, -50, 30,
       '{"diplomatic": 0.1, "expansionist": 0.8, "aggressiveness": 0.9}'::jsonb,
       '{"tech_priority": 0.1, "economic_priority": 0.2, "military_priority": 0.7}'::jsonb,
       true, 0.9, 200
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.factions WHERE session_id=3 AND name='The Den');

-- 2. FREE PORTS ALLIANCE — Independent traders, neutral to friendly
INSERT INTO maya_rp.factions (session_id, name, standing, trust, fear_of_player, treasury, economic_strength, trade_aggressiveness, reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, pirate_aggressiveness, pirate_fleet_power)
SELECT 3, 'Free Ports Alliance', 'friendly', 'high', 10, 12000000, 0.7, 0.6, 30, 40,
       '{"diplomatic": 0.8, "expansionist": 0.3, "aggressiveness": 0.1}'::jsonb,
       '{"tech_priority": 0.3, "economic_priority": 0.6, "military_priority": 0.1}'::jsonb,
       false, 0.2, 50
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.factions WHERE session_id=3 AND name='Free Ports Alliance');

-- 3. EXODUS FLEET — Bug War refugees, desperate but organised
INSERT INTO maya_rp.factions (session_id, name, standing, trust, fear_of_player, treasury, economic_strength, trade_aggressiveness, reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, pirate_aggressiveness, pirate_fleet_power)
SELECT 3, 'Exodus Fleet', 'neutral', 'medium', 20, 3000000, 0.3, 0.3, 10, 25,
       '{"diplomatic": 0.5, "expansionist": 0.2, "aggressiveness": 0.2}'::jsonb,
       '{"tech_priority": 0.2, "economic_priority": 0.5, "military_priority": 0.3}'::jsonb,
       false, 0.1, 80
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.factions WHERE session_id=3 AND name='Exodus Fleet');

-- 4. LOST COLONIES — Isolated settlements, pre-Fall remnants
INSERT INTO maya_rp.factions (session_id, name, standing, trust, fear_of_player, treasury, economic_strength, trade_aggressiveness, reputation, diplomatic_power, ai_personality, ai_goals, is_pirate, pirate_aggressiveness, pirate_fleet_power)
SELECT 3, 'Lost Colonies', 'unknown', 'none', 50, 1000000, 0.2, 0.1, -10, 10,
       '{"diplomatic": 0.2, "expansionist": 0.4, "aggressiveness": 0.6}'::jsonb,
       '{"tech_priority": 0.4, "economic_priority": 0.3, "military_priority": 0.3}'::jsonb,
       false, 0.3, 30
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.factions WHERE session_id=3 AND name='Lost Colonies');

-- ============================================================
-- FACTION RELATIONS
-- ============================================================

-- Helper: Get faction IDs
DO $$
DECLARE
    den_id INT; fpa_id INT; exodus_id INT; lost_id INT;
    setia_id INT; vein_id INT; iron_id INT; choir_id INT; ghost_id INT;
BEGIN
    SELECT id INTO den_id FROM maya_rp.factions WHERE session_id=3 AND name='The Den';
    SELECT id INTO fpa_id FROM maya_rp.factions WHERE session_id=3 AND name='Free Ports Alliance';
    SELECT id INTO exodus_id FROM maya_rp.factions WHERE session_id=3 AND name='Exodus Fleet';
    SELECT id INTO lost_id FROM maya_rp.factions WHERE session_id=3 AND name='Lost Colonies';
    SELECT id INTO setia_id FROM maya_rp.factions WHERE session_id=3 AND name='Setia Empire (Kingdom)';
    SELECT id INTO vein_id FROM maya_rp.factions WHERE session_id=3 AND name='Vein Collective';
    SELECT id INTO iron_id FROM maya_rp.factions WHERE session_id=3 AND name='Iron Concord';
    SELECT id INTO choir_id FROM maya_rp.factions WHERE session_id=3 AND name='The Silent Choir';
    SELECT id INTO ghost_id FROM maya_rp.factions WHERE session_id=3 AND name='Ghost Signal';

    -- Den relations (hostile to everyone)
    INSERT INTO maya_rp.faction_relations VALUES
    (nextval('maya_rp.faction_relations_id_seq'), 3, den_id, setia_id, 'hostile', 0, 0.8, 'Raided TKG shipping lanes', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, den_id, iron_id, 'hostile', 0, 0.7, 'Attacked Iron Concord outposts', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, den_id, vein_id, 'neutral', 1000, 0.3, 'Occasional Vein toll payments', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, den_id, choir_id, 'neutral', 500, 0.2, 'Mutual non-aggression understanding', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, den_id, ghost_id, 'suspicious', 0, 0.5, 'Den ships vanishing near Ghost Signal space', NOW())
    ON CONFLICT DO NOTHING;

    -- Free Ports relations (traders, welcome everywhere)
    INSERT INTO maya_rp.faction_relations VALUES
    (nextval('maya_rp.faction_relations_id_seq'), 3, fpa_id, setia_id, 'friendly', 5000, 0.1, 'Trade agreement active', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, fpa_id, iron_id, 'friendly', 3000, 0.1, 'Commerce routes open', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, fpa_id, vein_id, 'friendly', 2000, 0.1, 'Vein access fees paid', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, fpa_id, choir_id, 'neutral', 500, 0.2, 'Cautious trade', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, fpa_id, ghost_id, 'suspicious', 100, 0.4, 'Ghost Signal interference with trade routes', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, fpa_id, den_id, 'hostile', 0, 0.6, 'Pirate attacks on Free Port convoys', NOW())
    ON CONFLICT DO NOTHING;

    -- Exodus relations (seeking help, fleeing Bug War)
    INSERT INTO maya_rp.faction_relations VALUES
    (nextval('maya_rp.faction_relations_id_seq'), 3, exodus_id, setia_id, 'friendly', 1000, 0.1, 'Requesting asylum and supplies', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, exodus_id, iron_id, 'neutral', 500, 0.2, 'Limited trade', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, exodus_id, fpa_id, 'friendly', 2000, 0.1, 'Free Ports providing humanitarian aid', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, exodus_id, den_id, 'hostile', 0, 0.7, 'Den preying on refugee convoys', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, exodus_id, vein_id, 'neutral', 300, 0.2, 'Paying for Vein passage', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, exodus_id, ghost_id, 'suspicious', 0, 0.5, 'Refugee ships disappearing near Ghost Signal', NOW())
    ON CONFLICT DO NOTHING;

    -- Lost Colonies (isolationists, wary of everyone)
    INSERT INTO maya_rp.faction_relations VALUES
    (nextval('maya_rp.faction_relations_id_seq'), 3, lost_id, setia_id, 'suspicious', 100, 0.3, 'Rumours of TKG expansion into their space', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, lost_id, den_id, 'hostile', 0, 0.9, 'Den slavers raiding colony worlds', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, lost_id, ghost_id, 'suspicious', 0, 0.6, 'Strange signals from Ghost-adjacent colonies', NOW()),
    (nextval('maya_rp.faction_relations_id_seq'), 3, lost_id, vein_id, 'neutral', 200, 0.2, 'Old pre-Fall Vein access still functional', NOW())
    ON CONFLICT DO NOTHING;
END $$;
