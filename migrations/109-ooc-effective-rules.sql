-- 109: OOC resolver cascade — the ruleset one session actually lives under.
-- Additive only. Owner: maya.
--   Apply: PGPASSWORD=REDACTED psql -h 100.65.243.60 -U maya -d maya_memory -f <this>
--
-- Design: wiki/rp-dev/OOC-SYSTEM-DESIGN-2026-09-19.md §8 (D2) — the cascade
-- (campaign rows + session rows, filtered to the persona's trait composition) is
-- resolution policy, so it belongs in the store both planes read rather than in
-- the harness plugin, which stays stateless (§13 option C).
--
-- Order is meaningful: campaign rules first, then session rows, each by id, so a
-- caller that stops at the first match sees the broad rule before the override.

CREATE OR REPLACE FUNCTION maya_rp.ooc_effective_rules(p_session_id integer, p_traits text[])
RETURNS SETOF maya_rp.ooc_rules
LANGUAGE sql
STABLE
AS $$
  SELECT r.*
  FROM maya_rp.ooc_rules AS r
  WHERE r.enabled
    AND (r.session_id IS NULL OR r.session_id = p_session_id)
    AND (r.trait IS NULL OR r.trait = ANY (p_traits))
  ORDER BY (r.session_id IS NOT NULL) ASC, r.id ASC;
$$;

COMMENT ON FUNCTION maya_rp.ooc_effective_rules(integer, text[]) IS
  'OOC rule cascade: campaign rows (session_id IS NULL) + this session''s rows, kept to the persona traits, enabled only. `general` should always be included by the caller.';
