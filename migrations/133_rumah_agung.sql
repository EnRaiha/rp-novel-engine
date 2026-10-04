-- Correcting a guess from 132, and adding the two places it missed.
--
-- 132 added `garden_city_sayap_timur` on the assumption that an east wing belongs to the central
-- city. It does not. Turn 74, `### 3. Rumah agung`, describes the building and then says:
--
--   'Ersya Ardani tinggal di sayap timur, bilik lapan, dan dia tinggal di situ kerana dia memilihnya'
--
-- So the east wing is a wing of the great house. This renames the row and adds the house itself.
--
-- WHAT THE GREAT HOUSE IS, from the same turn: finished in month thirteen, 140 metres long, north of
-- the lake, on land facing the water and facing twelve 200-metre trees on the western horizon. Two
-- wings, three floors, one bathroom per six rooms, a kitchen that feeds three hundred, a reading room
-- with windows on the lake, a long third-floor balcony with one unrequested room at its end. One
-- hundred and twenty rooms, thirty-one occupied in month fourteen.
--
-- AND THE LAKE, from `### 4. Fountain`: four hectares, water clear to the sand, trees growing in it
-- that move without wind, and the blue-green stone on a stone platform at the centre, pulsing at the
-- same nine minutes twelve seconds.
--
-- Nothing in the data uses the old slug yet, so the rename costs nothing:
--
--   characters.scene_location matching a location_catalog name   0 rows
--   player_context.location set                                  0 rows

UPDATE maya_rp.location_catalog
   SET name = 'rumah_agung_sayap_timur'
 WHERE name = 'garden_city_sayap_timur';

INSERT INTO maya_rp.location_catalog (name, location_type, default_lighting, default_sound, default_smell, atmosphere)
VALUES
    ('rumah_agung',        'colony', 'windows on the lake',      'a house of thirty-one',  'wood, cooking, paper', 'domestic'),
    ('fountain',           'surface', 'clear water, no wind',    'nothing, and the pulse', 'wet stone',            'uncanny')
ON CONFLICT (name) DO NOTHING;
