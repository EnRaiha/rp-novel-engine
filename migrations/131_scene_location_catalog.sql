-- SYSTEMIC: the engine has no table that says where a scene is, so scene location is prose on one
-- side and a parsed substring on the other, and they cannot meet.
--
-- WHAT WAS MEASURED (2026-10-04, see wiki/rp-dev/SCENE-LOCATION-2026-10-04.md):
--
--   characters.scene_location   free prose: 'MASTIKA — Royal Palace (household)', 'CHOIR SPACE — silent'
--   get_player_location()       a slug parsed from player_context.current_focus by looking for the
--                               substring 'Location:', stripping it and splitting on ' on ', falling
--                               back to the hardcoded 'bridge'
--
--   characters WHERE scene_location = 'bridge'   →   0 rows, in any session
--   characters.scene_location populated          →   session 3: 177 of 275 · session 5: 0 of 440
--
-- So the filter `get_characters_at_location(session_id, location)` accepts can never match, and the
-- function returns the whole active roster instead. That was reported rather than patched in
-- tests/test_locations_review.py, which pins the current behaviour.
--
-- AND `territory` IS NOT THE MISSING TABLE. It holds 892 star systems, session 3 only, keyed by
-- system_name with values like '236-39', beside controlling_faction, population and slave_population.
-- It is the strategic layer. That is why `characters.scene_territory_id` → `territory(id)`, added by
-- 068_system_id_fk.sql, has never had a reader: a scene on a bridge is not a star system.
--
-- THE TABLE THAT DOES DESCRIBE A SCENE IS `location_catalog`: twelve rows, PRIMARY KEY (name), with
-- location_type and an atmosphere, already read by core/briefing.py and modules/locations.py for
-- lighting, sound and smell. Nine are ship interiors and three are at pelabuhan.
--
-- WHAT THIS MIGRATION DOES:
--   1. adds the places Arc I and Arc II actually name, so the catalogue describes the story rather
--      than one ship;
--   2. gives `player_context` a location column pointing at the same catalogue, so both sides of the
--      comparison speak one language.
--
-- WHAT IT DOES NOT DO, deliberately:
--   * no foreign key on `characters.scene_location`. Session 3 holds 177 free-form values written by
--     curation and the session is frozen; a constraint would reject them and a backfill would be a
--     campaign-wide rewrite nobody asked for. The catalogue is the vocabulary and a check reports
--     outliers, rather than the database refusing writes.
--   * `characters.scene_territory_id` is left alone. It is dead and named in tests/test_dead_columns.py,
--     and dropping a column from 715 rows is a separate call from giving scenes a vocabulary.

-- 1. The places the prose names.
--
-- Sourced from the scene headings of adventures/tkg-arc1-restart/novel/the-sunrise.md (38 scenes) and
-- from rp-current-session.md for the Arc II settlements. Slugs follow the existing convention
-- (<place>_<area>, as in pelabuhan_port and pelabuhan_square).
INSERT INTO maya_rp.location_catalog (name, location_type, default_lighting, default_sound, default_smell, atmosphere)
VALUES
    -- Arc I. Counts are scene-heading mentions in the compiled novel.
    ('padang_limbah',           'surface', 'open sky, no shade',        'wind over dust',        'dry grit',           'exposed'),
    ('gate_35',                 'station', 'inspection lamps',          'queued drives',         'coolant and paper',  'procedural'),
    ('kembar_ganjil',           'colony',  'dock floods',               'cranes and traffic',    'salt and fuel',      'transactional'),
    ('kandang_tujuh',           'colony',  'barred light',              'metal on metal',        'confined air',       'carceral'),
    ('limbah_7',                'colony',  'corridor strip lighting',   'ventilation',           'recycled air',       'orbital'),
    ('blok_c',                  'colony',  'forge glow',                'hammer on plate',       'hot metal',          'industrial'),
    ('pejabat_penempatan',      'colony',  'office fluorescents',       'pens and printers',     'paper and toner',    'administrative'),
    ('koridor_dua_belas',       'ship',    'deck strips',               'footsteps and hum',     'recycled air',       'cramped'),
    ('pelabuhan_tujuh_belas',   'colony',  'harbour lights',            'winches and gulls',     'brine',              'working port'),
    ('koloni_sembilan_belas',   'colony',  'colony floods',             'settlement noise',      'soil and smoke',     'frontier'),
    -- Arc II. Where session 5 stands now: the record names all three.
    ('heaven_reach',            'colony',  'colony floods',             'market and carts',      'soil and cooking',   'settled'),
    ('bukit_kaca',              'colony',  'furnace light',             'rollers and hammers',   'hot iron',           'industrial'),
    ('pesisir_panjang',         'colony',  'shore light',               'water on hulls',        'salt and fish',      'coastal')
ON CONFLICT (name) DO NOTHING;

-- 2. The player's own location, in the same vocabulary.
--
-- `current_focus` stays as it is: it is prose, other readers use it, and nothing here rewrites it.
-- The new column is what the engine reads, and `get_player_location` prefers it, falling back to the
-- parse only while a session has not set it.
ALTER TABLE maya_rp.player_context
    ADD COLUMN IF NOT EXISTS location TEXT;

COMMENT ON COLUMN maya_rp.player_context.location IS
    'A maya_rp.location_catalog.name. Null means unset, and the reader must say so rather than assume '
    'a place. Before this column, the reader parsed current_focus for the substring ''Location:'' and '
    'returned the hardcoded ''bridge'' when that failed, which is why every unset session reported '
    'its scene on the bridge.';
