-- SYSTEMIC: seven views in maya_rp expose no `session_id`, so every reader of them either leaks
-- across campaigns or cannot filter at all. Found while wiring `space_horror.get_active_threats`,
-- which took a session argument and ignored it because the view had nothing to filter on.
--
--     characters_unified   diplomatic_overview   economic_dashboard   economic_overview
--     infestation_threats  slave_overview        tech_tree
--
-- This migration fixes the one on the current path. The other six need the same treatment and are
-- recorded in wiki/rp-dev/VIEW-SESSION-OWNERSHIP-2026-10-03.md rather than swept in here, because
-- each has a different base table and each reader needs its own check.
--
-- `CREATE OR REPLACE VIEW` may only append a column, so session_id goes last.
CREATE OR REPLACE VIEW maya_rp.infestation_threats AS
 SELECT ii.id,
    ii.sector_id,
    s.name AS sector_name,
    ii.territory_id,
    t.system_name AS territory_name,
    st.name AS stage,
    st.threat_level,
    ii.biomass,
    ii.spread_progress,
    ii.contained,
    ii.containment_level,
    ii.discovered,
    ii.status,
    ii.created_at,
    ii.session_id
   FROM maya_rp.infestation_instances ii
     LEFT JOIN maya_rp.sectors s ON s.id = ii.sector_id
     LEFT JOIN maya_rp.territory t ON t.id = ii.territory_id
     JOIN maya_rp.infestation_stages st ON st.id = ii.stage_id
  WHERE ii.status::text <> ALL (ARRAY['destroyed'::character varying, 'eradicated'::character varying]::text[]);
