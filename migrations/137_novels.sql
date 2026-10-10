-- 137: every session names the novel it belongs to.
--
-- A novel is a property of the campaign. It lives on `sessions`, and every session-scoped row
-- inherits it through `session_id`, so no row copies the novel and nothing can drift from the
-- session it belongs to.
--
-- Four rows: the two campaigns that hold rows, the prequel that The Sunrise revamps, and `scratch`.
-- `scratch` is the column default, so the 97 test files that insert a `sessions` row keep working,
-- and an unbound campaign stays visible instead of merging into a canon novel.
--
-- `tkg-prequel` keeps its own row: `novel_chunks.book` holds `prequel-the-descent.md` and
-- `prequel-the-twenty-four.md`, and those chunks belong to the prequel, not to Setia Kingdom. No
-- chunk row moves here.
--
-- APPLIED 2026-10-10 as `maya`, recorded in `_migrations`. Safe to run twice: the table and the column are guarded, the insert conflicts on the
-- primary key, and each UPDATE touches only a session still on the `scratch` default.
--
-- Rollback: ALTER TABLE sessions DROP COLUMN novel_id; DROP TABLE novels; No row is lost.
BEGIN;
SET LOCAL search_path TO maya_rp;

CREATE TABLE IF NOT EXISTS novels (
    novel_id text PRIMARY KEY,
    title text NOT NULL,
    universe text NOT NULL DEFAULT 'TKG',
    adventures_dir text,
    status text NOT NULL DEFAULT 'active',
    supersedes text REFERENCES novels(novel_id),
    story_order integer,
    created_at timestamptz DEFAULT now()
);

COMMENT ON COLUMN novels.adventures_dir IS
  'Directory holding this novel''s text. tkg-prequel shares adventures/tkg/novel with Setia Kingdom; its files are prequel-*.md.';
COMMENT ON COLUMN novels.supersedes IS
  'Novel this row revamps. tkg-the-sunrise revamps tkg-prequel.';
COMMENT ON COLUMN novels.story_order IS
  'Reading order across novels. A revamp shares its original''s order.';
COMMENT ON COLUMN novels.status IS
  'active while a session plays it, superseded when a later novel replaces it.';

INSERT INTO novels (novel_id, title, universe, adventures_dir, status, supersedes, story_order) VALUES
    ('tkg-prequel',       'TKG Prequel',              'TKG', 'adventures/tkg/novel',        'superseded', NULL,          0),
    ('tkg-the-sunrise',   'TKG — Arc I: The Sunrise', 'TKG', 'adventures/tkg-arc1-restart', 'active',     'tkg-prequel', 0),
    ('tkg-setia-kingdom', 'TKG Setia Kingdom',        'TKG', 'adventures/tkg',              'active',     NULL,          1),
    ('scratch',           'Scratch',                  'TKG', NULL,                          'active',     NULL,          NULL)
ON CONFLICT (novel_id) DO NOTHING;

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS novel_id text NOT NULL DEFAULT 'scratch'
    REFERENCES novels(novel_id);

-- The guard follows 140_research_gate_names.sql: a re-run names the row still on the default, so it
-- cannot revert a binding a later card made.
UPDATE sessions SET novel_id = 'tkg-setia-kingdom' WHERE id = 3 AND novel_id = 'scratch';
UPDATE sessions SET novel_id = 'tkg-the-sunrise' WHERE id = 5 AND novel_id = 'scratch';

CREATE INDEX IF NOT EXISTS sessions_novel_id_idx ON sessions (novel_id);

COMMIT;
