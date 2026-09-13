-- 089-deck-children-blood.sql — CORRECTION: deck children are BLOOD children of the King.
-- The previous 'foster' classification was a broken-system assumption (engine never
-- registered royal-child rows → audit wrongly concluded 'foster'). Proven wrong now:
-- these are the King's own children by his queens. Elanor remains THE blood heir.

DO $$
DECLARE
  c_rec RECORD;
  mid INT;
BEGIN
  DROP TABLE IF EXISTS _tmp_children;
  CREATE TEMP TABLE _tmp_children (
    cid INT, cname TEXT, cgender TEXT, ctype TEXT, mother_id INT, cdesc TEXT
  );
  INSERT INTO _tmp_children VALUES
    (171, 'Prince Fajar al-Dabaran',    'male',   'prince', 20,  'Twin of Senja, son of the King & Maya. Says "Ay-ah!". First-born son (twin).'),
    (172, 'Princess Senja al-Dabaran',  'female', 'princess',20,  'Twin of Fajar, daughter of the King & Maya.'),
    (173, 'Prince Irfan al-Dabaran',    'male',   'prince', 14,  'Son of the King & Rika Voss (Iron Maiden). Age 3.'),
    (174, 'Princess Nilam al-Dabaran',  'female', 'princess',63,  'Daughter of the King & Dr Sierra Vance. Age 2.'),
    (175, 'Prince Ardhan al-Dabaran',   'male',   'prince', 65,  'Son of the King & Priestess of the Desert Storm (Sera). Age 3.'),
    (176, 'Princess Embun al-Dabaran',  'female', 'princess',62,  'Daughter of the King & Rhea (Forest Keeper). Age 2.'),
    (177, 'Princess Cahaya al-Dabaran', 'female', 'princess',25,  'Daughter of the King & Celestine Voss (Star Forger). Newborn.');

  FOR c_rec IN SELECT * FROM _tmp_children ORDER BY cid LOOP
    CONTINUE WHEN EXISTS (SELECT 1 FROM maya_rp.characters WHERE id = c_rec.cid);
    INSERT INTO maya_rp.characters
      (id, session_id, name, role, archetype, bond, status, traits,
       is_spouse, character_type, controlled_by, presence, species,
       clearance_level, bond_level, last_seen_day, background, appearance, description)
    VALUES
      (c_rec.cid, 3, c_rec.cname,
       CASE c_rec.ctype WHEN 'prince' THEN 'Prince of House al-Dabaran — blood son of the King'
                        ELSE 'Princess of House al-Dabaran — blood daughter of the King' END,
       'royal_child', 5, 'active',
       '["royal-blood","child","house-al-dabaran"]'::jsonb,
       false, 'royal', 'ai', 'visible',
       'human', 1, 5, 243,
       'Blood child of King Izzat al-Setia — part of the royal bloodline. Registered after the
        false "foster" assumption was corrected.',
       'Young royal of House al-Dabaran.',
       c_rec.cdesc);
  END LOOP;

  DROP TABLE IF EXISTS _tmp_children;
END $$;