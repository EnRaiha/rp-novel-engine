-- 110: widen ooc_rules.layer to carry an explicit `tool` authoring.
-- Additive only. Owner: maya.
--   Apply: PGPASSWORD=REDACTED psql -h 100.65.243.60 -U maya -d maya_memory -f <this>
--
-- Why: migration 108 allowed layer IN ('somatic','dialogue','both'), which left
-- the tool surface unreachable by design — any `both` rule then saw tool
-- arguments, which is the false positive §2 of the design note names (paths and
-- identifiers tripping a phrasing rule). Making `tool` an authored layer turns
-- that reach into an explicit opt-in per rule.

ALTER TABLE maya_rp.ooc_rules DROP CONSTRAINT IF EXISTS ooc_rules_layer_check;
ALTER TABLE maya_rp.ooc_rules
  ADD CONSTRAINT ooc_rules_layer_check
  CHECK (layer IN ('somatic', 'dialogue', 'both', 'tool'));

COMMENT ON COLUMN maya_rp.ooc_rules.layer IS
  'Prose surface the rule sees: somatic (narration), dialogue (quoted speech), both (whole text), or tool (a tool argument, opt-in only).';
