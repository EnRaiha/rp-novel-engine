-- The same defect as migration 128, in the other two instance views: neither
-- `megastructure_status` nor `port_overview` exposed `session_id`, so the readers that query them
-- returned every campaign's rows and had no way to ask for one campaign's.
--
-- `CREATE OR REPLACE VIEW` may only append a column, so session_id is the last column in both.
CREATE OR REPLACE VIEW maya_rp.megastructure_status AS
 SELECT mc.id,
    mt.name,
    mt.fantasy_tier,
    mc.current_phase,
    mc.progress_pct,
    mc.estimated_completion,
    mc.status,
    s.name AS sector_name,
    t.system_name AS territory_name,
    mc.session_id
   FROM maya_rp.megastructure_construction mc
     JOIN maya_rp.megastructure_types mt ON mt.id = mc.megastructure_type_id
     LEFT JOIN maya_rp.sectors s ON s.id = mc.sector_id
     LEFT JOIN maya_rp.territory t ON t.id = mc.territory_id;

CREATE OR REPLACE VIEW maya_rp.port_overview AS
 SELECT p.id,
    p.name,
    pt.name AS port_type,
    pt.category,
    p.level,
    p.status,
    t.system_name AS territory_name,
    p.built_at,
    p.upgrades_applied,
    p.session_id
   FROM maya_rp.ports p
     JOIN maya_rp.port_types pt ON pt.id = p.port_type_id
     JOIN maya_rp.territory t ON t.id = p.territory_id;
