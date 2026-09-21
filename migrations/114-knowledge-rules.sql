-- 114 — knowledge-blindness rules (M4): a fact a character cannot know.
--
-- Owner: maya. Apply by hand:
--   PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>
--
-- A `knowledge` rule's id names the fact (`fact:<key>`), and its pattern matches
-- the prose that reveals it. When the text matches and a character present in the
-- scene has no `character_knowledge` row for that key, the engine records a
-- knowledge finding. The rule ships DISABLED: enabling it on canon starts
-- flagging prose immediately.
--
-- Add a fact for a character with:
--   python3 scripts/cli.py ooc know learn "queen_lives" --observer=<id> --session=3

-- The kind vocabulary widens by exactly one value; the old constraint is
-- replaced rather than dropped so an unknown kind still refuses.
ALTER TABLE maya_rp.ooc_rules DROP CONSTRAINT IF EXISTS ooc_rules_kind_check;
ALTER TABLE maya_rp.ooc_rules ADD CONSTRAINT ooc_rules_kind_check
    CHECK (kind IN ('forbidden_lexicon', 'somatic_lock', 'modern_phrasing', 'scripted_beat', 'knowledge'));

INSERT INTO maya_rp.ooc_rules (id, scope, session_id, trait, kind, layer, pattern, is_regex, delta, enabled)
VALUES ('fact:queen_lives', 'campaign', NULL, NULL, 'knowledge', 'both',
        're:(the queen lives|queen survived|she still lives)', true, 1, false)
ON CONFLICT (id) DO UPDATE SET layer='both';

COMMENT ON COLUMN maya_rp.ooc_rules.kind IS
    'somatic_lock | forbidden_lexicon | modern_phrasing | scripted_beat | knowledge (M4: id=fact:<key>, flags prose a present character cannot know).';
