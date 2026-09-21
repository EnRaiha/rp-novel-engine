-- 112 — campaign layer: stage-scoped rules, endings, lorebook, director notes.
--
-- Additive only. Owner: maya.
--   Apply: PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>
--
-- The resolver (109) returns `SETOF maya_rp.ooc_rules`, so the two new columns
-- arrive through it without touching the function.

-- ── Stage-scoped rules (M27) ────────────────────────────────────────────────
-- A rule may be limited to an arc window: `min_stage` opens it, `max_stage`
-- closes it. Ranks are lockdown < selective < confrontation.
ALTER TABLE maya_rp.ooc_rules ADD COLUMN IF NOT EXISTS min_stage text;
ALTER TABLE maya_rp.ooc_rules ADD COLUMN IF NOT EXISTS max_stage text;

-- ── Endings (M28) ───────────────────────────────────────────────────────────
-- `condition` is a small expression the engine evaluates:
--   {"stat": "deviation", "op": ">=", "value": 100}
-- stats: deviation, roleplay_points, audits, findings, suspicion_max,
--        bond_max, beats_done.
CREATE TABLE IF NOT EXISTS maya_rp.ooc_endings (
    id bigserial PRIMARY KEY,
    session_id integer NOT NULL,
    name text NOT NULL,
    kind text NOT NULL DEFAULT 'neutral',
    condition text NOT NULL,
    prose text,
    triggered_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ooc_endings_session_name UNIQUE (session_id, name)
);

COMMENT ON TABLE maya_rp.ooc_endings IS
    'Campaign endings: a stat condition, its kind (bad/tragic/true/neutral), and the prose it resolves to.';

-- ── Lorebook (M29) ──────────────────────────────────────────────────────────
-- Keyword-triggered lore entries: injected only when a keyword appears in the
-- turn's context, so world detail stays out of the standing prompt.
CREATE TABLE IF NOT EXISTS maya_rp.ooc_lorebook (
    id bigserial PRIMARY KEY,
    session_id integer,
    keywords text[] NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    stage text,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE maya_rp.ooc_lorebook IS
    'Keyword-triggered lore entries; session_id NULL = campaign-wide. stage limits an entry to one arc stage.';

-- ── Director notes (M30) ────────────────────────────────────────────────────
-- Player-side out-of-character steering: recorded, never audited as prose.
CREATE TABLE IF NOT EXISTS maya_rp.ooc_directives (
    id bigserial PRIMARY KEY,
    session_id integer NOT NULL,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ── Seeds: the campaign's lorebook (fasa 6) ─────────────────────────────────
INSERT INTO maya_rp.ooc_lorebook (session_id, keywords, title, content)
SELECT NULL, ARRAY['System','Overseer','audit','penalty'], 'System Overseer',
       'An unyielding autonomous entity that monitors host compliance. Emotional leaks raise deviation; the penalty ladder runs Neural Tremor, Meridian Lock, System Reclamation. It never notices mortals noticing — suspicion belongs to the observer.'
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.ooc_lorebook WHERE title = 'System Overseer');

INSERT INTO maya_rp.ooc_lorebook (session_id, keywords, title, content)
SELECT NULL, ARRAY['loophole','malicious compliance','protect','covert'], 'Malicious Compliance',
       'Obedience in form, protection in effect. A compliant line that scores 40 or more earns a roleplay point, and points are paid only when the turn''s actions name a companion: the letter of the order is kept while its consequence shields an ally.'
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.ooc_lorebook WHERE title = 'Malicious Compliance');

INSERT INTO maya_rp.ooc_lorebook (session_id, keywords, title, content)
SELECT NULL, ARRAY['companion','bond','spouse'], 'Companions of the Crown',
       'A companion is bound by love, marriage or loyalty (bond above zero). They are the only subjects that make a roleplay-point payment legal, and the only ones whose suspicion moves: micro-slips that repeat raise it, clean turns relax it.'
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.ooc_lorebook WHERE title = 'Companions of the Crown');

-- ── Seeds: session 3 endings ────────────────────────────────────────────────
INSERT INTO maya_rp.ooc_endings (session_id, name, kind, condition, prose)
SELECT 3, 'System Soul Reclamation', 'bad', '{"stat":"deviation","op":">=","value":100}',
       'The ladder completes: System Reclamation takes the shell, and the crown speaks with no one behind it.'
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.ooc_endings WHERE session_id = 3 AND name = 'System Soul Reclamation');

INSERT INTO maya_rp.ooc_endings (session_id, name, kind, condition, prose)
SELECT 3, 'The Mask Breaks', 'tragic', '{"stat":"suspicion_max","op":">=","value":85}',
       'A companion stops watching for the gap and names it aloud. The mask breaks in front of the court.'
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.ooc_endings WHERE session_id = 3 AND name = 'The Mask Breaks');

INSERT INTO maya_rp.ooc_endings (session_id, name, kind, condition, prose)
SELECT 3, 'Silent Liberation', 'true', '{"stat":"roleplay_points","op":">=","value":500}',
       'Enough points banked, enough trust earned: the crown finally buys silence from its own overseer.'
WHERE NOT EXISTS (SELECT 1 FROM maya_rp.ooc_endings WHERE session_id = 3 AND name = 'Silent Liberation');
