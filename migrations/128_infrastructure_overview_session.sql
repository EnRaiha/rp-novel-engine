-- The view that lists facilities did not expose `session_id`, so there was no way to ask for one
-- campaign's facilities: `list_infrastructure` and `get_infrastructure` returned every session's, and
-- playing Arc I showed the frozen campaign's buildings. A view that cannot answer "whose" is the bug.
CREATE OR REPLACE VIEW maya_rp.infrastructure_overview AS
 SELECT ii.id,
    ii.name,
    it.name AS type_name,
    it.category,
    it.fantasy_tier,
    ii.level,
    ii.status,
    t.system_name AS territory_name,
    s.name AS sector_name,
    ii.built_at,
    ii.upgrades_applied,
    ii.session_id
   FROM maya_rp.infrastructure_instances ii
     JOIN maya_rp.infrastructure_types it ON it.id = ii.infrastructure_type_id
     LEFT JOIN maya_rp.territory t ON t.id = ii.territory_id
     LEFT JOIN maya_rp.sectors s ON s.id = ii.sector_id;

-- Note: `CREATE OR REPLACE VIEW` may only append a column, never insert one in the middle, so
-- session_id is the last column rather than sitting beside id where a reader would look for it.
