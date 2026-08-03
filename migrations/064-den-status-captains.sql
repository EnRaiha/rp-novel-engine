-- 064: Den status column + named captains (harta karun faces).
ALTER TABLE maya_rp.factions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';

INSERT INTO maya_rp.leaders (faction_id, name, age, gender, traits, stats, approval, active, character_type, controlled_by)
VALUES
(6, 'Kapten Balor Ironhand',     52, 'M', '["ruthless","fleet_commander","battle_hardened"]'::jsonb,
    '{"combat":85,"command":70,"treachery":90}'::jsonb, 35, TRUE, 'npc', 'ai'),
(6, 'Laksamana Sirene Vex',      41, 'F', '["cunning","raider","silver_tongue"]'::jsonb,
    '{"combat":60,"command":80,"treachery":75}'::jsonb, 60, TRUE, 'npc', 'ai'),
(6, 'Kapten Mordekai "The Vulture"', 47, 'M', '["greedy","artillery","siege"]'::jsonb,
    '{"combat":75,"command":55,"treachery":85}'::jsonb, 45, TRUE, 'npc', 'ai');
