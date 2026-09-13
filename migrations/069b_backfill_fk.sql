-- BACKFILL 069b: resolve name strings -> territory_id

-- 1. PLANETS: match by exact or substring of territory name (incl TKG worlds)
UPDATE maya_rp.planets p
SET territory_id = t.id
FROM maya_rp.territory t
WHERE p.territory_id IS NULL AND t.session_id = 3
  AND (lower(p.system_name) = lower(t.system_name)
       OR (p.system_name ~ '^[0-9]+-[0-9]+$' AND t.system_name ~ '^[0-9]+-[0-9]+$'
           AND p.system_name = t.system_name)
       OR (t.system_name ~ '^[0-9]+-[0-9]+$' AND p.system_name = t.system_name)
       OR (p.system_name ILIKE '%' || t.system_name || '%')
       OR (t.system_name ILIKE '%' || p.system_name || '%'));

-- 2. GOVERNOR APPLICANTS: home_system
UPDATE maya_rp.governor_applicants g
SET home_territory_id = t.id
FROM maya_rp.territory t
WHERE g.home_territory_id IS NULL AND t.session_id = 3
  AND (g.home_system = t.system_name
       OR (g.home_system ~ '^[0-9]+-[0-9]+$' AND t.system_name ~ '^[0-9]+-[0-9]+$'
           AND g.home_system = t.system_name)
       OR g.home_system ILIKE '%' || t.system_name || '%');

-- assigned_system
UPDATE maya_rp.governor_applicants g
SET assigned_territory_id = t.id
FROM maya_rp.territory t
WHERE g.assigned_territory_id IS NULL AND g.assigned_system IS NOT NULL AND t.session_id = 3
  AND (g.assigned_system = t.system_name
       OR (g.assigned_system ~ '^[0-9]+-[0-9]+$' AND t.system_name ~ '^[0-9]+-[0-9]+$'
           AND g.assigned_system = t.system_name)
       OR g.assigned_system ILIKE '%' || t.system_name || '%');

-- 3. YARD CAPACITY: location (Heaven/Mastika Belt/Relau/Waja -> territory)
UPDATE maya_rp.yard_capacity y
SET territory_id = t.id
FROM maya_rp.territory t
WHERE y.territory_id IS NULL AND t.session_id = 3
  AND (y.location = t.system_name
       OR y.location ILIKE '%' || t.system_name || '%'
       OR t.system_name ILIKE '%' || y.location || '%');
