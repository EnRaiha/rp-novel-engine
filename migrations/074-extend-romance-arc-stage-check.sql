-- 074-extend-romance-arc-stage-check.sql
-- BUGFIX: _map_bond_to_arc_stage() emits 'attraction' (5+) and 'deepening' (7+),
-- but the DB CHECK only allowed legacy stages — every advance_bond() past bond 4
-- crashed. Merged canonical list: strangers, acquaintance, attraction, deepening,
-- intimacy, devotion + legacy (flirtation, kiss, estrangement).
ALTER TABLE maya_rp.romance_arcs DROP CONSTRAINT IF EXISTS romance_arcs_arc_stage_check;
ALTER TABLE maya_rp.romance_arcs ADD CONSTRAINT romance_arcs_arc_stage_check CHECK (
    arc_stage = ANY (ARRAY[
        'strangers','acquaintance','attraction','deepening','intimacy','devotion',
        'flirtation','kiss','estrangement'
    ])
);
