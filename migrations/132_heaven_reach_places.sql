-- One name, two places: `garden` is the ship's Eden dome in code and the central city of Heaven
-- Reach in the story. A slug that means two things cannot filter a scene.
--
-- WHAT WAS MEASURED (2026-10-04):
--
--   characters.scene_location matching a location_catalog name   0 rows
--   player_context.location set                                  0 rows
--
-- So nothing depends on any slug yet, and the collision can be fixed before anything does.
--
-- `garden` STAYS THE SHIP'S. Three readers use it for the bioluminescent dome:
--   modules/environment.py:24   'Bioluminescent plants cast soft blue light...'
--   modules/locations.py:11     in the ship-location tuple
--   modules/romance.py:1010     'bioluminescent Eden dome, night cycle'
-- The colony's central city is therefore `garden_city`, which is what the population report calls it:
-- 'GARDEN — bandar pusat'.
--
-- THE SOURCE FOR THE REST is `maya_rag.dsh_turns` turn 73, `LAPORAN POPULASI — HEAVEN REACH`,
-- compiled by Zulaikha Nadira and confirmed by Hasnah Rahim on day 64. It gives three surface
-- settlements and the orbit, with populations, and names the interiors each one has:
--
--   GARDEN          8,400   administration, main clinic, school, river dock, archive,
--                           a 60 m town hall with the captain's office at one end
--   BUKIT KACA      3,300   iron: two furnaces at nine tonnes a day, a 300 kg drop hammer,
--                           an 8 mm plate roller, 62 stone houses
--   PESISIR PANJANG 3,100   fields, livestock, fishing, salt
--   AMANAH            120   archive, data servers, fine laboratories          (orbit)
--   Mistral kedua      60   relay, outer picket                            (orbit)
--   Kapal koloni    2,060   main satellite, second clinic, seed store       (orbit)
--
-- Only the places the prose actually puts someone in are added here. The rest of each settlement's
-- detail stays in the report, which is where a reader should go for it.

INSERT INTO maya_rp.location_catalog (name, location_type, default_lighting, default_sound, default_smell, atmosphere)
VALUES
    -- The central city. Named `garden_city` because `garden` is the ship's dome.
    ('garden_city',              'colony', 'colony floods and windows', 'market, carts, water',   'soil and cooking',   'settled'),
    ('garden_city_dewan',        'colony', 'hall lamps, 60 m of them',  'a crowd finding seats',  'wood and dust',      'formal'),
    ('garden_city_klinik',       'colony', 'clinical white',            'trolleys and voices',    'antiseptic',         'clinical'),
    ('garden_city_sayap_timur',  'colony', 'corridor sconces',          'quiet rooms',            'old building',       'private'),
    -- The orbit three. Seats in the sky that the ground cannot see into.
    ('amanah',                   'ship',   'archive racks and lamp',    'fans and drives',        'paper and ozone',    'archival'),
    ('amanah_arkib',             'ship',   'rack lighting',             'drives spinning',        'paper and ozone',    'archival'),
    ('mistral',                  'ship',   'picket running lights',     'relay chatter',          'cold air',           'watchful'),
    ('kapal_koloni',             'ship',   'satellite interior',        'two thousand people',    'recycled air',       'crowded')
ON CONFLICT (name) DO NOTHING;

COMMENT ON TABLE maya_rp.location_catalog IS
    'The vocabulary for where a scene is. Both characters.scene_location and player_context.location '
    'name a row here, which is what lets a scene cast be filtered at all. Values are slugs. '
    '`garden` is the ship''s Eden dome and `garden_city` is Heaven Reach''s central city: one name '
    'could not mean both, and the ship kept it because three readers already use it.';
