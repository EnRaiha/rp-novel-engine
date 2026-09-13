-- BACKFILL 069c: resolve OLD-scale coords (×10) -> territory_id
-- planets / governor_applicants / yard_capacity hold pre-migration "X-Y" strings.

-- helper approach: join by scaled coord match
-- planet system_name "13-11" -> territory "130-110"
UPDATE maya_rp.planets p
SET territory_id = t.id
FROM maya_rp.territory t
WHERE p.territory_id IS NULL AND t.session_id = 3
  AND t.system_name ~ '^[0-9]+-[0-9]+$'
  AND p.system_name ~ '^[0-9]+-[0-9]+$'
  AND (split_part(t.system_name,'-',1)::int = split_part(p.system_name,'-',1)::int * 10)
  AND (split_part(t.system_name,'-',2)::int = split_part(p.system_name,'-',2)::int * 10);

-- governor applicants home_system (old scale)
UPDATE maya_rp.governor_applicants g
SET home_territory_id = t.id
FROM maya_rp.territory t
WHERE g.home_territory_id IS NULL AND t.session_id = 3
  AND t.system_name ~ '^[0-9]+-[0-9]+$'
  AND g.home_system ~ '^[0-9]+-[0-9]+$'
  AND (split_part(t.system_name,'-',1)::int = split_part(g.home_system,'-',1)::int * 10)
  AND (split_part(t.system_name,'-',2)::int = split_part(g.home_system,'-',2)::int * 10);

-- governor applicants assigned_system (old scale)
UPDATE maya_rp.governor_applicants g
SET assigned_territory_id = t.id
FROM maya_rp.territory t
WHERE g.assigned_territory_id IS NULL AND g.assigned_system IS NOT NULL AND t.session_id = 3
  AND t.system_name ~ '^[0-9]+-[0-9]+$'
  AND g.assigned_system ~ '^[0-9]+-[0-9]+$'
  AND (split_part(t.system_name,'-',1)::int = split_part(g.assigned_system,'-',1)::int * 10)
  AND (split_part(t.system_name,'-',2)::int = split_part(g.assigned_system,'-',2)::int * 10);

-- yard_capacity: named locations (Mastika Belt -> Mastika? Heaven -> TKG Heaven territory?)
-- Mastika Belt / TKG Heaven are locations, not territory names — best-effort by substring
UPDATE maya_rp.yard_capacity y
SET territory_id = t.id
FROM maya_rp.territory t
WHERE y.territory_id IS NULL AND t.session_id = 3
  AND (lower(y.location) LIKE '%' || lower(t.system_name) || '%'
       OR lower(t.system_name) LIKE '%' || lower(y.location) || '%');
