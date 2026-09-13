-- BACKFILL: resolve location strings -> territory_id
-- Ships: "Frontier X-Y", "Sector X-Y — ...", "TKG ... — Sector X-Y"
UPDATE maya_rp.ships s
SET territory_id = t.id
FROM maya_rp.territory t
WHERE s.session_id = 3
  AND s.territory_id IS NULL
  AND t.session_id = 3
  AND t.system_name ~ '^[0-9]+-[0-9]+$'
  AND s.location ~ ('(^|[^0-9])' || t.system_name || '([^0-9]|$)');

-- Characters: scene_location contains "X-Y — ..."
UPDATE maya_rp.characters c
SET scene_territory_id = t.id
FROM maya_rp.territory t
WHERE c.session_id = 3
  AND c.scene_territory_id IS NULL
  AND t.session_id = 3
  AND t.system_name ~ '^[0-9]+-[0-9]+$'
  AND c.scene_location ~ ('(^|[^0-9])' || t.system_name || '([^0-9]|$)');

-- Campaigns
UPDATE maya_rp.campaigns c
SET target_territory_id = t.id
FROM maya_rp.territory t
WHERE t.session_id = 3
  AND t.system_name ~ '^[0-9]+-[0-9]+$'
  AND c.target_system ~ ('(^|[^0-9])' || t.system_name || '([^0-9]|$)');

-- Incoming raids (named targets like 'Tempa', 'Bisik')
UPDATE maya_rp.incoming_raids r
SET target_territory_id = t.id
FROM maya_rp.territory t
WHERE t.session_id = 3
  AND r.target_territory_id IS NULL
  AND lower(r.target_system) = lower(t.system_name);

-- Anti cloak grids
UPDATE maya_rp.anti_cloak_grids g
SET territory_id = t.id
FROM maya_rp.territory t
WHERE t.session_id = 3
  AND t.system_name ~ '^[0-9]+-[0-9]+$'
  AND g.system_name ~ ('(^|[^0-9])' || t.system_name || '([^0-9]|$)');
